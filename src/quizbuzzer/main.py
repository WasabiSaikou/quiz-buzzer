"""App factory: one FastAPI process serving the API, WebSocket and static teacher page.

`create_app(adapter, db_path)` lets tests inject FakeSheetsAdapter and a temp database.
The module-level `app` uses GoogleSheetsAdapter, built lazily on first use.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from quizbuzzer import db
from quizbuzzer.api import auth_routes, student_routes, teacher_routes, ws_routes
from quizbuzzer.api.auth import TeacherGuardMiddleware, TeacherSessions, WrongPasscode
from quizbuzzer.api.schemas import PreviewResponse
from quizbuzzer.config import PASSCODE_MISSING, ConfigError, Settings, load_settings
from quizbuzzer.models import SpreadsheetInfo, TabData
from quizbuzzer.realtime.hub import RealtimeHub
from quizbuzzer.services.participation_service import (
    ActivityEnded,
    AlreadyJoined,
    AlreadySubmitted,
    GroupChangeRefused,
    InvalidAnswers,
    InvalidJoin,
    JoinRefused,
    NotAMember,
    NotOpen,
    ParticipationService,
    UnitNotFound,
)
from quizbuzzer.services.activity_service import (
    ActivityNotFound,
    ActivityService,
    CurrentActivityExists,
    ImportHasErrors,
    InvalidGroupCount,
    PreviewChanged,
    PhaseConflict,
    ReimportRefused,
    WarningsNotAcknowledged,
)
from quizbuzzer.services.sheets_adapter import (
    InvalidSheetUrl,
    SheetNotFound,
    SheetNotShared,
    SheetsAdapter,
    SheetsUnavailable,
)

log = logging.getLogger("quizbuzzer")

STATIC_DIR = Path(__file__).resolve().parent / "static"

DetailsFn = Callable[[Exception], dict[str, Any] | None]


def error_response(
    status: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    """The error envelope from contracts/rest-api.md."""
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body)


def register_error(
    app: FastAPI,
    exc_type: type[Exception],
    status: int,
    code: str,
    message: str | Callable[[Exception], str],
    details: DetailsFn | None = None,
) -> None:
    """Map a domain exception to the error envelope. User stories add their own mappings."""

    async def handler(_request: Request, exc: Exception) -> JSONResponse:
        # Log codes only: never cell text or credentials (Principle VI).
        log.info("request failed: %s", code)
        text = message(exc) if callable(message) else message
        return error_response(status, code, text, details(exc) if details else None)

    app.add_exception_handler(exc_type, handler)


class LazyGoogleSheetsAdapter:
    """Builds GoogleSheetsAdapter on first use, so the app starts without Google access."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._inner: SheetsAdapter | None = None

    def _get(self) -> SheetsAdapter:
        if self._inner is None:
            from quizbuzzer.services.google_sheets_adapter import GoogleSheetsAdapter

            self._inner = GoogleSheetsAdapter(self._settings)
        return self._inner

    @property
    def service_account_email(self) -> str:
        return self._settings.service_account_email

    def list_tabs(self, spreadsheet_id: str) -> SpreadsheetInfo:
        return self._get().list_tabs(spreadsheet_id)

    def read_tab(self, spreadsheet_id: str, sheet_id: int) -> TabData:
        return self._get().read_tab(spreadsheet_id, sheet_id)


def _register_core_errors(app: FastAPI) -> None:
    register_error(app, InvalidSheetUrl, 400, "invalid_url", lambda e: str(e))
    register_error(
        app,
        SheetNotShared,
        403,
        "not_shared",
        "This spreadsheet is not shared with the app. "
        "Share it (Viewer) with the address below, then try again.",
        lambda e: {"serviceAccountEmail": e.service_account_email},  # type: ignore[attr-defined]
    )
    register_error(
        app,
        SheetNotFound,
        404,
        "not_found",
        "The spreadsheet or tab could not be found. Check the link, or that the tab still exists.",
    )
    register_error(
        app,
        SheetsUnavailable,
        502,
        "sheets_unavailable",
        "Google Sheets could not be reached. Check the network connection and try again.",
    )
    register_error(app, ConfigError, 500, "server_misconfigured", lambda e: str(e))

    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(p) for p in err["loc"][1:]) for err in exc.errors()})
        return error_response(
            422,
            "invalid_request",
            "The request is missing fields or has fields of the wrong type.",
            {"fields": fields},
        )

    app.add_exception_handler(RequestValidationError, validation_handler)


def _preview_details(exc: Exception) -> dict[str, Any]:
    preview = PreviewResponse.from_preview(exc.preview)  # type: ignore[attr-defined]
    return {"preview": preview.model_dump(mode="json", by_alias=True)}


