"""ActivityService rules (Principle V test-first): preview (US1), create (US2)."""

from __future__ import annotations

import pytest

from quizbuzzer.services.activity_service import ActivityService
from quizbuzzer.services.guided_notes_parser import compute_fingerprint, parse
from quizbuzzer.services.sheets_adapter import (
    InvalidSheetUrl,
    SheetNotFound,
    SheetNotShared,
    SheetsUnavailable,
)

SHIFTED = "https://docs.google.com/spreadsheets/d/shifted_layout/edit"
SINGLE = "https://docs.google.com/spreadsheets/d/template_single/edit"
GROUP = "https://docs.google.com/spreadsheets/d/template_group/edit"


@pytest.fixture
def service(fake_adapter, db_path):
    return ActivityService(fake_adapter, db_path)


# --- US1: list_tabs / preview_import ------------------------------------------------------


def test_list_tabs_preselects_first_tab_without_gid(service):
    info = service.list_tabs(SHIFTED)
    assert [t.title for t in info.tabs] == ["講義", "練習"]
    assert info.requested_gid is None
    assert info.preselected_sheet_id == 0


def test_list_tabs_preselects_gid_tab(service):
    info = service.list_tabs(SHIFTED + "#gid=918273645")
    assert info.requested_gid == 918273645
    assert info.preselected_sheet_id == 918273645


def test_list_tabs_unknown_gid_falls_back_to_first(service):
    assert service.list_tabs(SHIFTED + "#gid=555").preselected_sheet_id == 0


def test_preview_import_adds_identity_and_fingerprint(service, fake_adapter):
    preview = service.preview_import(SHIFTED, 918273645)
    tab = fake_adapter.read_tab("shifted_layout", 918273645)
    assert (preview.spreadsheet_id, preview.sheet_id) == ("shifted_layout", 918273645)
    assert (preview.spreadsheet_title, preview.tab_title) == ("Shifted Layout 測試", "練習")
    assert preview.units == parse(tab.grid, tab.merges).units
    assert preview.fingerprint == compute_fingerprint("shifted_layout", 918273645, preview.units)


def test_adapter_gets_spreadsheet_id_not_url(service, fake_adapter):
    service.list_tabs(SHIFTED)
    service.preview_import(SHIFTED + "#gid=0", 0)
    assert fake_adapter.calls == [
        ("list_tabs", ("shifted_layout",)),
        ("read_tab", ("shifted_layout", 0)),
    ]


@pytest.mark.parametrize("call", ["list_tabs", "preview_import"])
def test_invalid_url_never_reaches_adapter(service, fake_adapter, call):
    with pytest.raises(InvalidSheetUrl):
        if call == "list_tabs":
            service.list_tabs("https://example.com/x")
        else:
            service.preview_import("https://example.com/x", 0)
    assert fake_adapter.calls == []


def test_unknown_sheet_id_raises_not_found(service):
    with pytest.raises(SheetNotFound):
        service.preview_import(SINGLE, 12345)


@pytest.mark.parametrize(
    "exc", [SheetNotShared("sa@example.com"), SheetNotFound("x"), SheetsUnavailable("x")]
)
def test_adapter_errors_propagate(service, fake_adapter, exc):
    fake_adapter.fail_with(exc)
    with pytest.raises(type(exc)):
        service.list_tabs(SINGLE)
    with pytest.raises(type(exc)):
        service.preview_import(SINGLE, 0)


def test_preview_is_read_only(service, fake_adapter):
    before = fake_adapter.snapshot()
    service.list_tabs(SHIFTED)
    service.preview_import(SHIFTED, 918273645)
    service.preview_import(GROUP, 0)
    assert fake_adapter.snapshot() == before
