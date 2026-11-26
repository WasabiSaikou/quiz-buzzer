"""SheetsAdapter interface and its errors (diagrams/system-component.puml).

The adapter takes a spreadsheet_id, never a URL: ActivityService parses URLs first
(services/sheets_url.py). Implementations: GoogleSheetsAdapter (read-only scope) and
tests/fakes/fake_sheets_adapter.py: FakeSheetsAdapter.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from quizbuzzer.models import SpreadsheetInfo, TabData


class SheetsError(Exception):
    """Base class for errors raised while locating or reading a sheet."""


class InvalidSheetUrl(SheetsError):
    """The URL is not a Google Sheets spreadsheet link (FR-002). Raised before any network call."""


class SheetNotShared(SheetsError):
    """The spreadsheet is not shared with the service account (FR-004)."""

    def __init__(self, service_account_email: str, message: str | None = None) -> None:
        self.service_account_email = service_account_email
        super().__init__(message or "Spreadsheet is not shared with the service account.")


class SheetNotFound(SheetsError):
    """The spreadsheet, or the tab with the requested sheet_id, does not exist."""


class SheetsUnavailable(SheetsError):
    """Google could not be reached, timed out, or returned an unexpected error (502)."""


@runtime_checkable
class SheetsAdapter(Protocol):
    @property
    def service_account_email(self) -> str: ...

    def list_tabs(self, spreadsheet_id: str) -> SpreadsheetInfo:
        """Spreadsheet title and every tab (sheetId, title, index). Read-only."""
        ...

    def read_tab(self, spreadsheet_id: str, sheet_id: int) -> TabData:
        """Displayed values and merges of one tab. Unknown sheet_id -> SheetNotFound. Read-only."""
        ...
