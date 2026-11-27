"""GoogleSheetsWriter: the ONLY client with the Sheets write scope (003 research R1, FR-014).

It builds its own credentials, separate from GoogleSheetsAdapter (read-only scope), and sends
each export as exactly one `spreadsheets.values.batchUpdate` with valueInputOption RAW, so text
starting with `=` is stored as text, and only cell values change (no formatting).
"""

from __future__ import annotations

import socket
from collections.abc import Sequence
from typing import Any

from quizbuzzer.config import Settings
from quizbuzzer.models import CellWrite
from quizbuzzer.services.google_sheets_adapter import TIMEOUT_SECONDS, quote_tab_title
from quizbuzzer.services.sheets_adapter import SheetNotFound, SheetReadOnly, SheetsUnavailable

WRITE_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


class GoogleSheetsWriter:
    """Implements SheetsWriter against the Google Sheets API v4."""

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

            _ = self._settings.service_account_email  # validates the key file (ConfigError)
            creds = service_account.Credentials.from_service_account_file(
                str(self._settings.credentials_path), scopes=[WRITE_SCOPE]
            )
            http = google_auth_httplib2.AuthorizedHttp(
                creds, http=httplib2.Http(timeout=TIMEOUT_SECONDS)
            )
            self._service = build("sheets", "v4", http=http, cache_discovery=False)
        return self._service

    def write_cells(
        self, spreadsheet_id: str, sheet_id: int, tab_title: str, cells: Sequence[CellWrite]
    ) -> int:
        """One values.batchUpdate, RAW; ranges use `tab_title` (the CURRENT title for sheet_id)."""
        if not cells:
            return 0
        sheet = quote_tab_title(tab_title)
        body = {
            "valueInputOption": "RAW",
            "data": [{"range": f"{sheet}!{c.a1_ref}", "values": [[c.text]]} for c in cells],
        }
        request = self._api().spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id, body=body
        )
        result = self._execute(request)
        return int(result.get("totalUpdatedCells", len(cells)))

    def _execute(self, request: Any) -> dict:
        from googleapiclient.errors import HttpError

        try:
            return request.execute()
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            content = exc.content.decode("utf-8", "ignore") if isinstance(exc.content, bytes) else ""
            reason = f"{exc} {content}".lower()
            if status == 403 and ("service_disabled" in reason or "has not been used" in reason):
                raise SheetsUnavailable(
                    "The Google Sheets API is not enabled for the service account's project."
                ) from None
            if status == 403:
                # The re-read just succeeded, so the account can see but not edit the sheet.
                raise SheetReadOnly(self.service_account_email) from None
            if status == 404:
                raise SheetNotFound("Spreadsheet not found.") from None
            raise SheetsUnavailable(f"Google Sheets API error (HTTP {status}).") from None
        except (TimeoutError, socket.timeout, OSError) as exc:
            raise SheetsUnavailable(
                f"Google Sheets could not be reached ({type(exc).__name__})."
            ) from None
        except Exception as exc:  # httplib2 transport errors and anything unexpected
            if type(exc).__module__.startswith("httplib2"):
                raise SheetsUnavailable(
                    f"Google Sheets could not be reached ({type(exc).__name__})."
                ) from None
            raise
