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
import secrets
import sqlite3
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quizbuzzer import db
from quizbuzzer.models import Participant, Phase, StudentKey, Submission
from quizbuzzer.realtime.hub import student_state_message
from quizbuzzer.services.visibility import student_view

log = logging.getLogger("quizbuzzer.participation")

PARTICIPANT_COOKIE = "qb_participant"
PARTICIPANT_COOKIE_MAX_AGE = 12 * 60 * 60  # seconds (002 research R2)


MAX_NAME = 20  # data-model.md › Participant.display_name
MAX_ANSWER = 200  # data-model.md › SubmissionAnswer.text


# --- Service exceptions (plan › Diagram Blueprint; contracts/rest-api.md › Student API) ------


class InvalidJoin(ValueError):
    def __init__(self, field: str, max_value: int) -> None:
        self.field = field
        self.max = max_value
        if field == "displayName":
            message = f"Enter a name of 1–{max_value} characters."
        else:
            message = f"Choose a group from 1 to {max_value}."
        super().__init__(message)


class JoinRefused(Exception):
    def __init__(self, phase: Phase | None) -> None:
        self.phase = phase
        if phase is None:
            message = "There is no activity to join right now."
        elif phase is Phase.CLOSED:
            message = "This activity has ended; it can no longer be joined."
        else:
            message = "That activity is no longer the current one. Reload the page."
        super().__init__(message)


class AlreadyJoined(Exception):
    def __init__(self) -> None:
        super().__init__("You have already joined this activity.")


class NotAMember(Exception):
    def __init__(self) -> None:
        super().__init__("You are not in a group of the current activity. Join a group first.")


class GroupChangeRefused(Exception):
    def __init__(self, phase: Phase) -> None:
        self.phase = phase
        if phase is Phase.OPEN:
            message = "Groups are fixed once the activity has opened."
        else:
            message = "The activity has ended; groups can no longer change."
        super().__init__(message)


_REASON_TEXT = {
    "empty": "is empty",
    "too_long": f"is longer than {MAX_ANSWER} characters",
    "unknown": "does not belong to this question",
    "missing": "is missing",
    "duplicate": "was sent twice",
}


class InvalidAnswers(ValueError):
    def __init__(self, reasons: dict[int, str]) -> None:
        self.reasons = dict(sorted(reasons.items()))
        self.sub_parts = sorted(reasons)
        super().__init__(
            " ".join(f"Answer （{k}） {_REASON_TEXT[r]}." for k, r in self.reasons.items())
        )


class NotOpen(Exception):
    def __init__(self) -> None:
        super().__init__("The activity has not opened yet.")


class ActivityEnded(Exception):
    def __init__(self) -> None:
        super().__init__("The activity has ended.")


class UnitNotFound(LookupError):
    def __init__(self, unit_id: object) -> None:
        self.unit_id = unit_id
        super().__init__("That question is not part of this activity.")


class AlreadySubmitted(Exception):
    def __init__(self, unit_number: int, submission: dict[str, Any]) -> None:
        self.unit_number = unit_number
        self.submission = submission  # the group's OWN submission, student shape (no rank)
        super().__init__(f"Your group has already submitted question {unit_number}.")


