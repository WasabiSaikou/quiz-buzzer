"""Sheet export, tests first (003 T014 – T017; research R1 – R4; Constitution II, V).

- `format_cell`: single vs 題組 text.
- `plan_export` (pure): slot re-location on 3 differently shaped sheets, each also with rows
  inserted above / between questions and a column inserted, and the abort path.
- `SheetExporter.export` with FakeSheetsAdapter as both reader and writer: nothing is written on
  any failure; one write call on success.

Expected cells are derived from the ORIGINAL slot address plus the known shift of each edit, never
by re-running the parser, so the parser cannot confirm its own answer.
"""

from __future__ import annotations

import copy
import re

import pytest

from quizbuzzer.models import (
    Activity,
    AnswerSlot,
    CellWrite,
    Phase,
    QuestionUnit,
    Submission,
    SubmissionAnswer,
    UnitKind,
)
from quizbuzzer.services import guided_notes_parser
from quizbuzzer.services.activity_service import ActivityNotFound, PhaseConflict
from quizbuzzer.services.results_service import ResultsService, build_results
from quizbuzzer.services.sheet_exporter import (
    ExportBlocked,
    ExportNotShared,
    SheetExporter,
    format_cell,
    plan_export,
)
from quizbuzzer.services.sheets_adapter import (
    SheetNotFound,
    SheetNotShared,
    SheetReadOnly,
    SheetsUnavailable,
)
from tests.fakes.fake_sheets_adapter import FakeSheetsAdapter
from tests.live_helpers import run_sheet_activity

# --- T014: format_cell ------------------------------------------------------------------------


def test_single_question_cell_is_the_answer_itself():
    assert format_cell(UnitKind.SINGLE, 1, "光合作用") == "光合作用"


@pytest.mark.parametrize("k", [1, 2, 3, 10])
def test_group_set_cell_is_fullwidth_marker_plus_answer(k):
    text = format_cell(UnitKind.GROUP_SET, k, "葉綠體")
    assert text == f"（{k}）葉綠體"
    assert text.startswith("（") and f"{k}）" in text  # half-width digits, full-width parens


@pytest.mark.parametrize("answer", ["=1+1", "a,b", 'say "hi"', "line1\nline2", "@x", "+1", "-1"])
@pytest.mark.parametrize("kind", [UnitKind.SINGLE, UnitKind.GROUP_SET])
def test_answer_text_is_kept_verbatim(kind, answer):
    assert format_cell(kind, 2, answer).endswith(answer)


# --- helpers for plan_export ------------------------------------------------------------------

FAKE = FakeSheetsAdapter()
SHAPES = {
    # name: (spreadsheet_id, sheet_id, winning unit numbers)
    "template_single": ("template_single", 0, {1, 2, 3, 5, 6}),
    "template_group": ("template_group", 0, {1, 3}),
    "shifted_layout": ("shifted_layout", 918273645, {1, 2, 4, 5, 6}),
}


def tab(name):
    sid, sheet_id, _ = SHAPES[name]
    t = FAKE.read_tab(sid, sheet_id)
    return copy.deepcopy(t.grid), [tuple(m) for m in t.merges]


def activity_from(grid, merges, *, activity_id=1):
    """The activity exactly as import stores it (from the original grid)."""
    preview = guided_notes_parser.parse(grid, merges)
    assert not preview.errors
    units, slot_id = [], 100
    for pos, u in enumerate(preview.units):
        slots = []
        for s in u.slots:
            slot_id += 1
            slots.append(AnswerSlot(id=slot_id, sub_part=s.sub_part, cell_row=s.row,
                                    cell_column=s.column, a1_ref=s.a1_ref))
        units.append(QuestionUnit(id=10 + pos, number=u.number, kind=u.kind,
                                  source_row=u.source_row, position=pos, slots=tuple(slots)))
    return Activity(id=activity_id, title="T", phase=Phase.CLOSED, group_count=6,
                    source_spreadsheet_id="sid", source_sheet_id=0, source_tab_title="Tab",
                    created_at="x", imported_at="x", units=tuple(units))


