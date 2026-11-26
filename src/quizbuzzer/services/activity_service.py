"""ActivityService: orchestrates import, preview and activity writes (diagrams/001-seq-*.puml).

The sole authority for activity phase (Principle IV). URLs are parsed here, before any adapter
call (FR-002); the parser stays pure and the fingerprint is computed here (research R6).
Every write runs in one BEGIN IMMEDIATE transaction (research R7).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from quizbuzzer import db
from quizbuzzer.models import (
    MAX_GROUP_COUNT,
    MIN_GROUP_COUNT,
    Activity,
    ImportPreview,
    Phase,
    SpreadsheetInfo,
)
from quizbuzzer.realtime.hub import activity_state_message, dashboard_state_message
from quizbuzzer.services import guided_notes_parser
from quizbuzzer.services.sheets_adapter import SheetsAdapter
from quizbuzzer.services.sheets_url import parse_spreadsheet_url

log = logging.getLogger("quizbuzzer.activity")


# --- Service exceptions (plan › Diagram Blueprint) -------------------------------------------


class InvalidGroupCount(ValueError):
    def __init__(self, value: object) -> None:
        self.value = value
        super().__init__(
            f"The number of groups must be a whole number from {MIN_GROUP_COUNT} to "
            f"{MAX_GROUP_COUNT}."
        )


class _PreviewError(Exception):
    def __init__(self, preview: ImportPreview, message: str) -> None:
        self.preview = preview
        super().__init__(message)


class ImportHasErrors(_PreviewError):
    def __init__(self, preview: ImportPreview) -> None:
        super().__init__(
            preview,
            f"The preview has {len(preview.errors)} error(s). Fix them in the sheet, then "
            f"refresh the preview before confirming.",
        )


class PreviewChanged(_PreviewError):
    def __init__(self, preview: ImportPreview) -> None:
        super().__init__(
            preview,
            "The sheet changed after the preview was shown, so nothing was created. Review the "
            "updated preview and confirm again.",
        )


class WarningsNotAcknowledged(_PreviewError):
    def __init__(self, preview: ImportPreview) -> None:
        super().__init__(
            preview,
            f"The preview has {len(preview.warnings)} warning(s). Tick the box to acknowledge "
            f"them before confirming.",
        )


class CurrentActivityExists(Exception):
    def __init__(self, activity_id: int, title: str, phase: Phase) -> None:
        self.activity_id = activity_id
        self.title = title
        self.phase = phase
        hint = (
            "Re-import into it to replace its questions, or cancel it to start over."
            if phase is Phase.DRAFT
            else "End it before creating a new activity."
        )
        super().__init__(
            f'Activity "{title}" is still {phase.value}; only one activity can be current. {hint}'
        )


class ActivityNotFound(LookupError):
    def __init__(self, activity_id: int) -> None:
        self.activity_id = activity_id
        super().__init__(f"Activity {activity_id} does not exist.")


class ReimportRefused(Exception):
    """Re-import is only allowed while the activity is DRAFT (FR-024, FR-026)."""

    def __init__(self, activity_id: int, phase: Phase) -> None:
        self.activity_id = activity_id
        self.phase = phase
        super().__init__(
            f"Re-import is not possible: the activity is {phase.value}. Only a DRAFT activity's "
            f"questions can be replaced; its questions were not changed."
        )


class PhaseConflict(Exception):
    """A phase change the current phase does not allow (FR-005; contracts: phase_conflict)."""

    def __init__(self, activity_id: int, phase: Phase, action: str) -> None:
        self.activity_id = activity_id
        self.phase = phase
        self.action = action
        if action == "end" and phase is Phase.DRAFT:
            message = "A DRAFT activity cannot be ended. Use Cancel activity instead."
        elif action == "open" and phase is Phase.CLOSED:
            message = "The activity is CLOSED; a closed activity cannot be opened again."
        # 003 (contracts/rest-api.md › common refusals): results, export, CSV need CLOSED.
        elif action == "results":
            message = f"Results are available once the activity is CLOSED; it is {phase.value}."
        elif action == "export":
            message = (
                f"The results cannot be exported until the activity is CLOSED; it is {phase.value}."
            )
        elif action == "csv":
            message = (
                f"The results cannot be downloaded until the activity is CLOSED; it is {phase.value}."
            )
        else:
            message = f"The activity is already {phase.value}."
        super().__init__(message)


class CancelRefused(Exception):
    """Only a DRAFT activity can be cancelled (FR-008b)."""

    def __init__(self, activity_id: int, phase: Phase) -> None:
        self.activity_id = activity_id
        self.phase = phase
        if phase is Phase.OPEN:
            message = "An OPEN activity can only be ended."
        else:
            message = "A CLOSED activity is kept and cannot be cancelled."
        super().__init__(message)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_group_count(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not MIN_GROUP_COUNT <= value <= MAX_GROUP_COUNT
    ):
        raise InvalidGroupCount(value)
    return value


class ActivityService:
    def __init__(
        self,
        adapter: SheetsAdapter,
        db_path: str | Path,
        hub=None,
        student_publisher: Callable[[], None] | None = None,
    ) -> None:
        self.adapter = adapter
        self.db_path = Path(db_path)
        self.hub = hub
        # ParticipationService.publish_student_states (002 research R6): every student-bound
        # message is built there, through the visibility filter, never here.
        self.student_publisher = student_publisher

    # --- US1: locate and preview ---------------------------------------------------------

    def list_tabs(self, url: str) -> SpreadsheetInfo:
        """Tabs of the linked spreadsheet; `preselected_sheet_id` honours #gid= (FR-003)."""
        spreadsheet_id, gid = parse_spreadsheet_url(url)
        info = self.adapter.list_tabs(spreadsheet_id)
        return replace(info, requested_gid=gid)

    def preview_import(self, url: str, sheet_id: int) -> ImportPreview:
        """Read one tab and detect its questions; never writes anything (FR-005)."""
        spreadsheet_id, _gid = parse_spreadsheet_url(url)
        tab = self.adapter.read_tab(spreadsheet_id, sheet_id)
        preview = guided_notes_parser.parse(tab.grid, tab.merges)
        return replace(
            preview,
            spreadsheet_id=tab.spreadsheet_id,
            spreadsheet_title=tab.spreadsheet_title,
            sheet_id=tab.sheet_id,
            tab_title=tab.title,
            fingerprint=guided_notes_parser.compute_fingerprint(
                tab.spreadsheet_id, tab.sheet_id, preview.units
            ),
        )

    # --- US2: create the DRAFT activity --------------------------------------------------

    def create_from_import(
        self,
        url: str,
        sheet_id: int,
        group_count: object,
        fingerprint: str,
        acknowledge_warnings: bool,
    ) -> Activity:
        """Create the single current activity from a re-parsed, confirmed preview (FR-019–023)."""
        group_count = _validate_group_count(group_count)
        # Re-read and re-parse: client-sent cells are never trusted (research R6).
        preview = self.preview_import(url, sheet_id)
        self._check_confirmable(preview, fingerprint, acknowledge_warnings)

        now = _utc_now()
        conn = db.connect(self.db_path)
        try:
            try:
                with db.transaction(conn):
                    self._refuse_if_current_exists(conn)
                    activity_id = db.insert_activity(
                        conn,
                        title=f"{preview.spreadsheet_title} – {preview.tab_title}",
                        phase=Phase.DRAFT.value,
                        group_count=group_count,
                        spreadsheet_id=preview.spreadsheet_id,
                        sheet_id=preview.sheet_id,
                        tab_title=preview.tab_title,
                        created_at=now,
                        imported_at=now,
                    )
                    db.insert_units_and_slots(conn, activity_id, preview.units)
            except sqlite3.IntegrityError:
                # Second line of defence: the one_current_activity index (research R7).
                self._refuse_if_current_exists(conn)
                raise
            activity = db.get_activity_with_units(conn, activity_id)
        finally:
            conn.close()
        log.info("activity created: id=%s units=%s", activity.id, len(activity.units))
        self._publish(activity)
        return activity

    def get_current_activity(self) -> Activity | None:
        conn = db.connect(self.db_path)
        try:
            row = db.find_current_activity(conn)
            return db.get_activity_with_units(conn, row["id"]) if row else None
        finally:
            conn.close()

    def get_activity(self, activity_id: int) -> Activity:
        conn = db.connect(self.db_path)
        try:
            activity = db.get_activity_with_units(conn, activity_id)
        finally:
            conn.close()
        if activity is None:
            raise ActivityNotFound(activity_id)
        return activity

    # --- US3: re-import into a DRAFT activity -------------------------------------------

    def check_reimport_allowed(self, activity_id: int) -> Activity:
        """The activity, if it exists and is DRAFT; otherwise ActivityNotFound / ReimportRefused."""
        activity = self.get_activity(activity_id)
        if activity.phase is not Phase.DRAFT:
            raise ReimportRefused(activity_id, activity.phase)
        return activity

    def preview_reimport(self, activity_id: int, url: str, sheet_id: int) -> ImportPreview:
        """Preview a replacement question set (diagrams/001-seq-reimport.puml)."""
        self.check_reimport_allowed(activity_id)
        return self.preview_import(url, sheet_id)

    def replace_questions(
        self,
        activity_id: int,
        url: str,
        sheet_id: int,
        fingerprint: str,
        acknowledge_warnings: bool,
    ) -> Activity:
        """Replace the whole question set in one transaction; phase re-checked inside (FR-026)."""
        preview = self.preview_import(url, sheet_id)
        self._check_confirmable(preview, fingerprint, acknowledge_warnings)

        now = _utc_now()
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                phase = db.get_activity_phase(conn, activity_id)
                if phase is None:
                    raise ActivityNotFound(activity_id)
                if phase is not Phase.DRAFT:
                    raise ReimportRefused(activity_id, phase)
                db.replace_activity_questions(
                    conn,
                    activity_id,
                    spreadsheet_id=preview.spreadsheet_id,
                    sheet_id=preview.sheet_id,
                    tab_title=preview.tab_title,
                    imported_at=now,
                    units=preview.units,
                )
            activity = db.get_activity_with_units(conn, activity_id)
        finally:
            conn.close()
        log.info("activity questions replaced: id=%s units=%s", activity_id, len(activity.units))
        self._publish(activity)
        return activity

    # --- 002: phase changes (diagrams/002-seq-open-activity.puml, -end-activity) -------------

    def open_activity(self, activity_id: int) -> Activity:
        """DRAFT -> OPEN, checked and changed in one transaction (FR-005, FR-006)."""
        return self._transition(activity_id, "open", Phase.DRAFT, Phase.OPEN)

    def end_activity(self, activity_id: int) -> Activity:
        """OPEN -> CLOSED in one transaction; serialises with every submit (FR-017)."""
        return self._transition(activity_id, "end", Phase.OPEN, Phase.CLOSED)

    def cancel_activity(self, activity_id: int) -> None:
        """Delete a DRAFT activity (FR-008a - FR-008c; diagrams/002-seq-cancel-activity.puml).

        The phase check and the delete are one transaction, so against a simultaneous Open
        exactly one wins. Cancel is not a phase: nothing of the activity is kept.
        """
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                phase = db.get_activity_phase(conn, activity_id)
                if phase is None:
                    raise ActivityNotFound(activity_id)
                if phase is not Phase.DRAFT:
                    raise CancelRefused(activity_id, phase)
                db.delete_activity(conn, activity_id)
        finally:
            conn.close()
        log.info("activity cancelled: id=%s", activity_id)
        # After the commit: teachers see the displayed activity (latest CLOSED, or none) and no
        # dashboard; every student socket gets its new snapshot (FR-008, FR-008c).
        if self.hub is not None:
            self.hub.publish_from_thread(activity_state_message(self.get_displayed_activity()))
        self._publish_students()

    def get_displayed_activity(self) -> Activity | None:
        """The teacher's view (research R7): DRAFT/OPEN, else the latest CLOSED, else None.

        Display only: creating an activity still checks find_current_activity (DRAFT/OPEN).
        """
        conn = db.connect(self.db_path)
        try:
            row = db.find_current_activity(conn) or db.find_latest_activity(conn)
            return db.get_activity_with_units(conn, row["id"]) if row else None
        finally:
            conn.close()

    def _transition(self, activity_id: int, action: str, required: Phase, target: Phase) -> Activity:
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                phase = db.get_activity_phase(conn, activity_id)
                if phase is None:
                    raise ActivityNotFound(activity_id)
                if phase is not required:
                    raise PhaseConflict(activity_id, phase, action)
                db.set_phase(conn, activity_id, target)
            activity = db.get_activity_with_units(conn, activity_id)
        finally:
            conn.close()
        log.info("activity %s: id=%s phase=%s", action, activity_id, target.value)
        # Publish only after the commit (plan: Implementation Notes).
        self.publish_teacher_state(activity)
        self._publish_students()
        return activity

    # --- 002: teacher dashboard (contracts/rest-api.md: Dashboard) -------------------------

    def get_dashboard(self, activity_id: int) -> dict:
        conn = db.connect(self.db_path)
        try:
            activity = db.get_activity_with_units(conn, activity_id)
            if activity is None:
                raise ActivityNotFound(activity_id)
            submissions = db.list_dashboard_submissions(conn, activity_id)
            members = db.list_members_by_group(conn, activity_id)
        finally:
            conn.close()
        by_unit: dict[int, list] = {}
        for s in submissions:
            by_unit.setdefault(s.unit_id, []).append(s)
        return {
            "activityId": activity.id,
            "phase": activity.phase.value,
            "groupCount": activity.group_count,
            "units": [
                {
                    "unitId": u.id,
                    "number": u.number,
                    "kind": u.kind.value,
                    "subParts": [sl.sub_part for sl in sorted(u.slots, key=lambda sl: sl.sub_part)],
                    "submissions": [
                        {
                            "rank": s.rank,
                            "isWinner": s.is_winner,
                            "groupNumber": s.group_number,
                            "submittedBy": s.submitted_by,
                            "receivedAt": s.received_at,
                            "answers": [{"subPart": a.sub_part, "text": a.text} for a in s.answers],
                        }
                        for s in sorted(by_unit.get(u.id, []), key=lambda s: s.rank)
                    ],
                }
                for u in sorted(activity.units, key=lambda u: u.position)
            ],
            "groups": [
                {
                    "number": n,
                    "members": list(members.get(n, [])),
                    "memberCount": len(members.get(n, [])),
                }
                for n in range(1, activity.group_count + 1)
            ],
        }

    def publish_teacher_state(self, activity: Activity | None) -> None:
        """activity.state and, for an existing activity, dashboard.state to every teacher."""
        if self.hub is None:
            return
        self.hub.publish_from_thread(activity_state_message(activity))
        if activity is not None:
            self.hub.publish_from_thread(dashboard_state_message(self.get_dashboard(activity.id)))

    def publish_dashboard(self, activity_id: int) -> None:
        """dashboard.state only (after join / leave / submit; ParticipationService calls it)."""
        if self.hub is None:
            return
        try:
            dashboard = self.get_dashboard(activity_id)
        except ActivityNotFound:
            return
        self.hub.publish_from_thread(dashboard_state_message(dashboard))

    # --- helpers ------------------------------------------------------------------------------

    @staticmethod
    def _check_confirmable(
        preview: ImportPreview, fingerprint: str, acknowledge_warnings: bool
    ) -> None:
        """Order per diagrams/001-seq-confirm-create.puml: errors, fingerprint, warnings."""
        if preview.errors:
            raise ImportHasErrors(preview)
        if preview.fingerprint != fingerprint:
            raise PreviewChanged(preview)
        if preview.warnings and not acknowledge_warnings:
            raise WarningsNotAcknowledged(preview)

    @staticmethod
    def _refuse_if_current_exists(conn: sqlite3.Connection) -> None:
        current = db.find_current_activity(conn)
        if current is not None:
            raise CurrentActivityExists(current["id"], current["title"], Phase(current["phase"]))

    def _publish(self, activity: Activity | None) -> None:
        """After a commit: teacher `activity.state`, then every student's own snapshot."""
        if self.hub is not None:
            self.hub.publish_from_thread(activity_state_message(activity))
        self._publish_students()

    def _publish_students(self) -> None:
        if self.student_publisher is not None:
            self.student_publisher()
