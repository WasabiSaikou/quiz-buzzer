"""Student REST endpoints, prefix /api/student (002 contracts/rest-api.md › Student API).

The student is identified only by the `qb_participant` cookie (FR-014). Every StudentState in a
response is built by ParticipationService through `visibility.student_view` and returned as is,
so no second shape exists that could leak more (Constitution III).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from quizbuzzer.api.schemas import JoinRequest, SubmitRequest
from quizbuzzer.services.participation_service import (
    PARTICIPANT_COOKIE,
    PARTICIPANT_COOKIE_MAX_AGE,
    ParticipationService,
)

router = APIRouter(prefix="/api/student")


def _participation(request: Request) -> ParticipationService:
    return request.app.state.participation


def _token(request: Request) -> str | None:
    return request.cookies.get(PARTICIPANT_COOKIE)


@router.get("/state")
def get_state(request: Request) -> dict[str, Any]:
    return _participation(request).state_for_token(_token(request))


@router.post("/join", status_code=201)
def join(body: JoinRequest, request: Request) -> JSONResponse:
    token, state = _participation(request).join(
        _token(request), body.activity_id, body.group_number, body.display_name
    )
    response = JSONResponse(status_code=201, content=state)
    response.set_cookie(
        PARTICIPANT_COOKIE,
        token,
        max_age=PARTICIPANT_COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


@router.delete("/membership", status_code=204)
def leave(request: Request) -> Response:
    _participation(request).leave(_token(request))
    response = Response(status_code=204)
    response.delete_cookie(PARTICIPANT_COOKIE, path="/", httponly=True, samesite="strict")
    return response


@router.post("/submissions", status_code=201)
def submit(body: SubmitRequest, request: Request) -> JSONResponse:
    submission = _participation(request).submit(
        _token(request), body.unit_id, [{"subPart": a.sub_part, "text": a.text} for a in body.answers]
    )
    return JSONResponse(status_code=201, content=submission)
