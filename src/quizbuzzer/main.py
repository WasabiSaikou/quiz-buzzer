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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from quizbuzzer import db
from quizbuzzer.api import teacher_routes
from quizbuzzer.config import ConfigError, Settings, load_settings
from quizbuzzer.models import SpreadsheetInfo, TabData
from quizbuzzer.services.activity_service import ActivityService
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


def create_app(
    adapter: SheetsAdapter | None = None,
    db_path: str | Path | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or load_settings()
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
    app.state.hub = None  # RealtimeHub is wired in by US2 (T037)
    app.state.service = ActivityService(app.state.adapter, db_path, app.state.hub)

    _register_core_errors(app)
    app.include_router(teacher_routes.router)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/teacher", include_in_schema=False)
    def teacher_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "teacher.html", media_type="text/html; charset=utf-8")

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
