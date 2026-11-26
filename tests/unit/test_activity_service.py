"""ActivityService rules (Principle V test-first): preview (US1), create (US2)."""

from __future__ import annotations

import re
import sqlite3

import pytest

from quizbuzzer import db
from quizbuzzer.models import Phase
from quizbuzzer.services.activity_service import (
    ActivityNotFound,
    ActivityService,
    CurrentActivityExists,
    ImportHasErrors,
    InvalidGroupCount,
    PreviewChanged,
    WarningsNotAcknowledged,
)
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


# --- US2: create_from_import ---------------------------------------------------------------

NO_HEADER_GRID = [["題目", "答案"], ["1", ""]]
WARNING_GRID = [["題號", "作答"], ["1", "答：______"], ["2", ""]]
ISO_UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


class RecordingHub:
    def __init__(self):
        self.messages = []

    def publish_from_thread(self, message):
        self.messages.append(message)


def confirm(service, url=GROUP, sheet_id=0, group_count=6, ack=False):
    p = service.preview_import(url, sheet_id)
    return service.create_from_import(url, sheet_id, group_count, p.fingerprint, ack)


def counts(db_path):
    conn = db.connect(db_path)
    try:
        return tuple(
            conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("activities", "question_units", "answer_slots")
        )
    finally:
        conn.close()


def set_phase(db_path, activity_id, phase):
    conn = db.connect(db_path)
    try:
        conn.execute("UPDATE activities SET phase = ? WHERE id = ?", (phase, activity_id))
    finally:
        conn.close()


@pytest.fixture
def init_db(db_path):
    conn = db.connect(db_path)
    db.init_schema(conn)
    conn.close()


@pytest.fixture
def svc(fake_adapter, db_path, init_db):
    return ActivityService(fake_adapter, db_path)


def test_create_stores_exactly_the_confirmed_preview(svc):
    p = svc.preview_import(GROUP, 0)
    a = svc.create_from_import(GROUP, 0, 6, p.fingerprint, False)

    assert a.phase is Phase.DRAFT
    assert a.group_count == 6
    assert a.title == "template_group – Sheet1"
    assert (a.source_spreadsheet_id, a.source_sheet_id, a.source_tab_title) == (
        "template_group",
        0,
        "Sheet1",
    )
    assert ISO_UTC.match(a.created_at) and a.created_at == a.imported_at
    assert [(u.number, u.kind, u.source_row, u.position) for u in a.units] == [
        (u.number, u.kind, u.source_row, i) for i, u in enumerate(p.units)
    ]
    assert [[(s.sub_part, s.cell_row, s.cell_column, s.a1_ref) for s in u.slots] for u in a.units] == [
        [(s.sub_part, s.row, s.column, s.a1_ref) for s in u.slots] for u in p.units
    ]
    assert svc.get_activity(a.id) == a
    assert svc.get_current_activity() == a


@pytest.mark.parametrize("bad", [1, 13, 0, -4, "6", 6.5, None, True])
def test_invalid_group_count(svc, db_path, bad):
    with pytest.raises(InvalidGroupCount):
        confirm(svc, group_count=bad)
    assert counts(db_path) == (0, 0, 0)


@pytest.mark.parametrize("ok", [2, 12])
def test_group_count_bounds(svc, ok):
    assert confirm(svc, group_count=ok).group_count == ok


def test_import_errors_block_create(svc, fake_adapter, db_path):
    fake_adapter.replace_tab("template_single", 0, NO_HEADER_GRID)
    with pytest.raises(ImportHasErrors) as info:
        confirm(svc, SINGLE)
    assert not info.value.preview.can_confirm
    assert counts(db_path) == (0, 0, 0)


def test_warnings_need_acknowledgement(svc, fake_adapter, db_path):
    fake_adapter.replace_tab("template_single", 0, WARNING_GRID)
    with pytest.raises(WarningsNotAcknowledged):
        confirm(svc, SINGLE, ack=False)
    assert counts(db_path) == (0, 0, 0)
    assert confirm(svc, SINGLE, ack=True).phase is Phase.DRAFT


def test_preview_changed_creates_nothing(svc, fake_adapter, db_path):
    p = svc.preview_import(SINGLE, 0)
    grid = fake_adapter.read_tab("template_single", 0).grid + [["", "7", "新題目"]]
    fake_adapter.replace_tab("template_single", 0, grid)
    with pytest.raises(PreviewChanged) as info:
        svc.create_from_import(SINGLE, 0, 4, p.fingerprint, False)
    assert info.value.preview.total_units == 7
    assert counts(db_path) == (0, 0, 0)


def test_changed_sheet_with_errors_reports_errors_first(svc, fake_adapter, db_path):
    p = svc.preview_import(SINGLE, 0)
    fake_adapter.replace_tab("template_single", 0, NO_HEADER_GRID)
    with pytest.raises(ImportHasErrors):
        svc.create_from_import(SINGLE, 0, 4, p.fingerprint, False)
    assert counts(db_path) == (0, 0, 0)


