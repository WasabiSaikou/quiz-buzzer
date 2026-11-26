"""ParticipationService: student membership, submissions and every student-bound message.

Sole authority for arrival order and rank (Constitution I): see `submit`. Sole builder of
student-bound data (Constitution III): every state a student receives, over HTTP or WebSocket,
comes from `student_state`, which hands only the recipient's own group's rows to the pure
`visibility.student_view` (002 research R6; diagrams/002-seq-*.puml).

A student is identified only by the `qb_participant` cookie: the token is random, the DB holds
only its sha256 hash, and the group always comes from the stored participant (FR-014).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quizbuzzer import db
from quizbuzzer.models import StudentKey
from quizbuzzer.realtime.hub import student_state_message
from quizbuzzer.services.visibility import student_view

log = logging.getLogger("quizbuzzer.participation")

PARTICIPANT_COOKIE = "qb_participant"
PARTICIPANT_COOKIE_MAX_AGE = 12 * 60 * 60  # seconds (002 research R2)


def hash_token(token: str) -> str:
    """data-model.md › Participant.token_hash: sha256 hex of the 256-bit random token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ParticipationService:
    def __init__(
        self,
        db_path: str | Path,
        hub=None,
        teacher_publisher: Callable[[int], None] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.hub = hub
        # ActivityService.publish_teacher_state, wired by create_app (plan › Diagram Blueprint).
        self.teacher_publisher = teacher_publisher

    # --- read side ---------------------------------------------------------------------------

    def resolve_key(self, token: str | None) -> StudentKey | None:
        """The socket key for a participant cookie, or None (no or unknown membership)."""
        if not token:
            return None
        conn = db.connect(self.db_path)
        try:
            participant = db.find_participant_by_token_hash(conn, hash_token(token))
        finally:
            conn.close()
        if participant is None:
            return None
        return StudentKey(participant.activity_id, participant.id, participant.group_number)

    def student_state(self, key: StudentKey | None) -> dict[str, Any]:
        """StudentState for one recipient (contracts/rest-api.md › StudentState › Rules)."""
        conn = db.connect(self.db_path)
        try:
            return self._student_state(conn, key)
        finally:
            conn.close()

    def state_for_token(self, token: str | None) -> dict[str, Any]:
        return self.student_state(self.resolve_key(token))

    def _student_state(self, conn, key: StudentKey | None) -> dict[str, Any]:
        participant = db.get_participant(conn, key.participant_id) if key else None
        current = db.find_current_activity(conn)
        if current is not None:
            activity = db.get_activity_with_units(conn, current["id"])
            if participant is not None and participant.activity_id == activity.id:
                return self._member_view(conn, activity, participant)
            return student_view(activity, None, [], [])
        if participant is not None:
            latest = db.find_latest_activity(conn)
            if latest is not None and latest["id"] == participant.activity_id:
                activity = db.get_activity_with_units(conn, latest["id"])
                return self._member_view(conn, activity, participant)
        return student_view(None, None, [], [])

    @staticmethod
    def _member_view(conn, activity, participant) -> dict[str, Any]:
        # Only the recipient's own group's rows are read and passed on (Constitution III).
        members = db.list_group_members(conn, activity.id, participant.group_number)
        own = db.list_group_submissions(conn, activity.id, participant.group_number)
        return student_view(activity, participant, members, own)

    # --- publishing ------------------------------------------------------------------------

    def publish_student_states(self) -> None:
        """One filtered `student.state` per connected student socket (after phase changes)."""
        if self.hub is None:
            return
        self._send(self.hub.student_sockets())

    def publish_group_state(self, activity_id: int, group_number: int) -> None:
        """`student.state` only to the sockets of one group (after join, leave, submit)."""
        if self.hub is None:
            return
        self._send(self.hub.student_sockets(activity_id, group_number))

    def _send(self, sockets) -> None:
        if not sockets:
            return
        conn = db.connect(self.db_path)
        try:
            cache: dict[StudentKey | None, dict[str, Any]] = {}
            pairs = []
            for ws, key in sockets:
                if key not in cache:
                    cache[key] = student_state_message(self._student_state(conn, key))
                pairs.append((ws, cache[key]))
        finally:
            conn.close()
        self.hub.send_from_thread(pairs)
