"""Student REST endpoints, prefix /api/student (002 contracts/rest-api.md › Student API).

The student is identified only by the `qb_participant` cookie (FR-014). Every StudentState in a
response is built by ParticipationService through `visibility.student_view` and returned as is,
so no second shape exists that could leak more (Constitution III).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from quizbuzzer.services.participation_service import PARTICIPANT_COOKIE, ParticipationService

router = APIRouter(prefix="/api/student")


def _participation(request: Request) -> ParticipationService:
    return request.app.state.participation


@router.get("/state")
def get_state(request: Request) -> dict[str, Any]:
    return _participation(request).state_for_token(request.cookies.get(PARTICIPANT_COOKIE))