@pytest.mark.parametrize("phase", ["DRAFT", "OPEN"])
def test_current_activity_blocks_create(svc, db_path, phase):
    first = confirm(svc)
    set_phase(db_path, first.id, phase)
    with pytest.raises(CurrentActivityExists) as info:
        confirm(svc, SINGLE)
    assert (info.value.activity_id, info.value.title, info.value.phase) == (
        first.id,
        first.title,
        Phase(phase),
    )
    assert counts(db_path)[0] == 1


def _rows(db_path, activity_id):
    conn = db.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return (
            [tuple(r) for r in conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,))],
            [
                tuple(r)
                for r in conn.execute(
                    "SELECT * FROM question_units WHERE activity_id = ? ORDER BY id", (activity_id,)
                )
            ],
            [
                tuple(r)
                for r in conn.execute(
                    "SELECT s.* FROM answer_slots s JOIN question_units u ON s.unit_id = u.id "
                    "WHERE u.activity_id = ? ORDER BY s.id",
                    (activity_id,),
                )
            ],
        )
    finally:
        conn.close()


def test_closed_activities_are_kept_unchanged(svc, db_path):
    old = confirm(svc, GROUP)
    set_phase(db_path, old.id, "CLOSED")
    before = _rows(db_path, old.id)
    new = confirm(svc, SINGLE)
    assert new.id != old.id and new.phase is Phase.DRAFT
    assert _rows(db_path, old.id) == before
    assert svc.get_current_activity().id == new.id