def results_with_winners(activity, numbers):
    subs, sid = [], 0
    for u in activity.units:
        if u.number not in numbers:
            continue
        sid += 1
        subs.append(Submission(
            id=sid, unit_id=u.id, unit_number=u.number, group_number=2, participant_id=1,
            submitted_by="名", rank=1, received_at="2026-11-27T02:00:00.000Z",
            answers=tuple(SubmissionAnswer(slot_id=s.id, sub_part=s.sub_part,
                                           text=f"ans-{u.number}-{s.sub_part}") for s in u.slots),
        ))
        # a second, losing submission must never be written
        sid += 1
        subs.append(Submission(
            id=sid, unit_id=u.id, unit_number=u.number, group_number=3, participant_id=2,
            submitted_by="名", rank=2, received_at="2026-11-27T02:00:01.000Z",
            answers=tuple(SubmissionAnswer(slot_id=s.id, sub_part=s.sub_part, text="LOSER")
                          for s in u.slots),
        ))
    return build_results(activity, subs)


A1 = re.compile(r"^([A-Z]+)([0-9]+)$")


def shift(a1, rows=0, cols=0, from_row=1):
    m = A1.match(a1)
    col = 0
    for ch in m.group(1):
        col = col * 26 + ord(ch) - 64
    row = int(m.group(2))
    if row >= from_row:
        row += rows
    col += cols
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row}"


def insert_rows(grid, merges, at, n=1):
    """Insert n empty rows before 0-based row `at`; merges move or grow like in Sheets."""
    grid = grid[:at] + [[] for _ in range(n)] + grid[at:]
    out = []
    for r0, r1, c0, c1 in merges:
        if r0 >= at:
            out.append((r0 + n, r1 + n, c0, c1))
        elif r1 > at:
            out.append((r0, r1 + n, c0, c1))
        else:
            out.append((r0, r1, c0, c1))
    return grid, out


def insert_first_column(grid, merges):
    return [[""] + list(row) for row in grid], [(r0, r1, c0 + 1, c1 + 1) for r0, r1, c0, c1 in merges]


def expected_writes(activity, numbers, rename=lambda a1: a1):
    out = []
    for u in activity.units:
        if u.number not in numbers:
            continue
        for s in u.slots:
            text = f"ans-{u.number}-{s.sub_part}"
            out.append(CellWrite(rename(s.a1_ref), format_cell(u.kind, s.sub_part, text)))
    return out


def second_question_row(activity):
    return activity.units[1].source_row  # 1-based row of the 2nd numbered row


# --- T015: re-location on >= 3 shapes (Principle II) ---------------------------------------


@pytest.mark.parametrize("shape", list(SHAPES))
def test_unchanged_sheet_writes_winning_slots_only(shape):
    grid, merges = tab(shape)
    activity = activity_from(grid, merges)
    numbers = SHAPES[shape][2]
    writes = plan_export(activity, results_with_winners(activity, numbers),
                         guided_notes_parser.parse(grid, merges))
    assert writes == expected_writes(activity, numbers)
    assert all("LOSER" not in w.text for w in writes)


@pytest.mark.parametrize("shape", list(SHAPES))
def test_rows_inserted_above_header_move_every_target(shape):
    grid, merges = tab(shape)
    activity = activity_from(grid, merges)
    numbers = SHAPES[shape][2]
    new_grid, new_merges = insert_rows(grid, merges, 0, 2)
    writes = plan_export(activity, results_with_winners(activity, numbers),
                         guided_notes_parser.parse(new_grid, new_merges))
    assert writes == expected_writes(activity, numbers, lambda a1: shift(a1, rows=2))
    stored = [w.a1_ref for w in expected_writes(activity, numbers)]  # same order as writes
    assert all(new != old for new, old in zip((w.a1_ref for w in writes), stored, strict=True))


@pytest.mark.parametrize("shape", list(SHAPES))
def test_blank_row_inserted_between_questions(shape):
    grid, merges = tab(shape)
    activity = activity_from(grid, merges)
    numbers = SHAPES[shape][2]
    q2 = second_question_row(activity)
    new_grid, new_merges = insert_rows(grid, merges, q2 - 1, 1)
    writes = plan_export(activity, results_with_winners(activity, numbers),
                         guided_notes_parser.parse(new_grid, new_merges))
    assert writes == expected_writes(activity, numbers, lambda a1: shift(a1, rows=1, from_row=q2))


@pytest.mark.parametrize("shape", list(SHAPES))
def test_column_inserted_left_of_the_answer_column(shape):
    grid, merges = tab(shape)
    activity = activity_from(grid, merges)
    numbers = SHAPES[shape][2]
    new_grid, new_merges = insert_first_column(grid, merges)
    writes = plan_export(activity, results_with_winners(activity, numbers),
                         guided_notes_parser.parse(new_grid, new_merges))
    assert writes == expected_writes(activity, numbers, lambda a1: shift(a1, cols=1))


