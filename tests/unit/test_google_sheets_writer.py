"""GoogleSheetsWriter request shape, scope and error mapping (003 T018; research R1).

No network: the discovery service is a stub, and credential creation is intercepted.
"""

from __future__ import annotations

import socket

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from quizbuzzer.config import Settings
from quizbuzzer.models import CellWrite
from quizbuzzer.services.google_sheets_writer import WRITE_SCOPE, GoogleSheetsWriter
from quizbuzzer.services.sheets_adapter import (
    SheetNotFound,
    SheetReadOnly,
    SheetsUnavailable,
)

EMAIL = "sa@proj.iam.gserviceaccount.com"


class _Request:
    def __init__(self, result):
        self._result = result

    def execute(self):
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result


class _Values:
    def __init__(self, api):
        self._api = api

    def batchUpdate(self, **kwargs):  # noqa: N802 (Google API name)
        self._api.calls.append(("values.batchUpdate", kwargs))
        return _Request(self._api.result)


class _Spreadsheets:
    def __init__(self, api):
        self._api = api

    def values(self):
        return _Values(self._api)


class StubApi:
    def __init__(self, result=None):
        self.result = result if result is not None else {"totalUpdatedCells": 2}
        self.calls = []

    def spreadsheets(self):
        return _Spreadsheets(self)


@pytest.fixture
def settings(tmp_path):
    key = tmp_path / "key.json"
    key.write_text('{"client_email": "%s"}' % EMAIL, encoding="utf-8")
    return Settings(credentials_path=key, db_path=tmp_path / "x.db", host="h", port=1)


CELLS = [CellWrite("G5", "（1）光合作用"), CellWrite("G11", "=1+1")]


def test_one_batch_update_raw_with_ranges_from_the_given_title(settings):
    api = StubApi()
    n = GoogleSheetsWriter(settings, service=api).write_cells("sid", 7, "Tom's tab", CELLS)
    assert n == 2
    assert api.calls == [(
        "values.batchUpdate",
        {
            "spreadsheetId": "sid",
            "body": {
                "valueInputOption": "RAW",
                "data": [
                    {"range": "'Tom''s tab'!G5", "values": [["（1）光合作用"]]},
                    {"range": "'Tom''s tab'!G11", "values": [["=1+1"]]},
                ],
            },
        },
    )]


def test_falls_back_to_cell_count_when_google_omits_the_total(settings):
    assert GoogleSheetsWriter(settings, service=StubApi({})).write_cells("sid", 0, "T", CELLS) == 2


def test_no_cells_makes_no_request(settings):
    api = StubApi()
    assert GoogleSheetsWriter(settings, service=api).write_cells("sid", 0, "T", []) == 0
    assert api.calls == []


def http_error(status, body=b"{}"):
    return HttpError(Response({"status": status}), body)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (http_error(403), SheetReadOnly),
        (http_error(403, b'{"error": {"details": [{"reason": "SERVICE_DISABLED"}]}}'), SheetsUnavailable),
        (http_error(404), SheetNotFound),
        (http_error(400), SheetsUnavailable),
        (http_error(500), SheetsUnavailable),
        (socket.timeout("timed out"), SheetsUnavailable),
        (ConnectionResetError(), SheetsUnavailable),
    ],
)
def test_error_mapping(settings, error, expected):
    with pytest.raises(expected) as info:
        GoogleSheetsWriter(settings, service=StubApi(error)).write_cells("sid", 0, "T", CELLS)
    if expected is SheetReadOnly:
        assert info.value.service_account_email == EMAIL


def _capture_scopes(monkeypatch):
    seen = {}

    class FakeCreds:
        @staticmethod
        def from_service_account_file(path, scopes):
            seen["scopes"] = list(scopes)
            return object()

    import google.oauth2.service_account as sa
    import google_auth_httplib2
    import googleapiclient.discovery as discovery

    monkeypatch.setattr(sa, "Credentials", FakeCreds)
    monkeypatch.setattr(discovery, "build", lambda *a, **k: StubApi())
    monkeypatch.setattr(google_auth_httplib2, "AuthorizedHttp", lambda creds, http=None: object())
    return seen


def test_writer_asks_for_the_write_scope(settings, monkeypatch):
    seen = _capture_scopes(monkeypatch)
    GoogleSheetsWriter(settings).write_cells("sid", 0, "T", CELLS)
    assert WRITE_SCOPE == "https://www.googleapis.com/auth/spreadsheets"
    assert seen["scopes"] == [WRITE_SCOPE]


def test_import_adapter_still_uses_only_the_read_only_scope(settings, monkeypatch):
    """003 FR-014 / 001 FR-005: the import client must never get the write scope."""
    from quizbuzzer.services.google_sheets_adapter import READONLY_SCOPE, GoogleSheetsAdapter

    seen = _capture_scopes(monkeypatch)
    GoogleSheetsAdapter(settings)._api()
    assert seen["scopes"] == [READONLY_SCOPE]
    assert READONLY_SCOPE == "https://www.googleapis.com/auth/spreadsheets.readonly"
    assert not hasattr(GoogleSheetsAdapter, "write_cells")
