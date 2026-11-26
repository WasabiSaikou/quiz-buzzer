"""ActivityService: orchestrates import, preview and activity writes (diagrams/001-seq-*.puml).

The sole authority for activity phase (Principle IV). URLs are parsed here, before any adapter
call (FR-002); the parser stays pure and the fingerprint is computed here (research R6).
Every write runs in one BEGIN IMMEDIATE transaction (research R7).
"""

from __future__ import annotations

import logging
import sqlite3
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
from quizbuzzer.realtime.hub import activity_state_message
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
    def __init__(self, adapter: SheetsAdapter, db_path: str | Path, hub=None) -> None:
        self.adapter = adapter
        self.db_path = Path(db_path)
        self.hub = hub

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
        if self.hub is not None:
            self.hub.publish_from_thread(activity_state_message(activity))