def test_sub_part_added_after_import_is_ignored():
    grid, merges = tab("template_group")
    activity = activity_from(grid, merges)
    grid[6][6] = "（3）"  # spacer row after question 1 becomes a new sub-part 3
    writes = plan_export(activity, results_with_winners(activity, {1}),
                         guided_notes_parser.parse(grid, merges))
    assert [w.a1_ref for w in writes] == ["G5", "G6"]


def test_single_that_became_group_set_still_writes_plain_text_to_sub_part_1():
    grid, merges = tab("template_single")
    activity = activity_from(grid, merges)
    grid[4][6] = "（1）"
    grid[5][6] = "（2）"  # question 1 is now a 題組 in the sheet
    writes = plan_export(activity, results_with_winners(activity, {1}),
                         guided_notes_parser.parse(grid, merges))
    assert writes == [CellWrite("G5", "ans-1-1")]


def test_no_winners_means_no_writes():
    grid, merges = tab("template_group")
    activity = activity_from(grid, merges)
    assert plan_export(activity, results_with_winners(activity, set()),
                       guided_notes_parser.parse(grid, merges)) == []


# --- T016: the abort path -------------------------------------------------------------------


def blocked(activity, numbers, grid, merges):
    with pytest.raises(ExportBlocked) as info:
        plan_export(activity, results_with_winners(activity, numbers),
                    guided_notes_parser.parse(grid, merges))
    return info.value.problems


def test_parse_error_in_reread_blocks_with_every_error_listed():
    grid, merges = tab("template_single")
    activity = activity_from(grid, merges)
    grid[6][1] = "1"  # question 2 renumbered to 1: duplicate number
    preview = guided_notes_parser.parse(grid, merges)
    assert preview.errors
    problems = blocked(activity, {1, 2}, grid, merges)
    assert [p.kind for p in problems] == ["parse_error"] * len(preview.errors)
    assert [p.code for p in problems] == [e.code for e in preview.errors]
    assert all(p.message for p in problems)


def test_missing_header_blocks():
    grid, merges = tab("template_group")
    activity = activity_from(grid, merges)
    grid[3][1] = "編號"  # header label 題號 gone
    problems = blocked(activity, {1}, grid, merges)
    assert problems and {p.kind for p in problems} == {"parse_error"}


def test_deleted_winning_question_is_missing_question():
    grid, merges = tab("template_single")
    activity = activity_from(grid, merges)
    del grid[8]  # question 3's row
    problems = blocked(activity, {3}, grid, merges)
    assert [(p.kind, p.question_number, p.sub_part) for p in problems] == [("missing_question", 3, None)]
    assert "3" in problems[0].message


def test_deleted_winning_sub_part_is_missing_sub_part():
    grid, merges = tab("template_group")
    activity = activity_from(grid, merges)
    del grid[5]  # question 1 sub-part 2
    problems = blocked(activity, {1}, grid, merges)
    assert [(p.kind, p.question_number, p.sub_part) for p in problems] == [("missing_sub_part", 1, 2)]


def test_every_problem_is_listed():
    grid, merges = tab("template_group")
    activity = activity_from(grid, merges)
    del grid[10]  # question 3 (single)
    del grid[5]  # question 1 sub-part 2
    problems = blocked(activity, {1, 3}, grid, merges)
    assert [(p.kind, p.question_number, p.sub_part) for p in problems] == [
        ("missing_sub_part", 1, 2),
        ("missing_question", 3, None),
    ]


def test_deleted_question_without_winner_does_not_block():
    grid, merges = tab("template_single")
    activity = activity_from(grid, merges)
    del grid[10]  # question 4 has no winner; its number gap is only a warning
    preview = guided_notes_parser.parse(grid, merges)
    assert preview.warnings and not preview.errors
    writes = plan_export(activity, results_with_winners(activity, {1, 2, 3, 5, 6}), preview)
    assert [w.a1_ref for w in writes] == ["G5", "G7", "G9", "G12", "G14"]


# --- T017: SheetExporter.export with the fake (nothing written on failure) -----------------

GROUP = "template_group"
PLAYS = [(1, 2), (1, 4), (3, 5, ["=1+1"])]  # unit 1 (題組) won by 2, unit 3 won by 5; 2, 4 none


@pytest.fixture
def fake():
    return FakeSheetsAdapter()


@pytest.fixture
def closed(fake, db_path):
    return run_sheet_activity(fake, db_path, GROUP, 0, PLAYS)


def exporter(fake, db_path):
    return SheetExporter(fake, fake, ResultsService(db_path))


