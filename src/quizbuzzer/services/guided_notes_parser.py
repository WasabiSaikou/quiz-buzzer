"""Guided Notes parser: locate questions and answer cells from sheet content alone.

Pure functions (no I/O, no Google types). Constitution Principle II: no hardcoded cell
addresses; every location is derived from the header labels 題號 / 作答, numbered rows and
（k） sub-part markers. Rules: spec FR-006–FR-016; research R2 (merges), R3 (normalisation),
R4 (sub-part assignment); issue codes in data-model.md.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from quizbuzzer.models import (
    HeaderInfo,
    ImportPreview,
    Issue,
    Merge,
    ParsedSlot,
    ParsedUnit,
    UnitKind,
)

NUMBER_LABEL = "題號"
ANSWER_LABEL = "作答"

_WHITESPACE = re.compile(r"\s+")
_QUESTION_NUMBER = re.compile(r"^[Qq]?([0-9]+)[.、]?$")
_MARKER = re.compile(r"^\(\s*([0-9]+)\s*\)")


# --- Helpers ------------------------------------------------------------------------------


def to_a1(row: int, column: int) -> str:
    """1-based (row, column) -> A1 reference, e.g. (12, 4) -> "D12"."""
    letters = ""
    n = column
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return f"{letters}{row}"


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _question_number(text: str) -> int | None:
    m = _QUESTION_NUMBER.match(_norm(text).strip())
    if m and int(m.group(1)) > 0:
        return int(m.group(1))
    return None


def _marker(text: str) -> tuple[int, str] | None:
    """(k, remaining text) if the cell starts with a （k） / (k) marker, k > 0."""
    normalized = _norm(text).strip()
    m = _MARKER.match(normalized)
    if not m or int(m.group(1)) == 0:
        return None
    return int(m.group(1)), normalized[m.end() :].strip()


def _quote(text: str) -> str:
    return '"' + text.strip().replace("\n", " ") + '"'


def _ranges(numbers: list[int]) -> str:
    return ", ".join(str(n) for n in numbers)


class _Cells:
    """Grid access that honours merges: covered (non top-left) cells read as empty."""

    def __init__(self, grid: Sequence[Sequence[str]], merges: Sequence[Merge]) -> None:
        self._grid = grid
        self._top_left: dict[tuple[int, int], tuple[int, int]] = {}
        for r0, r1, c0, c1 in merges:
            for r in range(r0, r1):
                for c in range(c0, c1):
                    self._top_left[(r, c)] = (r0, c0)
        self.row_count = len(grid)

    def raw(self, r: int, c: int) -> str:
        if r >= len(self._grid) or c >= len(self._grid[r]):
            return ""
        value = self._grid[r][c]
        return "" if value is None else str(value)

    def value(self, r: int, c: int) -> str:
        """Displayed value at 0-based (r, c); empty if covered by a merge started elsewhere."""
        if self._top_left.get((r, c), (r, c)) != (r, c):
            return ""
        return self.raw(r, c)

    def location(self, r: int, c: int) -> tuple[int, int]:
        """0-based location an answer at (r, c) is stored at: the merge's top-left, if merged."""
        return self._top_left.get((r, c), (r, c))

    def row_width(self, r: int) -> int:
        return len(self._grid[r]) if r < len(self._grid) else 0


# --- Header (FR-006) ------------------------------------------------------------------------


def _find_header(cells: _Cells) -> tuple[HeaderInfo | None, Issue | None]:
    number_cells: list[tuple[int, int]] = []
    answer_cells: list[tuple[int, int]] = []
    for r in range(cells.row_count):
        row_numbers, row_answers = [], []
        for c in range(cells.row_width(r)):
            label = _WHITESPACE.sub("", _norm(cells.value(r, c)))
            if label == NUMBER_LABEL:
                row_numbers.append((r, c))
            elif label == ANSWER_LABEL:
                row_answers.append((r, c))
        number_cells += row_numbers
        answer_cells += row_answers
        if row_numbers and row_answers:
            if len(row_numbers) > 1 or len(row_answers) > 1:
                dupes = (row_numbers if len(row_numbers) > 1 else []) + (
                    row_answers if len(row_answers) > 1 else []
                )
                refs = [to_a1(rr + 1, cc + 1) for rr, cc in dupes]
                return None, Issue(
                    "error",
                    "header_ambiguous",
                    f"Row {r + 1} has more than one {NUMBER_LABEL} or {ANSWER_LABEL} header "
                    f"cell ({', '.join(refs)}). Keep exactly one {NUMBER_LABEL} cell and one "
                    f"{ANSWER_LABEL} cell in the header row.",
                    tuple(refs),
                    (r + 1,),
                )
            (nr, nc), (_, ac) = row_numbers[0], row_answers[0]
            return HeaderInfo(row=nr + 1, number_column=nc + 1, answer_column=ac + 1), None

    message = (
        f"No header row found: no single row contains both a {NUMBER_LABEL} cell and a "
        f"{ANSWER_LABEL} cell. Add one row with both labels above the questions."
    )
    if number_cells and answer_cells:
        (nr, nc), (ar, ac) = number_cells[0], answer_cells[0]
        n_ref, a_ref = to_a1(nr + 1, nc + 1), to_a1(ar + 1, ac + 1)
        message = (
            f"No header row found: {NUMBER_LABEL} is in {n_ref} but {ANSWER_LABEL} is in "
            f"{a_ref}, on a different row. Put both labels in the same row "
            f"(rows {nr + 1} and {ar + 1})."
        )
        found = sorted([(nr, nc), (ar, ac)])
        cells_refs = tuple(to_a1(r + 1, c + 1) for r, c in found)
        rows = tuple(sorted({nr + 1, ar + 1}))
        return None, Issue("error", "header_not_found", message, cells_refs, rows)
    return None, Issue("error", "header_not_found", message)


