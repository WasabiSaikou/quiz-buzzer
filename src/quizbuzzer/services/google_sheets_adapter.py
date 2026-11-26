"""GoogleSheetsAdapter: reads Google Sheets with a read-only service account (research R5).

FR-005 is enforced at the credential level: the import scope is spreadsheets.readonly, so this
adapter cannot modify a sheet even by mistake.
"""

from __future__ import annotations

import socket
from typing import Any

from quizbuzzer.config import Settings
from quizbuzzer.models import Merge, SpreadsheetInfo, TabData, TabInfo
from quizbuzzer.services.sheets_adapter import SheetNotFound, SheetNotShared, SheetsUnavailable

READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
TIMEOUT_SECONDS = 10

LIST_TABS_FIELDS = "properties.title,sheets.properties(sheetId,title,index)"
READ_TAB_FIELDS = "properties.title,sheets(properties(sheetId,title),merges)"


def quote_tab_title(title: str) -> str:
    """A1 range for a whole tab: 'title', with single quotes doubled."""
    return "'" + title.replace("'", "''") + "'"


class GoogleSheetsAdapter:
    """Implements SheetsAdapter against the Google Sheets API v4."""

    def __init__(self, settings: Settings, service: Any | None = None) -> None:
        self._settings = settings
        self._service = service  # injectable for tests; built lazily otherwise

    @property
    def service_account_email(self) -> str:
        return self._settings.service_account_email

    def _api(self) -> Any:
        if self._service is None:
            import google_auth_httplib2
            import httplib2
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            # Accessing service_account_email validates the key file first (clear ConfigError).
            _ = self._settings.service_account_email
            creds = service_account.Credentials.from_service_account_file(
                str(self._settings.credentials_path), scopes=[READONLY_SCOPE]
            )
            http = google_auth_httplib2.AuthorizedHttp(
                creds, http=httplib2.Http(timeout=TIMEOUT_SECONDS)
            )
            self._service = build("sheets", "v4", http=http, cache_discovery=False)
        return self._service

    def list_tabs(self, spreadsheet_id: str) -> SpreadsheetInfo:
        data = self._execute(
            self._api().spreadsheets().get(spreadsheetId=spreadsheet_id, fields=LIST_TABS_FIELDS)
        )
        tabs = tuple(
            TabInfo(
                sheet_id=int(p.get("sheetId", 0)),
                title=str(p.get("title", "")),
                index=int(p.get("index", 0)),
            )
            for p in (s.get("properties", {}) for s in data.get("sheets", []))
        )
        if not tabs:
            raise SheetNotFound(f"Spreadsheet {spreadsheet_id} has no tabs.")
        return SpreadsheetInfo(
            spreadsheet_id=spreadsheet_id,
            title=str(data.get("properties", {}).get("title", "")),
            tabs=tuple(sorted(tabs, key=lambda t: t.index)),
        )

    def read_tab(self, spreadsheet_id: str, sheet_id: int) -> TabData:
        api = self._api()
        meta = self._execute(
            api.spreadsheets().get(spreadsheetId=spreadsheet_id, fields=READ_TAB_FIELDS)
        )
        for sheet in meta.get("sheets", []):
            props = sheet.get("properties", {})
            if int(props.get("sheetId", 0)) == sheet_id:
                break
        else:
            raise SheetNotFound(f"No tab with id {sheet_id} in spreadsheet {spreadsheet_id}.")
        title = str(props.get("title", ""))
        values = self._execute(
            api.spreadsheets()
            .values()
            .get(
                spreadsheetId=spreadsheet_id,
                range=quote_tab_title(title),
                valueRenderOption="FORMATTED_VALUE",
            )
        )
        grid = [[("" if v is None else str(v)) for v in row] for row in values.get("values", [])]
        merges: list[Merge] = [
            (
                int(m.get("startRowIndex", 0)),
                int(m.get("endRowIndex", 0)),
                int(m.get("startColumnIndex", 0)),
                int(m.get("endColumnIndex", 0)),
            )
            for m in sheet.get("merges", [])
        ]
        return TabData(
            spreadsheet_id=spreadsheet_id,
            spreadsheet_title=str(meta.get("properties", {}).get("title", "")),
            sheet_id=sheet_id,
            title=title,
            grid=grid,
            merges=merges,
        )

    def _execute(self, request: Any) -> dict:
        from googleapiclient.errors import HttpError

        try:
            return request.execute()
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            content = exc.content.decode("utf-8", "ignore") if isinstance(exc.content, bytes) else ""
            reason = f"{exc} {content}".lower()
            if status == 403 and ("service_disabled" in reason or "has not been used" in reason):
                raise SheetsUnavailable("The Google Sheets API is not enabled for the service account's project.") from None
            if status == 403:
                raise SheetNotShared(self.service_account_email) from None
            if status == 404:
                raise SheetNotFound("Spreadsheet not found.") from None
            raise SheetsUnavailable(f"Google Sheets API error (HTTP {status}).") from None
        except (TimeoutError, socket.timeout, OSError) as exc:
            raise SheetsUnavailable(f"Google Sheets could not be reached ({type(exc).__name__}).") from None
        except Exception as exc:  # httplib2 transport errors and anything unexpected
            if type(exc).__module__.startswith("httplib2"):
                raise SheetsUnavailable(f"Google Sheets could not be reached ({type(exc).__name__}).") from None
            raise