def _register_activity_errors(app: FastAPI) -> None:
    """US2 service exceptions -> contracts/rest-api.md › Error envelope."""
    register_error(app, InvalidGroupCount, 422, "invalid_group_count", lambda e: str(e))
    register_error(app, ImportHasErrors, 422, "import_errors", lambda e: str(e), _preview_details)
    register_error(
        app, WarningsNotAcknowledged, 422, "warnings_not_acknowledged", lambda e: str(e)
    )
    register_error(app, PreviewChanged, 409, "preview_changed", lambda e: str(e), _preview_details)
    register_error(
        app,
        CurrentActivityExists,
        409,
        "current_activity_exists",
        lambda e: str(e),
        lambda e: {
            "activity": {
                "id": e.activity_id,  # type: ignore[attr-defined]
                "title": e.title,  # type: ignore[attr-defined]
                "phase": e.phase.value,  # type: ignore[attr-defined]
            }
        },
    )
    register_error(app, ActivityNotFound, 404, "not_found", lambda e: str(e))
    register_error(
        app,
        ReimportRefused,
        409,
        "reimport_refused",
        lambda e: str(e),
        lambda e: {"phase": e.phase.value},  # type: ignore[attr-defined]
    )


def _register_phase_errors(app: FastAPI) -> None:
    """002 contracts/rest-api.md: Teacher activity control."""
    register_error(
        app,
        PhaseConflict,
        409,
        "phase_conflict",
        lambda e: str(e),
        lambda e: {"phase": e.phase.value},  # type: ignore[attr-defined]
    )


def _register_student_errors(app: FastAPI) -> None:
    """002 contracts/rest-api.md › Student API. Details carry only the student's own data."""
    register_error(
        app, InvalidJoin, 422, "invalid_join", lambda e: str(e),
        lambda e: {"field": e.field, "max": e.max},  # type: ignore[attr-defined]
    )
    register_error(
        app, JoinRefused, 409, "join_refused", lambda e: str(e),
        lambda e: {"phase": e.phase.value if e.phase else None},  # type: ignore[attr-defined]
    )
    register_error(app, AlreadyJoined, 409, "already_joined", lambda e: str(e))
    register_error(app, NotAMember, 401, "not_a_member", lambda e: str(e))
    register_error(
        app, GroupChangeRefused, 409, "group_change_refused", lambda e: str(e),
        lambda e: {"phase": e.phase.value},  # type: ignore[attr-defined]
    )
    register_error(
        app, InvalidAnswers, 422, "invalid_answers", lambda e: str(e),
        lambda e: {  # type: ignore[attr-defined]
            "subParts": e.sub_parts,
            "reasons": {str(k): r for k, r in e.reasons.items()},
        },
    )
    register_error(app, NotOpen, 409, "not_open", lambda e: str(e))
    register_error(app, ActivityEnded, 409, "activity_ended", lambda e: str(e))
    register_error(app, UnitNotFound, 404, "unit_not_found", lambda e: str(e))
    register_error(
        app, AlreadySubmitted, 409, "already_submitted", lambda e: str(e),
        lambda e: {"submission": e.submission},  # type: ignore[attr-defined]
    )


def _register_auth_errors(app: FastAPI) -> None:
    """002 contracts/rest-api.md › Teacher access. No details: never hint at the passcode."""
    register_error(app, WrongPasscode, 401, "wrong_passcode", "Wrong passcode.")


def create_app(
    adapter: SheetsAdapter | None = None,
    db_path: str | Path | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    if not settings.teacher_passcode.strip():
        raise ConfigError(PASSCODE_MISSING)  # 002 FR-004: refuse to start without it
    db_path = Path(db_path) if db_path is not None else settings.db_path

    conn = db.connect(db_path)
    try:
        db.init_schema(conn)
    finally:
        conn.close()

    app = FastAPI(title="Quiz Buzzer")
    app.state.settings = settings
    app.state.db_path = db_path
    app.state.adapter = adapter if adapter is not None else LazyGoogleSheetsAdapter(settings)
    app.state.hub = RealtimeHub()
    app.state.participation = ParticipationService(db_path, app.state.hub)
    app.state.service = ActivityService(
        app.state.adapter,
        db_path,
        app.state.hub,
        student_publisher=app.state.participation.publish_student_states,
    )
    app.state.participation.teacher_publisher = app.state.service.publish_dashboard
    app.state.teacher_sessions = TeacherSessions(settings.teacher_passcode.strip())

    _register_core_errors(app)
    _register_activity_errors(app)
    _register_auth_errors(app)
    _register_phase_errors(app)
    _register_student_errors(app)
    app.add_middleware(TeacherGuardMiddleware)
    app.include_router(auth_routes.router)
    app.include_router(teacher_routes.router)
    app.include_router(student_routes.router)
    app.include_router(ws_routes.router)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/teacher", include_in_schema=False)
    def teacher_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "teacher.html", media_type="text/html; charset=utf-8")

    @app.get("/student", include_in_schema=False)
    def student_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "student.html", media_type="text/html; charset=utf-8")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/student", status_code=307)  # 002 research R8

    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    # `uvicorn quizbuzzer.main:app` reads this attribute; building it lazily means importing
    # create_app (e.g. in tests) does not create the real database or read .env.
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
