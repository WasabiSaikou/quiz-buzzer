"""ActivityService: orchestrates import, preview and activity writes (diagrams/001-seq-*.puml).

The sole authority for activity phase (Principle IV). URLs are parsed here, before any adapter
call (FR-002); the parser stays pure and the fingerprint is computed here (research R6).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from quizbuzzer.models import ImportPreview, SpreadsheetInfo
from quizbuzzer.services import guided_notes_parser
from quizbuzzer.services.sheets_adapter import SheetsAdapter
from quizbuzzer.services.sheets_url import parse_spreadsheet_url


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
