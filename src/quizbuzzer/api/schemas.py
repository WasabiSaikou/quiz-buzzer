"""Request/response models for /api/teacher (contracts/rest-api.md). camelCase on the wire."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from quizbuzzer.models import Activity, ImportPreview, SpreadsheetInfo


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# --- Requests ---------------------------------------------------------------------------


class ImportTabsRequest(ApiModel):
    url: str


class PreviewRequest(ApiModel):
    url: str
    sheet_id: int


class CreateActivityRequest(ApiModel):
    url: str
    sheet_id: int
    # Validated by ActivityService (2..12), so a bad value yields 422 invalid_group_count
    # rather than a generic validation error (data-model.md › Activity.groupCount).
    group_count: Any
    fingerprint: str
    acknowledge_warnings: bool = False


class ReplaceQuestionsRequest(ApiModel):
    url: str
    sheet_id: int
    fingerprint: str
    acknowledge_warnings: bool = False


# --- Tabs -------------------------------------------------------------------------------


class TabOut(ApiModel):
    sheet_id: int
    title: str
    index: int


class TabsResponse(ApiModel):
    spreadsheet_id: str
    spreadsheet_title: str
    tabs: list[TabOut]
    preselected_sheet_id: int

    @classmethod
    def from_info(cls, info: SpreadsheetInfo, preselected_sheet_id: int) -> TabsResponse:
        return cls(
            spreadsheet_id=info.spreadsheet_id,
            spreadsheet_title=info.title,
            tabs=[TabOut(sheet_id=t.sheet_id, title=t.title, index=t.index) for t in info.tabs],
            preselected_sheet_id=preselected_sheet_id,
        )


# --- Preview ----------------------------------------------------------------------------


class HeaderOut(ApiModel):
    row: int
    number_column: int
    answer_column: int


class PreviewSlotOut(ApiModel):
    sub_part: int
    a1_ref: str
    row: int
    column: int


class PreviewUnitOut(ApiModel):
    number: int
    kind: Literal["SINGLE", "GROUP_SET"]
    source_row: int
    slots: list[PreviewSlotOut]


class IssueOut(ApiModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    cells: list[str]
    rows: list[int]


class PreviewTotals(ApiModel):
    units: int
    slots: int
    errors: int
    warnings: int


class PreviewResponse(ApiModel):
    spreadsheet_id: str | None
    spreadsheet_title: str | None
    sheet_id: int | None
    tab_title: str | None
    header: HeaderOut | None
    units: list[PreviewUnitOut]
    issues: list[IssueOut]
    totals: PreviewTotals
    fingerprint: str | None
    can_confirm: bool

    @classmethod
    def from_preview(cls, p: ImportPreview) -> PreviewResponse:
        return cls(
            spreadsheet_id=p.spreadsheet_id,
            spreadsheet_title=p.spreadsheet_title,
            sheet_id=p.sheet_id,
            tab_title=p.tab_title,
            header=(
                HeaderOut(
                    row=p.header.row,
                    number_column=p.header.number_column,
                    answer_column=p.header.answer_column,
                )
                if p.header
                else None
            ),
            units=[
                PreviewUnitOut(
                    number=u.number,
                    kind=u.kind.value,
                    source_row=u.source_row,
                    slots=[
                        PreviewSlotOut(sub_part=s.sub_part, a1_ref=s.a1_ref, row=s.row, column=s.column)
                        for s in u.slots
                    ],
                )
                for u in p.units
            ],
            issues=[
                IssueOut(
                    severity=i.severity,
                    code=i.code,
                    message=i.message,
                    cells=list(i.cells),
                    rows=list(i.rows),
                )
                for i in p.issues
            ],
            totals=PreviewTotals(
                units=p.total_units,
                slots=p.total_slots,
                errors=len(p.errors),
                warnings=len(p.warnings),
            ),
            fingerprint=p.fingerprint,
            can_confirm=p.can_confirm,
        )


# --- Activity ---------------------------------------------------------------------------


class SourceOut(ApiModel):
    spreadsheet_id: str
    sheet_id: int
    tab_title: str


class ActivitySlotOut(ApiModel):
    id: int
    sub_part: int
    a1_ref: str
    row: int
    column: int


class ActivityUnitOut(ApiModel):
    id: int
    number: int
    kind: Literal["SINGLE", "GROUP_SET"]
    source_row: int
    position: int
    slots: list[ActivitySlotOut]


class ActivityTotals(ApiModel):
    units: int
    slots: int


class ActivityResponse(ApiModel):
    id: int
    title: str
    phase: Literal["DRAFT", "OPEN", "CLOSED"]
    group_count: int
    source: SourceOut
    created_at: str
    imported_at: str
    units: list[ActivityUnitOut]
    totals: ActivityTotals

    @classmethod
    def from_activity(cls, a: Activity) -> ActivityResponse:
        return cls(
            id=a.id,
            title=a.title,
            phase=a.phase.value,
            group_count=a.group_count,
            source=SourceOut(
                spreadsheet_id=a.source_spreadsheet_id,
                sheet_id=a.source_sheet_id,
                tab_title=a.source_tab_title,
            ),
            created_at=a.created_at,
            imported_at=a.imported_at,
            units=[
                ActivityUnitOut(
                    id=u.id,
                    number=u.number,
                    kind=u.kind.value,
                    source_row=u.source_row,
                    position=u.position,
                    slots=[
                        ActivitySlotOut(
                            id=s.id, sub_part=s.sub_part, a1_ref=s.a1_ref, row=s.cell_row, column=s.cell_column
                        )
                        for s in u.slots
                    ],
                )
                for u in a.units
            ],
            totals=ActivityTotals(
                units=len(a.units), slots=sum(len(u.slots) for u in a.units)
            ),
        )


class CurrentActivityResponse(ApiModel):
    activity: ActivityResponse | None


# --- Errors -----------------------------------------------------------------------------


class ErrorBody(ApiModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorEnvelope(ApiModel):
    error: ErrorBody
