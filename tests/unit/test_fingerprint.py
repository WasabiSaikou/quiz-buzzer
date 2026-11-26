"""compute_fingerprint: structure only (research R6, FR-022)."""

from dataclasses import replace

from quizbuzzer.models import ParsedSlot, ParsedUnit, UnitKind
from quizbuzzer.services.guided_notes_parser import compute_fingerprint, parse

GRID = [
    ["題號", "題目", "作答"],
    ["1", "第一題", ""],
    ["2", "第二題", "（1）"],
    ["", "", "（2）"],
]


def units(grid=GRID):
    return parse(grid, []).units


def fp(u=None, sid="sid", sheet=0):
    return compute_fingerprint(sid, sheet, units() if u is None else u)


def test_stable():
    assert fp() == fp()
    assert len(fp()) == 64  # hex SHA-256


def test_changes_with_identity():
    assert fp(sid="other") != fp()
    assert fp(sheet=1) != fp()


def _mutate_first_slot(**changes):
    u = list(units())
    first = u[1]
    slots = list(first.slots)
    slots[0] = replace(slots[0], **changes)
    u[1] = replace(first, slots=tuple(slots))
    return u


def test_changes_with_structure():
    base = units()
    variants = [
        [replace(base[0], number=9), base[1]],
        [replace(base[0], kind=UnitKind.GROUP_SET), base[1]],
        [replace(base[0], source_row=20), base[1]],
        _mutate_first_slot(sub_part=5),
        _mutate_first_slot(row=99),
        _mutate_first_slot(column=9),
        [base[0]],
        [base[0], base[1], ParsedUnit(3, UnitKind.SINGLE, 9, (ParsedSlot(1, 9, 3, "C9"),))],
    ]
    seen = {fp()}
    for v in variants:
        f = fp(v)
        assert f not in seen
        seen.add(f)


def test_ignores_text_and_warnings():
    edited = [row[:] for row in GRID]
    edited[1][1] = "改過的題目文字"  # question text changed
    edited[1][2] = "答：______"  # now produces a slot_cell_has_text warning
    assert parse(edited, []).issues
    assert fp(units(edited)) == fp()
