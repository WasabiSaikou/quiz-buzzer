"""parse_spreadsheet_url (FR-002; research R5). Pure: never touches the network."""

import pytest

from quizbuzzer.services.sheets_adapter import InvalidSheetUrl
from quizbuzzer.services.sheets_url import parse_spreadsheet_url

SID = "1AbCdEfGhIjKlMnOp_qr-STuv"
BASE = f"https://docs.google.com/spreadsheets/d/{SID}"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (f"{BASE}/edit", (SID, None)),
        (f"{BASE}/edit#gid=918273645", (SID, 918273645)),
        (f"{BASE}/edit#gid=0", (SID, 0)),
        (f"{BASE}/edit?gid=42", (SID, 42)),
        (f"{BASE}/edit?usp=sharing&gid=42", (SID, 42)),
        (f"{BASE}/edit?usp=sharing#gid=7", (SID, 7)),
        (BASE, (SID, None)),
        (f"{BASE}/", (SID, None)),
        (f"  {BASE}/edit#gid=5 \n", (SID, 5)),
        (f"http://docs.google.com/spreadsheets/d/{SID}/edit", (SID, None)),
        (f"https://docs.google.com/spreadsheets/u/1/d/{SID}/edit", (SID, None)),
    ],
)
def test_accepts_sheets_urls(url, expected):
    assert parse_spreadsheet_url(url) == expected


def test_non_numeric_gid_is_ignored():
    assert parse_spreadsheet_url(f"{BASE}/edit#gid=abc") == (SID, None)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/x",
        f"https://docs.google.com/document/d/{SID}/edit",  # a Docs link, not Sheets
        "https://docs.google.com/spreadsheets/d/",  # missing id
        "https://docs.google.com/spreadsheets/d//edit",
        f"https://evil.example/docs.google.com/spreadsheets/d/{SID}",
        f"ftp://docs.google.com/spreadsheets/d/{SID}",
        "docs.google.com/spreadsheets",
        "",
        "   ",
    ],
)
def test_rejects_non_sheets_urls(url):
    with pytest.raises(InvalidSheetUrl):
        parse_spreadsheet_url(url)


def test_rejects_non_string():
    with pytest.raises(InvalidSheetUrl):
        parse_spreadsheet_url(None)  # type: ignore[arg-type]
