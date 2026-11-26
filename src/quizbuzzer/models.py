"""Domain types (diagrams/domain-class.puml; specs/001-sheets-import/data-model.md).

Pure data: no I/O. Persisted entities mirror the diagram (camelCase there, snake_case here).
Transient types carry import results between the adapter, parser, service and API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class Phase(str, Enum):
    """Activity.phase. Feature 001 only ever writes DRAFT."""

    DRAFT = "DRAFT"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class UnitKind(str, Enum):
    """QuestionUnit.kind: GROUP_SET (題組) iff the unit has 2+ slots."""

    SINGLE = "SINGLE"
    GROUP_SET = "GROUP_SET"


MIN_GROUP_COUNT = 2
MAX_GROUP_COUNT = 12


# --- Persisted entities ---------------------------------------------------------------


@dataclass(frozen=True)
class AnswerSlot:
    id: int
    sub_part: int  # > 0; 1 for SINGLE
    cell_row: int  # 1-based; top-left of a merge
    cell_column: int  # 1-based
    a1_ref: str  # derived from cell_row/cell_column, e.g. "D12"


@dataclass(frozen=True)
class QuestionUnit:
    id: int
    number: int  # > 0, unique within the activity
    kind: UnitKind
    source_row: int  # 1-based row of the numbered row
    position: int  # 0-based order in the sheet
    slots: tuple[AnswerSlot, ...] = ()


@dataclass(frozen=True)
class Activity:
    id: int
    title: str
    phase: Phase
    group_count: int  # 2..12
    source_spreadsheet_id: str
    source_sheet_id: int
    source_tab_title: str
    created_at: str  # ISO-8601 UTC, server clock
    imported_at: str  # ISO-8601 UTC, updated on re-import
    units: tuple[QuestionUnit, ...] = ()


# --- Transient types (not stored) -----------------------------------------------------


@dataclass(frozen=True)
class TabInfo:
    sheet_id: int
    title: str
    index: int


@dataclass(frozen=True)
class SpreadsheetInfo:
    spreadsheet_id: str
    title: str
    tabs: tuple[TabInfo, ...]
    requested_gid: int | None = None  # from the URL's #gid=, if any

    @property
    def preselected_sheet_id(self) -> int:
        """The #gid= tab if it exists, otherwise the first tab (lowest index) (FR-003)."""
        if self.requested_gid is not None and any(
            t.sheet_id == self.requested_gid for t in self.tabs
        ):
            return self.requested_gid
        return min(self.tabs, key=lambda t: t.index).sheet_id


Merge = tuple[int, int, int, int]
"""(start_row, end_row, start_col, end_col): 0-based, half-open, as the Sheets API returns."""


@dataclass(frozen=True)
class TabData:
    spreadsheet_id: str
    spreadsheet_title: str
    sheet_id: int
    title: str  # tab title
    grid: list[list[str]]  # displayed values; ragged rows allowed
    merges: list[Merge] = field(default_factory=list)


@dataclass(frozen=True)
class HeaderInfo:
    row: int  # 1-based
    number_column: int  # 1-based
    answer_column: int  # 1-based


@dataclass(frozen=True)
class ParsedSlot:
    sub_part: int
    row: int
    column: int
    a1_ref: str
    existing_text: str = ""


@dataclass(frozen=True)
class ParsedUnit:
    number: int
    kind: UnitKind
    source_row: int
    slots: tuple[ParsedSlot, ...]


Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    message: str
    cells: tuple[str, ...] = ()  # A1 refs
    rows: tuple[int, ...] = ()  # 1-based


@dataclass(frozen=True)
class ImportPreview:
    header: HeaderInfo | None  # None when header_not_found / header_ambiguous
    units: tuple[ParsedUnit, ...]
    issues: tuple[Issue, ...]
    # Source identity: filled in by ActivityService, not by parse().
    spreadsheet_id: str | None = None
    spreadsheet_title: str | None = None
    sheet_id: int | None = None
    tab_title: str | None = None
    fingerprint: str | None = None

    @property
    def total_units(self) -> int:
        return len(self.units)

    @property
    def total_slots(self) -> int:
        return sum(len(u.slots) for u in self.units)

    @property
    def errors(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.severity == "error")

    @property
    def warnings(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.severity == "warning")

    @property
    def can_confirm(self) -> bool:
        """True iff the preview has no error-severity issues."""
        return not self.errors