def test_export_writes_once_with_all_cells_and_reports_counts(fake, db_path, closed):
    report = exporter(fake, db_path).export(closed.id)
    assert (report.cells_written, report.units_written, report.units_skipped) == (3, 2, 2)
    assert len(fake.writes) == 1
    sid, sheet_id, title, cells = fake.writes[0]
    assert (sid, sheet_id, title) == (GROUP, 0, "Sheet1")
    assert cells == (
        CellWrite("G5", "（1）ans-1-1"),
        CellWrite("G6", "（2）ans-1-2"),
        CellWrite("G11", "=1+1"),
    )
    grid = fake.read_tab(GROUP, 0).grid
    assert grid[10][6] == "=1+1" and grid[4][6] == "（1）ans-1-1"
    assert grid[7][6] == "（1）" and grid[12][6] == ""  # unanswered units untouched


def test_export_after_rows_inserted_and_tab_renamed(fake, db_path, closed):
    grid, _ = insert_rows(fake.read_tab(GROUP, 0).grid, [], 0, 2)
    fake.replace_tab(GROUP, 0, grid)
    fake.rename_tab(GROUP, 0, "改名後")
    exporter(fake, db_path).export(closed.id)
    _, _, title, cells = fake.writes[0]
    assert title == "改名後"
    assert [c.a1_ref for c in cells] == ["G7", "G8", "G13"]


def test_repeated_export_writes_the_same_cells(fake, db_path, closed):
    first = exporter(fake, db_path).export(closed.id)
    second = exporter(fake, db_path).export(closed.id)
    assert first == second
    assert fake.writes[0][3] == fake.writes[1][3]


def assert_nothing_written(fake, before):
    assert fake.writes == []
    assert fake.snapshot() == before


def test_blocked_export_writes_nothing(fake, db_path, closed):
    grid = fake.read_tab(GROUP, 0).grid
    del grid[5]  # unit 1 sub-part 2
    fake.replace_tab(GROUP, 0, grid)
    before = fake.snapshot()
    with pytest.raises(ExportBlocked) as info:
        exporter(fake, db_path).export(closed.id)
    assert [(p.kind, p.question_number, p.sub_part) for p in info.value.problems] == [
        ("missing_sub_part", 1, 2)
    ]
    assert_nothing_written(fake, before)


def test_view_only_share_writes_nothing(fake, db_path, closed):
    fake.make_read_only(GROUP)
    before = fake.snapshot()
    with pytest.raises(SheetReadOnly) as info:
        exporter(fake, db_path).export(closed.id)
    assert info.value.service_account_email == fake.service_account_email
    assert_nothing_written(fake, before)


def test_not_shared_becomes_export_not_shared_naming_the_email(fake, db_path, closed):
    before = fake.snapshot()
    fake.fail_with(SheetNotShared(fake.service_account_email))
    with pytest.raises(ExportNotShared) as info:
        exporter(fake, db_path).export(closed.id)
    fake.fail_with(None)
    assert info.value.service_account_email == fake.service_account_email
    assert "Editor" in str(info.value)
    assert_nothing_written(fake, before)


def test_deleted_tab_writes_nothing(fake, db_path, closed):
    fake.delete_tab(GROUP, 0)
    before = fake.snapshot()
    with pytest.raises(SheetNotFound):
        exporter(fake, db_path).export(closed.id)
    assert_nothing_written(fake, before)


def test_google_unavailable_writes_nothing(fake, db_path, closed):
    before = fake.snapshot()
    fake.fail_with(SheetsUnavailable("down"))
    with pytest.raises(SheetsUnavailable):
        exporter(fake, db_path).export(closed.id)
    fake.fail_with(None)
    assert_nothing_written(fake, before)


def test_zero_winners_makes_no_google_call(fake, db_path):
    activity = run_sheet_activity(fake, db_path, GROUP, 0, [])
    fake.calls.clear()
    report = exporter(fake, db_path).export(activity.id)
    assert (report.cells_written, report.units_written, report.units_skipped) == (0, 0, 4)
    assert fake.calls == [] and fake.writes == []


@pytest.mark.parametrize("phase", ["DRAFT", "OPEN"])
def test_export_refused_before_closed_without_google_call(fake, db_path, phase):
    activity = run_sheet_activity(fake, db_path, GROUP, 0, [], final_phase=phase)
    fake.calls.clear()
    with pytest.raises(PhaseConflict) as info:
        exporter(fake, db_path).export(activity.id)
    assert info.value.action == "export"
    assert fake.calls == [] and fake.writes == []


def test_unknown_activity(fake, db_path, closed):
    with pytest.raises(ActivityNotFound):
        exporter(fake, db_path).export(closed.id + 99)