# --- Body (FR-008–FR-016) -------------------------------------------------------------------


@dataclass
class _Marker:
    k: int
    row: int  # 0-based
    col: int  # 0-based, stored location
    rest: str
    raw: str


@dataclass
class _Question:
    number: int
    row: int  # 0-based
    loc: tuple[int, int]  # stored location of its answer cell (0-based)
    answer_raw: str
    markers: list[_Marker] = field(default_factory=list)


def parse(grid: Sequence[Sequence[str]], merges: Sequence[Merge]) -> ImportPreview:
    """Detect header, questions, slots, errors and warnings in one tab's displayed values."""
    cells = _Cells(grid, merges)
    header, header_issue = _find_header(cells)
    if header is None:
        return ImportPreview(header=None, units=(), issues=(header_issue,))

    issues: list[Issue] = []
    nc, ac = header.number_column - 1, header.answer_column - 1
    questions: list[_Question] = []

    for r in range(header.row, cells.row_count):
        number_raw = cells.value(r, nc)
        answer_raw = cells.value(r, ac)
        loc = cells.location(r, ac)
        answer_ref = to_a1(loc[0] + 1, loc[1] + 1)

        if number_raw.strip():
            number = _question_number(number_raw)
            if number is not None:
                questions.append(_Question(number, r, loc, answer_raw))
                continue
            ref = to_a1(r + 1, nc + 1)
            issues.append(
                Issue(
                    "warning",
                    "unrecognised_question_number",
                    f"Row {r + 1}: {NUMBER_LABEL} cell {ref} {_quote(number_raw)} is not a "
                    f"question number, so the row was skipped. Use a form like 1, 1., 1、 or Q1 "
                    f"if it is a question; otherwise clear the cell.",
                    (ref,),
                    (r + 1,),
                )
            )

        if not answer_raw.strip():
            continue
        marker = _marker(answer_raw)
        if marker is not None:
            k, rest = marker
            if not questions:
                issues.append(
                    Issue(
                        "error",
                        "orphan_sub_part",
                        f"Row {r + 1}: sub-part marker in {answer_ref} {_quote(answer_raw)} comes "
                        f"before the first numbered question. Add a question number above it, "
                        f"or remove the marker.",
                        (answer_ref,),
                        (r + 1,),
                    )
                )
            else:
                questions[-1].markers.append(_Marker(k, loc[0], loc[1], rest, answer_raw))
            continue
        issues.append(
            Issue(
                "warning",
                "stray_answer_text",
                f"Row {r + 1}: {answer_ref} contains {_quote(answer_raw)} but has no question "
                f"number or sub-part marker, so no answer slot was created. Add a marker such as "
                f"（2） if it is meant to be a sub-part.",
                (answer_ref,),
                (r + 1,),
            )
        )

    units = tuple(_build_unit(q, issues) for q in questions)
    _check_numbers(questions, nc, issues)
    if not questions:
        issues.append(
            Issue(
                "error",
                "no_questions",
                f"No numbered questions were found below the header (row {header.row}). Put "
                f"question numbers in the {NUMBER_LABEL} column.",
                (),
                (),
            )
        )
    return ImportPreview(header=header, units=units, issues=tuple(issues))


