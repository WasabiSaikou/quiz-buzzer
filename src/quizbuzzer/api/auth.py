"""Teacher passcode and teacher sessions (002 research R1; diagrams/002-seq-teacher-unlock.puml).

`TeacherSessions` keeps random session tokens in memory, so a restart locks every teacher page
(FR-003). The passcode is compared in constant time and never stored, echoed or logged (FR-004).

Every `/api/teacher/*` request except `POST /api/teacher/session` passes through
`TeacherGuardMiddleware`, which applies `require_teacher` **before** routing and body parsing,
so a request without the cookie gets 401 even when its body is malformed (contracts/rest-api.md ›
Guard). `/ws/teacher` calls `require_teacher` itself before sending anything.
"""

from __future__ import annotations

import hmac
import logging
import secrets
import threading

from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger("quizbuzzer.auth")

TEACHER_COOKIE = "qb_teacher"
SESSION_PATH = "/api/teacher/session"
TEACHER_PREFIX = "/api/teacher"


class WrongPasscode(Exception):
    def __init__(self) -> None:
        super().__init__("Wrong passcode.")


class TeacherRequired(Exception):
    def __init__(self) -> None:
        super().__init__("Teacher passcode required.")


class TeacherSessions:
    """In-memory set of teacher session tokens (data-model.md › TeacherSessions)."""

    def __init__(self, passcode: str) -> None:
        self._passcode = passcode.encode("utf-8")
        self._tokens: set[str] = set()
        self._lock = threading.Lock()

    def create(self, passcode: str) -> str:
        """A new session token if `passcode` matches; otherwise WrongPasscode."""
        if not isinstance(passcode, str) or not hmac.compare_digest(
            passcode.encode("utf-8"), self._passcode
        ):
            raise WrongPasscode()
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._tokens.add(token)
        return token

    def is_valid(self, token: str | None) -> bool:
        if not token or not isinstance(token, str):
            return False
        with self._lock:
            return token in self._tokens


def require_teacher(conn: HTTPConnection) -> None:
    """Raise TeacherRequired unless the request or socket carries a valid teacher cookie."""
    sessions: TeacherSessions = conn.app.state.teacher_sessions
    if not sessions.is_valid(conn.cookies.get(TEACHER_COOKIE)):
        raise TeacherRequired()


def is_guarded_path(path: str) -> bool:
    return (path == TEACHER_PREFIX or path.startswith(TEACHER_PREFIX + "/")) and path != SESSION_PATH


class TeacherGuardMiddleware:
    """Pure ASGI middleware: 401 `teacher_required` for unauthenticated /api/teacher/* requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and is_guarded_path(scope["path"]):
            try:
                require_teacher(HTTPConnection(scope))
            except TeacherRequired as exc:
                log.info("request failed: teacher_required")
                response = JSONResponse(
                    status_code=401,
                    content={"error": {"code": "teacher_required", "message": str(exc)}},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
