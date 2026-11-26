"""POST /api/teacher/session: unlock the teacher controls (002 contracts/rest-api.md › Teacher access).

The only /api/teacher/* route outside the teacher guard.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, StrictStr

from quizbuzzer.api.auth import SESSION_PATH, TEACHER_COOKIE, TeacherSessions

router = APIRouter()


class SessionRequest(BaseModel):
    passcode: StrictStr


@router.post(SESSION_PATH, status_code=204)
def create_session(body: SessionRequest, request: Request) -> Response:
    sessions: TeacherSessions = request.app.state.teacher_sessions
    token = sessions.create(body.passcode)  # WrongPasscode -> 401 wrong_passcode
    response = Response(status_code=204)
    # Session cookie (no Max-Age): lost when the browser closes; tokens die on restart (FR-003).
    response.set_cookie(TEACHER_COOKIE, token, httponly=True, samesite="strict", path="/")
    return response
