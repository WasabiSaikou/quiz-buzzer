"""Teacher REST endpoints, prefix /api/teacher (contracts/rest-api.md).

Plain `def` handlers: FastAPI runs them in worker threads, which suits the synchronous Google
client and sqlite3 (research R8). Every route here is behind 002's TeacherGuardMiddleware
(api/auth.py), which rejects requests without the teacher cookie before routing.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

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
    activity = _service(request).get_current_activity()
    return CurrentActivityResponse(
        activity=ActivityResponse.from_activity(activity) if activity else None
    )


@router.get("/activities/{activity_id}", response_model=ActivityResponse)
def get_activity(activity_id: int, request: Request) -> ActivityResponse:
    return ActivityResponse.from_activity(_service(request).get_activity(activity_id))


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
