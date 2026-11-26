"""Domain types (diagrams/domain-class.puml; 001 and 002 data-model.md).

Pure data: no I/O. Persisted entities mirror the diagram (camelCase there, snake_case here).
Transient types carry import results between the adapter, parser, service and API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, NamedTuple


class Phase(str, Enum):
    """Activity.phase: DRAFT -> OPEN -> CLOSED, forward only (002 FR-005)."""

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


# --- Feature 002 entities (specs/002-live-buzz-activity/data-model.md) -------------------
# A group is a value (activity, group_number), not an entity (002 research R4).


@dataclass(frozen=True)
class Participant:
    """One student's membership in one group of one activity (data-model.md › Participant)."""

    id: int
    activity_id: int
    group_number: int  # 1..Activity.group_count
    display_name: str  # trimmed, 1..20 characters; student data: never logged
    joined_at: str  # ISO-8601 UTC, server clock
    # token_hash is deliberately not carried here: only db.py and the service see it.


@dataclass(frozen=True)
class SubmissionAnswer:
    slot_id: int
    sub_part: int
    text: str  # trimmed, 1..200 characters; never logged


@dataclass(frozen=True)
class Submission:
    """One group's answer to one unit (data-model.md › Submission)."""

    id: int
    unit_id: int
    unit_number: int
    group_number: int
    participant_id: int
    submitted_by: str  # the submitter's display name
    rank: int  # 1 = winner; assigned by the server in arrival order (Constitution I)
    received_at: str  # ISO-8601 UTC with milliseconds; display and 003 CSV only
    answers: tuple[SubmissionAnswer, ...] = ()

    @property
    def is_winner(self) -> bool:
        return self.rank == 1


class StudentKey(NamedTuple):
    """Resolved once when a /ws/student socket connects (data-model.md › StudentKey)."""

    activity_id: int
    participant_id: int
    group_number: int


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
