"""RealtimeHub: the set of teacher WebSockets and server -> client pushes (research R8).

The database is the source of truth (Principle IV); messages carry state read from it, and a
client that reconnects gets the current state on connect. Student sockets and their visibility
filter (Principle III) arrive with the student features.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import anyio.from_thread
from fastapi import WebSocket

from quizbuzzer.models import Activity

log = logging.getLogger("quizbuzzer.realtime")


def activity_state_message(activity: Activity | None) -> dict[str, Any]:
    """`activity.state` summary (contracts/websocket.md)."""
    if activity is None:
        return {"type": "activity.state", "activity": None}
    return {
        "type": "activity.state",
        "activity": {
            "id": activity.id,
            "title": activity.title,
            "phase": activity.phase.value,
            "groupCount": activity.group_count,
            "totals": {
                "units": len(activity.units),
                "slots": sum(len(u.slots) for u in activity.units),
            },
            "importedAt": activity.imported_at,
        },
    }


class RealtimeHub:
    def __init__(self) -> None:
        self._sockets: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def __len__(self) -> int:
        return len(self._sockets)

    def connect(self, ws: WebSocket) -> None:
        """Register an accepted socket (call from the event loop)."""
        self._loop = asyncio.get_running_loop()
        self._sockets.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._sockets.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        for ws in list(self._sockets):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 - a dead socket must not stop the others
                log.info("dropping teacher socket after failed send")
                self._sockets.discard(ws)

    def publish_from_thread(self, message: dict[str, Any]) -> None:
        """Broadcast from synchronous service code running in a worker thread."""
        if not self._sockets:
            return
        try:
            anyio.from_thread.run(self.broadcast, message)
        except RuntimeError:
            # Not an AnyIO worker thread (e.g. a plain thread): hand off to the socket loop.
            if self._loop is not None and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self.broadcast(message), self._loop)