def _build_unit(q: _Question, issues: list[Issue]) -> ParsedUnit:
    """Research R4: decide whether the numbered row itself is a slot, then add marker slots."""
    slots: list[_Marker] = []
    own = _marker(q.answer_raw)
    if own is not None:  # rule 1: numbered row carries its own marker
        slots.append(_Marker(own[0], q.loc[0], q.loc[1], own[1], q.answer_raw))
    elif q.markers and q.markers[0].k == 1:  # rule 2: next marker is (1) -> not a slot
        if q.answer_raw.strip():
            ref = to_a1(q.loc[0] + 1, q.loc[1] + 1)
            issues.append(
                Issue(
                    "warning",
                    "stray_answer_text",
                    f"Row {q.row + 1}: {ref} contains {_quote(q.answer_raw)}, but question "
                    f"{q.number}'s sub-parts start with （1） on a later row, so this cell is not "
                    f"an answer slot. Clear it, or move the （1） marker here.",
                    (ref,),
                    (q.row + 1,),
                )
            )
    else:  # rule 3 (implicit sub-part 1) or rule 4 (single question)
        slots.append(_Marker(1, q.loc[0], q.loc[1], q.answer_raw.strip(), q.answer_raw))
    slots += q.markers

    for s in slots:  # FR-011a: existing text will be overwritten by export
        if s.rest:
            ref = to_a1(s.row + 1, s.col + 1)
            issues.append(
                Issue(
                    "warning",
                    "slot_cell_has_text",
                    f"{ref} (row {s.row + 1}) already contains {_quote(s.raw)}. Export will "
                    f"replace the whole cell with the answer; clear it if that text matters.",
                    (ref,),
                    (s.row + 1,),
                )
            )

    by_k: dict[int, list[_Marker]] = defaultdict(list)
    for s in slots:
        by_k[s.k].append(s)
    for k, same in sorted(by_k.items()):
        if len(same) > 1:
            refs = tuple(to_a1(s.row + 1, s.col + 1) for s in same)
            rows = tuple(s.row + 1 for s in same)
            issues.append(
                Issue(
                    "error",
                    "duplicate_sub_part",
                    f"Question {q.number} has sub-part （{k}） more than once ({', '.join(refs)}; "
                    f"rows {_ranges(list(rows))}). Renumber the markers so each appears once.",
                    refs,
                    rows,
                )
            )
    if slots:
        missing = [k for k in range(1, max(by_k) + 1) if k not in by_k]
        if missing:
            issues.append(
                Issue(
                    "warning",
                    "sub_part_gap",
                    f"Question {q.number} (row {q.row + 1}) has no sub-part "
                    f"{', '.join(f'（{k}）' for k in missing)}. Check the markers; slots keep "
                    f"the numbers written in the sheet.",
                    (),
                    (q.row + 1,),
                )
            )

    parsed = tuple(
        ParsedSlot(
            sub_part=s.k,
            row=s.row + 1,
            column=s.col + 1,
            a1_ref=to_a1(s.row + 1, s.col + 1),
            existing_text=s.rest,
        )
        for s in slots
    )
    kind = UnitKind.GROUP_SET if len(parsed) >= 2 else UnitKind.SINGLE
    return ParsedUnit(number=q.number, kind=kind, source_row=q.row + 1, slots=parsed)


def _check_numbers(questions: list[_Question], nc: int, issues: list[Issue]) -> None:
    rows_by_number: dict[int, list[int]] = defaultdict(list)
    for q in questions:
        rows_by_number[q.number].append(q.row + 1)
    for number, rows in sorted(rows_by_number.items()):
        if len(rows) > 1:
            refs = tuple(to_a1(r, nc + 1) for r in rows)
            issues.append(
                Issue(
                    "error",
                    "duplicate_question_number",
                    f"Question number {number} appears more than once (rows {_ranges(rows)}: "
                    f"{', '.join(refs)}). Give each question a different number.",
                    refs,
                    tuple(rows),
                )
            )
    if not questions:
        return
    present = set(rows_by_number)
    missing = [n for n in range(1, max(present) + 1) if n not in present]
    if missing:
        issues.append(
            Issue(
                "warning",
                "question_number_gap",
                f"Question numbers {_ranges(missing)} are missing. Check the numbering; the "
                f"questions found will still be imported.",
                (),
                (),
            )
        )
    for prev, cur in zip(questions, questions[1:]):
        if cur.number < prev.number:
            ref = to_a1(cur.row + 1, nc + 1)
            issues.append(
                Issue(
                    "warning",
                    "question_number_out_of_order",
                    f"Row {cur.row + 1}: question {cur.number} ({ref}) comes after question "
                    f"{prev.number}. Questions keep the sheet's row order; renumber if that is "
                    f"not intended.",
                    (ref,),
                    (cur.row + 1,),
                )
            )


# --- Fingerprint (research R6) --------------------------------------------------------------


def compute_fingerprint(
    spreadsheet_id: str, sheet_id: int, units: Sequence[ParsedUnit]
) -> str:
    """SHA-256 of the structure only (identity + units + slot cells); ignores text and issues."""
    payload = {
        "spreadsheetId": spreadsheet_id,
        "sheetId": sheet_id,
        "units": [
            {
                "number": u.number,
                "kind": u.kind.value,
                "sourceRow": u.source_row,
                "slots": [{"subPart": s.sub_part, "row": s.row, "column": s.column} for s in u.slots],
            }
            for u in units
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
