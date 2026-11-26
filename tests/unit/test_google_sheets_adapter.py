"""GoogleSheetsAdapter request shapes and error mapping, against a stub API object.

No network: the googleapiclient service is replaced by a stub (research R5).
"""

from __future__ import annotations

import socket

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from quizbuzzer.config import Settings
from quizbuzzer.services.google_sheets_adapter import (
    LIST_TABS_FIELDS,
    READ_TAB_FIELDS,
    GoogleSheetsAdapter,
    quote_tab_title,
)
from quizbuzzer.services.sheets_adapter import SheetNotFound, SheetNotShared, SheetsUnavailable


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

    def get(self, **kwargs):
        self._api.calls.append(("values.get", kwargs))
        return _Request(self._api.values_result)


class _Spreadsheets:
    def __init__(self, api):
        self._api = api

    def get(self, **kwargs):
        self._api.calls.append(("get", kwargs))
        return _Request(self._api.get_result)

    def values(self):
        return _Values(self._api)


class StubApi:
    def __init__(self, get_result=None, values_result=None):
        self.get_result = get_result
        self.values_result = values_result
        self.calls = []

    def spreadsheets(self):
        return _Spreadsheets(self)


@pytest.fixture
def key_file(tmp_path):
    p = tmp_path / "key.json"
    p.write_text('{"client_email": "sa@proj.iam.gserviceaccount.com"}', encoding="utf-8")
    return p


def adapter(key_file, api):
    settings = Settings(credentials_path=key_file, db_path=key_file.parent / "x.db", host="h", port=1)
    return GoogleSheetsAdapter(settings, service=api)


def http_error(status, body=b"{}"):
    return HttpError(Response({"status": status}), body)


META = {
    "properties": {"title": "Ch3"},
    "sheets": [
        {"properties": {"sheetId": 0, "title": "講義", "index": 0}},
        {
            "properties": {"sheetId": 918273645, "title": "Tom's tab", "index": 1},
            "merges": [{"startRowIndex": 2, "endRowIndex": 4, "endColumnIndex": 3}],
        },
    ],
}


def test_list_tabs(key_file):
    api = StubApi(get_result=META)
    info = adapter(key_file, api).list_tabs("sid")
    assert api.calls == [("get", {"spreadsheetId": "sid", "fields": LIST_TABS_FIELDS})]
    assert info.title == "Ch3"
    assert [(t.sheet_id, t.title, t.index) for t in info.tabs] == [
        (0, "講義", 0),
        (918273645, "Tom's tab", 1),
    ]


def test_read_tab_uses_title_range_formatted_values_and_merges(key_file):
    api = StubApi(get_result=META, values_result={"values": [["題號", "作答"], ["1"]]})
    tab = adapter(key_file, api).read_tab("sid", 918273645)
    assert api.calls[0] == ("get", {"spreadsheetId": "sid", "fields": READ_TAB_FIELDS})
    assert api.calls[1] == (
        "values.get",
        {"spreadsheetId": "sid", "range": "'Tom''s tab'", "valueRenderOption": "FORMATTED_VALUE"},
    )
    assert (tab.spreadsheet_title, tab.title, tab.sheet_id) == ("Ch3", "Tom's tab", 918273645)
    assert tab.grid == [["題號", "作答"], ["1"]]
    assert tab.merges == [(2, 4, 0, 3)]  # omitted indices default to 0


def test_read_tab_unknown_sheet_id(key_file):
    with pytest.raises(SheetNotFound):
        adapter(key_file, StubApi(get_result=META)).read_tab("sid", 42)


def test_read_tab_empty_values(key_file):
    tab = adapter(key_file, StubApi(get_result=META, values_result={})).read_tab("sid", 0)
    assert tab.grid == [] and tab.merges == []


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (http_error(403), SheetNotShared),
        (http_error(404), SheetNotFound),
        (http_error(500), SheetsUnavailable),
        (http_error(403, b'{"error": {"status": "PERMISSION_DENIED", "details": [{"reason": "SERVICE_DISABLED"}]}}'), SheetsUnavailable),
        (socket.timeout("timed out"), SheetsUnavailable),
        (TimeoutError(), SheetsUnavailable),
        (ConnectionResetError(), SheetsUnavailable),
    ],
)
def test_error_mapping(key_file, error, expected):
    with pytest.raises(expected) as info:
        adapter(key_file, StubApi(get_result=error)).list_tabs("sid")
    if expected is SheetNotShared:
        assert info.value.service_account_email == "sa@proj.iam.gserviceaccount.com"


def test_quote_tab_title():
    assert quote_tab_title("講義") == "'講義'"
    assert quote_tab_title("It's") == "'It''s'"