def test_create_is_all_or_nothing(svc, db_path, monkeypatch):
    original = db.insert_units_and_slots

    def fail_after_insert(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("disk full")

    monkeypatch.setattr(db, "insert_units_and_slots", fail_after_insert)
    with pytest.raises(RuntimeError):
        confirm(svc)
    assert counts(db_path) == (0, 0, 0)


def test_reads(svc):
    assert svc.get_current_activity() is None
    with pytest.raises(ActivityNotFound):
        svc.get_activity(999)


def test_create_publishes_activity_state(fake_adapter, db_path, init_db):
    hub = RecordingHub()
    svc = ActivityService(fake_adapter, db_path, hub)
    a = confirm(svc)
    assert hub.messages == [
        {
            "type": "activity.state",
            "activity": {
                "id": a.id,
                "title": a.title,
                "phase": "DRAFT",
                "groupCount": 6,
                "totals": {"units": 4, "slots": 6},
                "importedAt": a.imported_at,
            },
        }
    ]


def test_failed_create_publishes_nothing(fake_adapter, db_path, init_db):
    hub = RecordingHub()
    svc = ActivityService(fake_adapter, db_path, hub)
    with pytest.raises(InvalidGroupCount):
        confirm(svc, group_count=1)
    assert hub.messages == []


# --- US3: re-import into a DRAFT activity ---------------------------------------------------

from quizbuzzer.services import activity_service as activity_service_module  # noqa: E402
from quizbuzzer.services.activity_service import ReimportRefused  # noqa: E402

REIMPORT = "https://docs.google.com/spreadsheets/d/reimport/edit"


def numbered_grid(n):
    return [["題號", "作答"]] + [[str(i), ""] for i in range(1, n + 1)]


@pytest.fixture
def reimport_sheet(fake_adapter):
    fake_adapter.add_spreadsheet(
        "reimport",
        "Re-import Book",
        [
            {"sheetId": 0, "title": "Five", "index": 0, "grid": numbered_grid(5)},
            {"sheetId": 5, "title": "Seven", "index": 1, "grid": numbered_grid(7)},
        ],
    )
    return fake_adapter


@pytest.fixture
def clock(monkeypatch):
    times = iter(f"2026-11-26T08:00:0{i}Z" for i in range(10))
    monkeypatch.setattr(activity_service_module, "_utc_now", lambda: next(times))


@pytest.fixture
def draft(svc, reimport_sheet, clock):
    """A DRAFT activity holding 5 single questions from tab 'Five'."""
    return confirm(svc, REIMPORT, 0, group_count=5)


def replace(svc, activity_id, url=REIMPORT, sheet_id=5, ack=False, fingerprint=None):
    if fingerprint is None:
        fingerprint = svc.preview_reimport(activity_id, url, sheet_id).fingerprint
    return svc.replace_questions(activity_id, url, sheet_id, fingerprint, ack)


def ids(db_path, activity_id):
    conn = db.connect(db_path)
    try:
        units = {r[0] for r in conn.execute(
            "SELECT id FROM question_units WHERE activity_id = ?", (activity_id,))}
        slots = {r[0] for r in conn.execute(
            "SELECT s.id FROM answer_slots s JOIN question_units u ON s.unit_id = u.id "
            "WHERE u.activity_id = ?", (activity_id,))}
        return units, slots
    finally:
        conn.close()


def test_reimport_replaces_the_whole_question_set(svc, db_path, draft):
    old_units, old_slots = ids(db_path, draft.id)
    assert len(draft.units) == 5

    updated = replace(svc, draft.id)

    assert [u.number for u in updated.units] == [1, 2, 3, 4, 5, 6, 7]
    new_units, new_slots = ids(db_path, draft.id)
    assert not (new_units & old_units) and not (new_slots & old_slots)
    assert (updated.source_spreadsheet_id, updated.source_sheet_id, updated.source_tab_title) == (
        "reimport",
        5,
        "Seven",
    )
    # FR-025: phase, group count, creation time and title are unchanged; imported_at moves.
    assert updated.phase is Phase.DRAFT and updated.group_count == 5
    assert updated.created_at == draft.created_at and updated.title == draft.title
    assert updated.imported_at > draft.imported_at
    assert svc.get_activity(draft.id) == updated


def test_check_reimport_allowed_for_draft(svc, draft):
    assert svc.check_reimport_allowed(draft.id).id == draft.id


@pytest.mark.parametrize("phase", ["OPEN", "CLOSED"])
def test_reimport_refused_when_not_draft(svc, db_path, draft, phase):
    set_phase(db_path, draft.id, phase)
    before = svc.get_activity(draft.id).units
    fp = svc.preview_import(REIMPORT, 5).fingerprint
    for call in (
        lambda: svc.check_reimport_allowed(draft.id),
        lambda: svc.preview_reimport(draft.id, REIMPORT, 5),
        lambda: svc.replace_questions(draft.id, REIMPORT, 5, fp, False),
    ):
        with pytest.raises(ReimportRefused) as info:
            call()
        assert info.value.phase is Phase(phase)
    assert svc.get_activity(draft.id).units == before


def test_reimport_rechecks_phase_at_confirm(svc, db_path, draft):
    p = svc.preview_reimport(draft.id, REIMPORT, 5)
    set_phase(db_path, draft.id, "OPEN")  # opened after the preview was shown (US3 AS4)
    with pytest.raises(ReimportRefused):
        svc.replace_questions(draft.id, REIMPORT, 5, p.fingerprint, False)
    assert len(svc.get_activity(draft.id).units) == 5


def test_reimport_preview_changed(svc, reimport_sheet, draft):
    p = svc.preview_reimport(draft.id, REIMPORT, 5)
    reimport_sheet.replace_tab("reimport", 5, numbered_grid(8))
    with pytest.raises(PreviewChanged):
        svc.replace_questions(draft.id, REIMPORT, 5, p.fingerprint, False)
    assert len(svc.get_activity(draft.id).units) == 5


def test_reimport_import_errors(svc, reimport_sheet, draft):
    reimport_sheet.replace_tab("reimport", 5, NO_HEADER_GRID)
    with pytest.raises(ImportHasErrors):
        replace(svc, draft.id)
    assert len(svc.get_activity(draft.id).units) == 5


def test_reimport_warnings_need_acknowledgement(svc, reimport_sheet, draft):
    reimport_sheet.replace_tab("reimport", 5, WARNING_GRID)
    with pytest.raises(WarningsNotAcknowledged):
        replace(svc, draft.id, ack=False)
    assert len(svc.get_activity(draft.id).units) == 5
    assert [u.number for u in replace(svc, draft.id, ack=True).units] == [1, 2]


def test_reimport_is_all_or_nothing(svc, db_path, draft, monkeypatch):
    before = svc.get_activity(draft.id)
    original = db.insert_units_and_slots

    def fail_after_insert(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("disk full")

    p = svc.preview_reimport(draft.id, REIMPORT, 5)
    monkeypatch.setattr(db, "insert_units_and_slots", fail_after_insert)
    with pytest.raises(RuntimeError):
        svc.replace_questions(draft.id, REIMPORT, 5, p.fingerprint, False)
    assert svc.get_activity(draft.id) == before


def test_reimport_unknown_activity(svc, reimport_sheet):
    with pytest.raises(ActivityNotFound):
        svc.preview_reimport(999, REIMPORT, 5)
    fp = svc.preview_import(REIMPORT, 5).fingerprint
    with pytest.raises(ActivityNotFound):
        svc.replace_questions(999, REIMPORT, 5, fp, False)


def test_reimport_publishes_activity_state(fake_adapter, db_path, init_db, reimport_sheet, clock):
    hub = RecordingHub()
    svc = ActivityService(fake_adapter, db_path, hub)
    a = confirm(svc, REIMPORT, 0)
    hub.messages.clear()
    updated = replace(svc, a.id)
    assert [m["activity"]["totals"] for m in hub.messages] == [{"units": 7, "slots": 7}]
    assert hub.messages[0]["activity"]["importedAt"] == updated.imported_at


def test_refused_reimport_publishes_nothing(fake_adapter, db_path, init_db, reimport_sheet, clock):
    hub = RecordingHub()
    svc = ActivityService(fake_adapter, db_path, hub)
    a = confirm(svc, REIMPORT, 0)
    hub.messages.clear()
    set_phase(db_path, a.id, "CLOSED")
    fp = svc.preview_import(REIMPORT, 5).fingerprint
    with pytest.raises(ReimportRefused):
        svc.replace_questions(a.id, REIMPORT, 5, fp, False)
    assert hub.messages == []
