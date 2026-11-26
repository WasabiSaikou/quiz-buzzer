"""guided_notes_parser.parse (Principle II; FR-006–FR-018; research R2–R4).

Reference sheets: template_single.csv, template_group.csv, shifted_layout.json (3 shapes).
Edge cases: tests/fixtures/sheets/edge_cases/*.json.
"""

from __future__ import annotations

import copy
import json

import pytest

from quizbuzzer.models import UnitKind
from quizbuzzer.services.guided_notes_parser import parse, to_a1
from tests.fakes.fake_sheets_adapter import FIXTURES_DIR, FakeSheetsAdapter

REFERENCE_SHEETS = ["template_single", "template_group", "shifted_layout"]


def summarize(preview):
    return [(u.number, u.kind.value, [s.a1_ref for s in u.slots]) for u in preview.units]


def issues_of(preview):
    return sorted((i.severity, i.code, tuple(i.cells), tuple(i.rows)) for i in preview.issues)


# --- Reference sheets (SC-002) ----------------------------------------------------------


@pytest.mark.parametrize("stem", REFERENCE_SHEETS)
def test_reference_sheet_matches_expected(stem):
    expected = json.loads((FIXTURES_DIR / f"{stem}.expected.json").read_text(encoding="utf-8"))
    tab = FakeSheetsAdapter(FIXTURES_DIR).read_tab(stem, expected["sheetId"])

    preview = parse(tab.grid, tab.merges)

    h = expected["header"]
    assert (preview.header.row, preview.header.number_column, preview.header.answer_column) == (
        h["row"],
        h["numberColumn"],
        h["answerColumn"],
    )
    got = [
        {
            "number": u.number,
            "kind": u.kind.value,
            "sourceRow": u.source_row,
            "slots": [{"subPart": s.sub_part, "a1Ref": s.a1_ref} for s in u.slots],
        }
        for u in preview.units
    ]
    assert got == expected["units"]
    assert (preview.total_units, preview.total_slots) == (
        expected["totals"]["units"],
        expected["totals"]["slots"],
    )
    assert sorted(i.code for i in preview.issues) == sorted(expected["issueCodes"])
    assert preview.can_confirm


def test_no_fixed_addresses_shifted_grid_gives_shifted_cells():
    """FR-007: the same sheet moved by +3 rows and +2 columns parses identically, shifted."""
    tab = FakeSheetsAdapter(FIXTURES_DIR).read_tab("template_group", 0)
    shifted = [[] for _ in range(3)] + [["", ""] + row for row in tab.grid]

    a, b = parse(tab.grid, []), parse(shifted, [])

    assert (b.header.row, b.header.number_column, b.header.answer_column) == (
        a.header.row + 3,
        a.header.number_column + 2,
        a.header.answer_column + 2,
    )
    for ua, ub in zip(a.units, b.units, strict=True):
        assert (ub.number, ub.kind, ub.source_row) == (ua.number, ua.kind, ua.source_row + 3)
        assert [(s.sub_part, s.row, s.column) for s in ub.slots] == [
            (s.sub_part, s.row + 3, s.column + 2) for s in ua.slots
        ]


def test_parse_is_pure_and_does_not_modify_input():
    tab = FakeSheetsAdapter(FIXTURES_DIR).read_tab("shifted_layout", 918273645)
    grid, merges = copy.deepcopy(tab.grid), list(tab.merges)
    parse(grid, merges)
    assert grid == tab.grid and merges == tab.merges


# --- Edge cases ---------------------------------------------------------------------------

S, G = "SINGLE", "GROUP_SET"