def _utc_now_ms() -> str:
    """Server receive time: ISO-8601 UTC with milliseconds (data-model › Submission.received_at)."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def validate_display_name(value: object) -> str:
    """data-model.md › Participant.display_name: trimmed, 1–20 characters."""
    name = value.strip() if isinstance(value, str) else ""
    if not 1 <= len(name) <= MAX_NAME:
        raise InvalidJoin("displayName", MAX_NAME)
    return name


def validate_answers(answers: Iterable[Any]) -> dict[int, str]:
    """Shape checks before the transaction (research R3): sub_part -> trimmed text.

    `str.strip()` removes all Unicode whitespace, incl. U+3000 and line breaks (FR-016).
    """
    reasons: dict[int, str] = {}
    texts: dict[int, str] = {}
    for item in answers:
        k = item["subPart"] if isinstance(item, dict) else item.sub_part
        text = item["text"] if isinstance(item, dict) else item.text
        if k in texts or k in reasons:
            reasons[k] = "duplicate"
            continue
        trimmed = text.strip() if isinstance(text, str) else ""
        if not trimmed:
            reasons[k] = "empty"
        elif len(trimmed) > MAX_ANSWER:
            reasons[k] = "too_long"
        texts[k] = trimmed
    if reasons:
        raise InvalidAnswers(reasons)
    return texts


def submission_out(s: Submission) -> dict[str, Any]:
    """A submission in the student shape: never rank or winner flag (FR-023)."""
    return {
        "unitId": s.unit_id,
        "unitNumber": s.unit_number,
        "answers": [{"subPart": a.sub_part, "text": a.text} for a in s.answers],
        "submittedBy": s.submitted_by,
        "receivedAt": s.received_at,
    }


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

    # --- join / change group (diagrams/002-seq-join.puml) ------------------------------------

    def join(
        self, token: str | None, activity_id: int, group_number: object, display_name: object
    ) -> tuple[str, dict[str, Any]]:
        """Join a group of the current activity; returns (new cookie token, StudentState)."""
        name = validate_display_name(display_name)
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                current = db.find_current_activity(conn)
                if current is None or current["id"] != activity_id:
                    requested = (
                        db.get_activity_phase(conn, activity_id)
                        if isinstance(activity_id, int)
                        else None
                    )
                    raise JoinRefused(requested)
                group_count = db.get_group_count(conn, activity_id)
                if (
                    isinstance(group_number, bool)
                    or not isinstance(group_number, int)
                    or not 1 <= group_number <= group_count
                ):
                    raise InvalidJoin("groupNumber", group_count)
                if token:
                    existing = db.find_participant_by_token_hash(conn, hash_token(token))
                    if existing is not None and existing.activity_id == activity_id:
                        raise AlreadyJoined()
                new_token = secrets.token_urlsafe(32)
                participant_id = db.insert_participant(
                    conn,
                    activity_id=activity_id,
                    group_number=group_number,
                    display_name=name,
                    token_hash=hash_token(new_token),
                    joined_at=_utc_now_ms(),
                )
            key = StudentKey(activity_id, participant_id, group_number)
            state = self._student_state(conn, key)
        finally:
            conn.close()
        log.info("joined: activity=%s group=%s participant=%s", activity_id, group_number, participant_id)
        self._after_group_change(activity_id, group_number)
        return new_token, state

    def leave(self, token: str | None) -> None:
        """Leave the group (change group); only while DRAFT (FR-013)."""
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                participant, phase = self._member_in_tx(conn, token)
                if phase is not Phase.DRAFT:
                    raise GroupChangeRefused(phase)
                db.delete_participant(conn, participant.id)
        finally:
            conn.close()
        log.info("left: activity=%s group=%s", participant.activity_id, participant.group_number)
        self._after_group_change(participant.activity_id, participant.group_number)

    # --- submit (diagrams/002-seq-submit.puml; research R3; Constitution I) -------------------

    def submit(self, token: str | None, unit_id: int, answers: Iterable[Any]) -> dict[str, Any]:
        """Accept one group's answer to one unit, ranked by server arrival order.

        The phase check, duplicate check, rank = 1 + count, and insert run in ONE
        BEGIN IMMEDIATE transaction, which serialises every submit, end and cancel, so ranks
        are 1..n without gaps or repeats and nothing is accepted after CLOSED. Client time is
        never read; received_at is for display and 003's CSV only.
        """
        texts = validate_answers(answers)  # before the transaction
        conn = db.connect(self.db_path)
        try:
            try:
                with db.transaction(conn):
                    participant, phase = self._member_in_tx(conn, token)
                    if phase is Phase.DRAFT:
                        raise NotOpen()
                    if phase is Phase.CLOSED:
                        raise ActivityEnded()
                    unit = db.get_unit_for_activity(conn, unit_id, participant.activity_id)
                    if unit is None:
                        raise UnitNotFound(unit_id)
                    expected = {s.sub_part for s in unit.slots}
                    reasons = {k: "unknown" for k in texts.keys() - expected}
                    reasons |= {k: "missing" for k in expected - texts.keys()}
                    if reasons:
                        raise InvalidAnswers(reasons)
                    existing = db.get_group_submission(conn, unit.id, participant.group_number)
                    if existing is not None:
                        raise AlreadySubmitted(unit.number, submission_out(existing))
                    rank = db.count_unit_submissions(conn, unit.id) + 1
                    db.insert_submission(
                        conn,
                        unit_id=unit.id,
                        group_number=participant.group_number,
                        participant_id=participant.id,
                        rank=rank,
                        received_at=_utc_now_ms(),
                        answers=[(s.id, texts[s.sub_part]) for s in unit.slots],
                    )
            except sqlite3.IntegrityError:
                # UNIQUE(unit_id, group_number) backstop: report the group's own submission.
                existing = db.get_group_submission(conn, unit.id, participant.group_number)
                if existing is None:
                    raise
                raise AlreadySubmitted(unit.number, submission_out(existing)) from None
            submission = db.get_group_submission(conn, unit.id, participant.group_number)
        finally:
            conn.close()
        log.info(
            "submission accepted: activity=%s unit=%s group=%s",
            participant.activity_id,
            unit.id,
            participant.group_number,
        )
        self._after_submission(participant.activity_id, participant.group_number)
        return submission_out(submission)

    @staticmethod
    def _member_in_tx(conn, token: str | None) -> tuple[Participant, Phase]:
        """The caller's participant and its activity's phase, or NotAMember (FR-014)."""
        participant = db.find_participant_by_token_hash(conn, hash_token(token)) if token else None
        if participant is None:
            raise NotAMember()
        current = db.find_current_activity(conn)
        if current is not None and current["id"] != participant.activity_id:
            raise NotAMember()  # a membership of an older activity never carries over
        return participant, db.get_activity_phase(conn, participant.activity_id)

    # --- after-commit hooks: group push (US4) and teacher dashboard (US3) ---------------------

    # Called only after a successful commit, never on refusal. A submission sends nothing at
    # all to other groups' sockets, so not even the timing of a message leaks (FR-023).

    def _after_group_change(self, activity_id: int, group_number: int) -> None:
        self.publish_group_state(activity_id, group_number)  # FR-022: members update
        self._publish_teacher(activity_id)

    def _after_submission(self, activity_id: int, group_number: int) -> None:
        self.publish_group_state(activity_id, group_number)  # FR-021: teammates see it
        self._publish_teacher(activity_id)

    def _publish_teacher(self, activity_id: int) -> None:
        """dashboard.state to every teacher tab (FR-027, FR-028)."""
        if self.teacher_publisher is not None:
            self.teacher_publisher(activity_id)

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
