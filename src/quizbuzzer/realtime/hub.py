"""RealtimeHub: teacher and student WebSockets and server -> client pushes (002 research R6).

The database is the source of truth (Principle IV). Every message is a full snapshot, built by
the services; the hub only delivers. Teacher sockets form one set. Student sockets are keyed by
the `StudentKey` resolved from their cookie at connect time (or None), so a group push can
target one group's sockets without a DB lookup. The hub never builds student data itself:
student messages come only from ParticipationService through the visibility filter
(Constitution III).

Services are synchronous and run in worker threads; they deliver through
`publish_from_thread` (teachers) and `send_from_thread` (any socket list).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import Any

import anyio.from_thread
from fastapi import WebSocket

from quizbuzzer.models import Activity, StudentKey

log = logging.getLogger("quizbuzzer.realtime")

Message = dict[str, Any]


def activity_state_message(activity: Activity | None) -> Message:
    """`activity.state` summary (001 contracts/websocket.md)."""
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


def student_state_message(state: dict[str, Any]) -> Message:
    """`student.state` (002 contracts/websocket.md › /ws/student)."""
    return {"type": "student.state", "state": state}


def dashboard_state_message(dashboard: dict[str, Any]) -> Message:
    """`dashboard.state` (002 contracts/websocket.md › /ws/teacher)."""
    return {"type": "dashboard.state", "dashboard": dashboard}


class RealtimeHub:
    def __init__(self) -> None:
        self.teachers: set[WebSocket] = set()
        self.students: dict[WebSocket, StudentKey | None] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def __len__(self) -> int:
        with self._lock:
            return len(self.teachers) + len(self.students)

    # --- registration (call from the event loop) -----------------------------------------

    def connect(self, ws: WebSocket) -> None:
        """Register an accepted teacher socket."""
        self._loop = asyncio.get_running_loop()
        with self._lock:
            self.teachers.add(ws)

    connect_teacher = connect

    def connect_student(self, ws: WebSocket, key: StudentKey | None) -> None:
        self._loop = asyncio.get_running_loop()
        with self._lock:
            self.students[ws] = key

    def disconnect(self, ws: WebSocket) -> None:
        with self._lock:
            self.teachers.discard(ws)
            self.students.pop(ws, None)

    # --- queries (safe from any thread) --------------------------------------------------

    def teacher_sockets(self) -> list[WebSocket]:
        with self._lock:
            return list(self.teachers)

    def student_sockets(
        self, activity_id: int | None = None, group_number: int | None = None
    ) -> list[tuple[WebSocket, StudentKey | None]]:
        """Student sockets, optionally only those keyed to (activity_id, group_number)."""
        with self._lock:
            pairs = list(self.students.items())
        if activity_id is None and group_number is None:
            return pairs
        return [
            (ws, key)
            for ws, key in pairs
            if key is not None
            and (activity_id is None or key.activity_id == activity_id)
            and (group_number is None or key.group_number == group_number)
        ]

    # --- delivery --------------------------------------------------------------------------

    async def send_many(self, pairs: Iterable[tuple[WebSocket, Message]]) -> None:
        for ws, message in pairs:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 - a dead socket must not stop the others
                log.info("dropping socket after failed send")
                self.disconnect(ws)

    async def broadcast(self, message: Message) -> None:
        """Send one message to every teacher socket."""
        await self.send_many((ws, message) for ws in self.teacher_sockets())

    def publish_from_thread(self, message: Message) -> None:
        """Broadcast to teachers from synchronous service code (001 behaviour kept)."""
        if not self.teacher_sockets():
            return
        self._run_from_thread(self.broadcast, message)

    def send_from_thread(self, pairs: Sequence[tuple[WebSocket, Message]]) -> None:
        """Deliver prepared (socket, message) pairs from synchronous service code."""
        if not pairs:
            return
        self._run_from_thread(self.send_many, list(pairs))

    def _run_from_thread(self, fn: Callable[[Any], Awaitable[None]], arg: Any) -> None:
        try:
            anyio.from_thread.run(fn, arg)
        except RuntimeError:
            # Not an AnyIO worker thread (e.g. a plain thread): hand off to the socket loop.
            if self._loop is not None and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(fn(arg), self._loop)