EDGE_CASES = {
    # name: (units [(number, kind, [a1...])], issues [(severity, code, cells, rows)])
    "no_header": ([], [("error", "header_not_found", (), ())]),
    "header_whitespace": ([(1, S, ["D2"])], []),
    "header_whitespace_space": ([(1, S, ["B2"])], []),
    "header_extra_chars": ([], [("error", "header_not_found", (), ())]),
    "header_split_rows": ([], [("error", "header_not_found", ("A1", "B2"), (1, 2))]),
    "header_duplicate_label": ([], [("error", "header_ambiguous", ("B1", "C1"), (1,))]),
    "header_topmost_wins": (
        [(1, S, ["B3"]), (2, S, ["B5"])],
        [
            ("warning", "stray_answer_text", ("B4",), (4,)),
            ("warning", "unrecognised_question_number", ("A4",), (4,)),
        ],
    ),
    "duplicate_numbers": (
        [(1, S, ["B2"]), (2, S, ["B3"]), (2, S, ["B4"])],
        [("error", "duplicate_question_number", ("A3", "A4"), (3, 4))],
    ),
    "number_gap": (
        [(1, S, ["B2"]), (2, S, ["B3"]), (4, S, ["B4"])],
        [("warning", "question_number_gap", (), ())],
    ),
    "numbers_out_of_order": (
        [(1, S, ["B2"]), (3, S, ["B3"]), (2, S, ["B4"])],
        [("warning", "question_number_out_of_order", ("A4",), (4,))],
    ),
    "unrecognised_numbers": (
        [(1, S, ["B2"]), (2, S, ["B8"])],
        [("warning", "unrecognised_question_number", (f"A{r}",), (r,)) for r in range(3, 8)],
    ),
    "number_forms": ([(n, S, [f"B{n + 1}"]) for n in range(1, 9)], []),
    "fullwidth_q_and_dot": ([(1, S, ["B2"]), (2, S, ["B3"])], []),
    "zero_questions": ([], [("error", "no_questions", (), ())]),
    "stray_answer_text": (
        [(1, G, ["B2", "B4"])],
        [("warning", "stray_answer_text", ("B3",), (3,))],
    ),
    "slot_cell_has_text": (
        [(1, S, ["B2"]), (2, S, ["B3"]), (3, G, ["B4", "B5"]), (4, S, ["B6"])],
        [
            ("warning", "slot_cell_has_text", ("B2",), (2,)),
            ("warning", "slot_cell_has_text", ("B3",), (3,)),
            ("warning", "slot_cell_has_text", ("B5",), (5,)),
        ],
    ),
    "duplicate_sub_part": (
        [(1, G, ["B2", "B3", "B4"])],
        [("error", "duplicate_sub_part", ("B3", "B4"), (3, 4))],
    ),
    "sub_part_gap": ([(1, G, ["B2", "B3"])], [("warning", "sub_part_gap", (), (2,))]),
    "orphan_sub_part": ([(1, S, ["B3"])], [("error", "orphan_sub_part", ("B2",), (2,))]),
    "marker_forms": ([(1, G, ["B2", "B3", "B4", "B5"])], []),
    "numbered_row_then_marker_1": ([(1, G, ["B3", "B4"])], []),
    "single_empty_answer": ([(1, S, ["B2"])], []),
    "spacer_rows_in_group": ([(1, G, ["B2", "B5"])], []),
    "merged_answer_cell": ([(1, S, ["C2"]), (2, S, ["D3"])], []),
    "ragged_rows": ([(1, S, ["B2"]), (2, S, ["B4"])], []),
}


@pytest.mark.parametrize("name", sorted(EDGE_CASES))
def test_edge_case(name, load_grid):
    grid, merges = load_grid(name)
    units, issues = EDGE_CASES[name]

    preview = parse(grid, merges)

    assert summarize(preview) == units
    assert issues_of(preview) == sorted(issues)
    assert preview.can_confirm == (not any(sev == "error" for sev, *_ in issues))
    for issue in preview.issues:  # FR-016 / SC-004: every message names its cells and rows
        assert issue.message
        for cell in issue.cells:
            assert cell in issue.message
        for row in issue.rows:
            assert str(row) in issue.message


def test_header_not_found_names_both_labels(load_grid):
    preview = parse(*load_grid("no_header"))
    assert preview.header is None
    (issue,) = preview.issues
    assert "題號" in issue.message and "作答" in issue.message


def test_header_split_rows_names_found_cells(load_grid):
    preview = parse(*load_grid("header_split_rows"))
    assert preview.header is None
    assert "A1" in preview.issues[0].message and "B2" in preview.issues[0].message


def test_sub_part_numbers_and_kinds(load_grid):
    preview = parse(*load_grid("sub_part_gap"))
    (unit,) = preview.units
    assert [s.sub_part for s in unit.slots] == [1, 3]
    assert unit.kind is UnitKind.GROUP_SET

    preview = parse(*load_grid("numbered_row_then_marker_1"))
    assert [(s.sub_part, s.row) for s in preview.units[0].slots] == [(1, 3), (2, 4)]


def test_kind_iff_two_or_more_slots():
    for stem in REFERENCE_SHEETS:
        expected = json.loads((FIXTURES_DIR / f"{stem}.expected.json").read_text(encoding="utf-8"))
        tab = FakeSheetsAdapter(FIXTURES_DIR).read_tab(stem, expected["sheetId"])
        for unit in parse(tab.grid, tab.merges).units:
            assert (unit.kind is UnitKind.GROUP_SET) == (len(unit.slots) >= 2)


def test_slot_cell_warning_quotes_existing_text(load_grid):
    preview = parse(*load_grid("slot_cell_has_text"))
    messages = {i.cells[0]: i.message for i in preview.issues}
    assert "答：" in messages["B2"]
    assert "（2）______" in messages["B5"]
    assert all("replace" in m.lower() for m in messages.values())


def test_slot_existing_text_is_kept(load_grid):
    preview = parse(*load_grid("slot_cell_has_text"))
    slots = {s.a1_ref: s for u in preview.units for s in u.slots}
    assert slots["B2"].existing_text == "答："
    assert slots["B4"].existing_text == ""


def test_number_gap_message_names_missing_number(load_grid):
    (issue,) = parse(*load_grid("number_gap")).issues
    assert "3" in issue.message


def test_unrecognised_number_message_quotes_content(load_grid):
    preview = parse(*load_grid("unrecognised_numbers"))
    assert any("備註" in i.message for i in preview.issues)


def test_empty_grid_has_no_header():
    preview = parse([], [])
    assert preview.header is None
    assert [i.code for i in preview.issues] == ["header_not_found"]


@pytest.mark.parametrize(
    ("row", "col", "ref"),
    [(1, 1, "A1"), (7, 26, "Z7"), (3, 27, "AA3"), (10, 52, "AZ10"), (2, 703, "AAA2")],
)
def test_to_a1(row, col, ref):
    assert to_a1(row, col) == ref
