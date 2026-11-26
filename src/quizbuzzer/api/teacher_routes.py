"""Teacher REST endpoints, prefix /api/teacher (contracts/rest-api.md).

Plain `def` handlers: FastAPI runs them in worker threads, which suits the synchronous Google
client and sqlite3 (research R8). Every route here is behind 002's TeacherGuardMiddleware
(api/auth.py), which rejects requests without the teacher cookie before routing.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response

from quizbuzzer.api.schemas import (
    ActivityResponse,
    CreateActivityRequest,
    CurrentActivityResponse,
    ImportTabsRequest,
    PreviewRequest,
    PreviewResponse,
    ReplaceQuestionsRequest,
    TabsResponse,
)
from quizbuzzer.services.activity_service import ActivityService

router = APIRouter(prefix="/api/teacher")


def _service(request: Request) -> ActivityService:
    return request.app.state.service


@router.post("/import/tabs", response_model=TabsResponse)
def import_tabs(body: ImportTabsRequest, request: Request) -> TabsResponse:
    info = _service(request).list_tabs(body.url)
    return TabsResponse.from_info(info, info.preselected_sheet_id)


@router.post("/import/preview", response_model=PreviewResponse)
def import_preview(body: PreviewRequest, request: Request) -> PreviewResponse:
    return PreviewResponse.from_preview(_service(request).preview_import(body.url, body.sheet_id))


@router.post("/activities", response_model=ActivityResponse, status_code=201)
def create_activity(body: CreateActivityRequest, request: Request) -> ActivityResponse:
    activity = _service(request).create_from_import(
        body.url, body.sheet_id, body.group_count, body.fingerprint, body.acknowledge_warnings
    )
    return ActivityResponse.from_activity(activity)


# Declared before /activities/{activity_id} so "current" is not parsed as an id.
@router.get("/activities/current", response_model=CurrentActivityResponse)
def current_activity(request: Request) -> CurrentActivityResponse:
    # 002 research R7: the displayed activity (current, else the latest CLOSED one).
    activity = _service(request).get_displayed_activity()
    return CurrentActivityResponse(
        activity=ActivityResponse.from_activity(activity) if activity else None
    )


@router.get("/activities/{activity_id}", response_model=ActivityResponse)
def get_activity(activity_id: int, request: Request) -> ActivityResponse:
    return ActivityResponse.from_activity(_service(request).get_activity(activity_id))


@router.post("/activities/{activity_id}/open", response_model=ActivityResponse)
def open_activity(activity_id: int, request: Request) -> ActivityResponse:
    """002 FR-005: DRAFT -> OPEN (diagrams/002-seq-open-activity.puml)."""
    return ActivityResponse.from_activity(_service(request).open_activity(activity_id))


@router.delete("/activities/{activity_id}", status_code=204)
def cancel_activity(activity_id: int, request: Request) -> Response:
    """002 FR-008a: cancel (delete) a DRAFT activity (diagrams/002-seq-cancel-activity.puml)."""
    _service(request).cancel_activity(activity_id)
    return Response(status_code=204)


@router.post("/activities/{activity_id}/end", response_model=ActivityResponse)
def end_activity(activity_id: int, request: Request) -> ActivityResponse:
    """002 FR-005: OPEN -> CLOSED (diagrams/002-seq-end-activity.puml)."""
    return ActivityResponse.from_activity(_service(request).end_activity(activity_id))


@router.get("/activities/{activity_id}/dashboard")
def get_dashboard(activity_id: int, request: Request) -> dict[str, Any]:
    """002 FR-026 - FR-029 (contracts/rest-api.md: Dashboard)."""
    return _service(request).get_dashboard(activity_id)


@router.post("/activities/{activity_id}/reimport/preview", response_model=PreviewResponse)
def reimport_preview(activity_id: int, body: PreviewRequest, request: Request) -> PreviewResponse:
    preview = _service(request).preview_reimport(activity_id, body.url, body.sheet_id)
    return PreviewResponse.from_preview(preview)


@router.put("/activities/{activity_id}/questions", response_model=ActivityResponse)
def replace_questions(
    activity_id: int, body: ReplaceQuestionsRequest, request: Request
) -> ActivityResponse:
    activity = _service(request).replace_questions(
        activity_id, body.url, body.sheet_id, body.fingerprint, body.acknowledge_warnings
    )
    return ActivityResponse.from_activity(activity)
