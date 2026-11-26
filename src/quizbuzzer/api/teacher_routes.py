"""Teacher REST endpoints, prefix /api/teacher (contracts/rest-api.md).

Plain `def` handlers: FastAPI runs them in worker threads, which suits the synchronous Google
client and sqlite3 (research R8). Feature 002 adds its passcode check as a router dependency.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from quizbuzzer.api.schemas import ImportTabsRequest, PreviewRequest, PreviewResponse, TabsResponse
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
