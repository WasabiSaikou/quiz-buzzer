"""WebSockets /ws/teacher and /ws/student (001 + 002 contracts/websocket.md).

Every message is a full snapshot read from the database, and a socket gets the same snapshot on
connect, so a reconnecting client recovers state with no extra logic (Principle IV). Client
frames are ignored. Sockets are registered before the state is read, so no push between the
read and the registration is missed.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket
from starlette.concurrency import run_in_threadpool

from quizbuzzer.api.auth import TeacherRequired, require_teacher
from quizbuzzer.realtime.hub import (
    RealtimeHub,
    activity_state_message,
    dashboard_state_message,
    student_state_message,
)
from quizbuzzer.services.activity_service import ActivityNotFound
from quizbuzzer.services.participation_service import PARTICIPANT_COOKIE

router = APIRouter()


async def _drain(ws: WebSocket) -> None:
    while True:
        message = await ws.receive()
        if message["type"] == "websocket.disconnect":
            break
        # Any client frame is ignored; state always comes from the database.


@router.websocket("/ws/teacher")
async def teacher_socket(ws: WebSocket) -> None:
    hub: RealtimeHub = ws.app.state.hub
    service = ws.app.state.service
    await ws.accept()
    try:
        require_teacher(ws)  # 002 research R1: accept, then close 4401 before any message
    except TeacherRequired:
        await ws.close(code=4401)
        return
    hub.connect(ws)  # register first, so no push between the read below and now is missed
    try:
        # The displayed activity (002 research R7) and, if any, its dashboard.
        activity = await run_in_threadpool(service.get_displayed_activity)
        await ws.send_json(activity_state_message(activity))
        if activity is not None:
            try:
                dashboard = await run_in_threadpool(service.get_dashboard, activity.id)
            except ActivityNotFound:
                dashboard = None  # cancelled in between; the cancel push follows
            if dashboard is not None:
                await ws.send_json(dashboard_state_message(dashboard))
        await _drain(ws)
    finally:
        hub.disconnect(ws)


@router.websocket("/ws/student")
async def student_socket(ws: WebSocket) -> None:
    """diagrams/002-seq-reconnect.puml: resolve key -> register -> send student.state."""
    hub: RealtimeHub = ws.app.state.hub
    participation = ws.app.state.participation
    await ws.accept()
    key = await run_in_threadpool(participation.resolve_key, ws.cookies.get(PARTICIPANT_COOKIE))
    hub.connect_student(ws, key)
    try:
        state = await run_in_threadpool(participation.student_state, key)
        await ws.send_json(student_state_message(state))
        await _drain(ws)
    finally:
        hub.disconnect(ws)
