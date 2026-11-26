"""Teacher WebSocket /ws/teacher (contracts/websocket.md).

On connect the socket receives the current activity.state, so a reconnecting client recovers
state from the server (Principle IV). Client frames are ignored in this feature.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket
from starlette.concurrency import run_in_threadpool

from quizbuzzer.realtime.hub import RealtimeHub, activity_state_message

router = APIRouter()


@router.websocket("/ws/teacher")
async def teacher_socket(ws: WebSocket) -> None:
    hub: RealtimeHub = ws.app.state.hub
    service = ws.app.state.service
    await ws.accept()
    hub.connect(ws)  # register first, so no push between the read below and now is missed
    try:
        activity = await run_in_threadpool(service.get_current_activity)
        await ws.send_json(activity_state_message(activity))
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
            # Any client frame is ignored; phase always comes from the database.
    finally:
        hub.disconnect(ws)
