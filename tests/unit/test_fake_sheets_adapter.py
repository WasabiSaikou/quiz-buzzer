"""FakeSheetsAdapter behaves like a read-only SheetsAdapter (research R9, FR-005)."""

import pytest

from quizbuzzer.services.sheets_adapter import (
    SheetNotFound,
    SheetNotShared,
    SheetsAdapter,
    SheetsUnavailable,
)
from tests.fakes.fake_sheets_adapter import FakeSheetsAdapter


def test_is_a_sheets_adapter(fake_adapter):
    assert isinstance(fake_adapter, SheetsAdapter)


@pytest.mark.parametrize("stem", ["template_single", "template_group"])
def test_loads_csv_templates_as_single_tab(fake_adapter, stem):
    info = fake_adapter.list_tabs(stem)
    assert info.title == stem
    assert [(t.sheet_id, t.title, t.index) for t in info.tabs] == [(0, "Sheet1", 0)]
    tab = fake_adapter.read_tab(stem, 0)
    assert tab.spreadsheet_title == stem and tab.title == "Sheet1" and tab.merges == []
    assert tab.grid[3][1] == "題號" and tab.grid[3][6] == "作答"  # header at row 4 (B, G)


def test_expected_files_are_not_loaded_as_sheets(fake_adapter):
    assert not any(sid.endswith(".expected") for sid in fake_adapter.spreadsheet_ids)


def test_unknown_spreadsheet_and_tab_raise_not_found(fake_adapter):
    with pytest.raises(SheetNotFound):
        fake_adapter.list_tabs("nope")
    with pytest.raises(SheetNotFound):
        fake_adapter.read_tab("template_single", 12345)


def test_json_spreadsheet_and_tab_order():
    fake = FakeSheetsAdapter(fixtures_dir=None)
    fake.add_spreadsheet(
        "sid",
        "Ch3",
        [
            {"sheetId": 9, "title": "練習", "index": 1, "grid": [["a"]], "merges": [[0, 2, 0, 1]]},
            {"sheetId": 0, "title": "講義", "index": 0, "grid": [["b", None]]},
        ],
    )
    assert [t.title for t in fake.list_tabs("sid").tabs] == ["講義", "練習"]
    assert fake.read_tab("sid", 9).merges == [(0, 2, 0, 1)]
    assert fake.read_tab("sid", 0).grid == [["b", ""]]


@pytest.mark.parametrize(
    "exc", [SheetNotShared("sa@example.com"), SheetNotFound("x"), SheetsUnavailable("x")]
)
def test_fail_with(fake_adapter, exc):
    fake_adapter.fail_with(exc)
    with pytest.raises(type(exc)):
        fake_adapter.list_tabs("template_single")
    fake_adapter.fail_with(None)
    fake_adapter.list_tabs("template_single")


def test_returned_data_cannot_modify_fixtures(fake_adapter):
    before = fake_adapter.snapshot()
    tab = fake_adapter.read_tab("template_group", 0)
    tab.grid[4][6] = "changed"
    tab.grid.append(["extra"])
    assert fake_adapter.snapshot() == before


def test_replace_tab_and_call_log(fake_adapter):
    fake_adapter.replace_tab("template_single", 0, [["題號", "作答"], ["1", ""]])
    assert fake_adapter.read_tab("template_single", 0).grid == [["題號", "作答"], ["1", ""]]
    assert fake_adapter.calls[-1] == ("read_tab", ("template_single", 0))


# --- Feature 003: the fake also acts as the SheetsWriter (003 research R9, T003) -----------

from quizbuzzer.models import CellWrite  # noqa: E402
from quizbuzzer.services.sheets_adapter import SheetReadOnly, SheetsWriter  # noqa: E402


def _one_tab(fake: FakeSheetsAdapter) -> None:
    fake.add_spreadsheet(
        "w", "W", [{"sheetId": 5, "title": "Tab", "index": 0, "grid": [["題號", "作答"], ["1"]]}]
    )


def test_is_a_sheets_writer(fake_adapter):
    assert isinstance(fake_adapter, SheetsWriter)


def test_write_cells_stores_text_verbatim_and_grows_rows():
    fake = FakeSheetsAdapter(None)
    _one_tab(fake)
    n = fake.write_cells("w", 5, "Tab", [CellWrite("B2", "=1+1"), CellWrite("D4", "（2）a,b")])
    assert n == 2
    grid = fake.read_tab("w", 5).grid
    assert grid[1][1] == "=1+1"
    assert grid[3][3] == "（2）a,b"
    assert grid[0] == ["題號", "作答"]


def test_write_cells_logs_one_entry_per_call():
    fake = FakeSheetsAdapter(None)
    _one_tab(fake)
    cells = [CellWrite("B2", "x"), CellWrite("B3", "y")]
    fake.write_cells("w", 5, "Tab", cells)
    assert fake.writes == [("w", 5, "Tab", tuple(cells))]


def test_write_cells_unknown_tab_raises_not_found():
    fake = FakeSheetsAdapter(None)
    _one_tab(fake)
    with pytest.raises(SheetNotFound):
        fake.write_cells("w", 99, "Tab", [CellWrite("A1", "x")])


def test_read_only_share_refuses_writes_but_allows_reads():
    fake = FakeSheetsAdapter(None)
    _one_tab(fake)
    fake.make_read_only("w")
    before = fake.snapshot()
    with pytest.raises(SheetReadOnly) as info:
        fake.write_cells("w", 5, "Tab", [CellWrite("B2", "x")])
    assert info.value.service_account_email == fake.service_account_email
    assert fake.read_tab("w", 5).grid[0] == ["題號", "作答"]
    assert fake.snapshot() == before
    assert fake.writes == []


def test_fail_with_also_applies_to_writes():
    fake = FakeSheetsAdapter(None)
    _one_tab(fake)
    fake.fail_with(SheetsUnavailable("down"))
    with pytest.raises(SheetsUnavailable):
        fake.write_cells("w", 5, "Tab", [CellWrite("B2", "x")])
    fake.fail_with(None)
    assert fake.writes == []
