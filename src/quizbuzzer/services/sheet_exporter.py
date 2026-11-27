"""SheetExporter: writes winning answers back into the source sheet (diagrams/003-seq-export-sheet.puml).

Constitution II: no stored or hardcoded cell address is ever a write target. The tab is re-read
by its fixed sheetId with the READ-ONLY adapter, re-parsed with the 001 parser, and each winning
slot is found again by (question number, sub-part). `plan_export` is pure; any problem raises
ExportBlocked before anything is sent. All cells go out in ONE write through the separate,
write-scoped SheetsWriter (research R1 – R4). Answer text is never logged (FR-024).
"""

from __future__ import annotations

import logging

from quizbuzzer.models import (
    Activity,
    ActivityResults,
    CellWrite,
    ExportProblem,
    ExportReport,
    ImportPreview,
    UnitKind,
)
from quizbuzzer.services import guided_notes_parser
from quizbuzzer.services.results_service import ResultsService
from quizbuzzer.services.sheets_adapter import SheetNotShared, SheetsAdapter, SheetsWriter

log = logging.getLogger("quizbuzzer.export")


class ExportBlocked(Exception):
    """The re-read sheet has errors, or a winning question / sub-part is missing (FR-009)."""

    def __init__(self, problems: list[ExportProblem]) -> None:
        self.problems = problems
        super().__init__(
            f"Nothing was written: the sheet no longer matches the activity "
            f"({len(problems)} problem(s)). Fix the sheet, then export again."
        )


class ExportNotShared(Exception):
    """The source sheet cannot be read during export: it must be shared as Editor (FR-013)."""

    def __init__(self, service_account_email: str) -> None:
        self.service_account_email = service_account_email
        super().__init__(
            "The spreadsheet is not shared with the app. Share it with the address below as an "
            "Editor, then export again. Nothing was written."
        )


def format_cell(kind: UnitKind, sub_part: int, answer: str) -> str:
    """FR-007 / research R4: SINGLE -> answer; GROUP_SET -> '（k）' + answer (full-width parens)."""
    if kind is UnitKind.GROUP_SET:
        return f"（{sub_part}）{answer}"
    return answer


def plan_export(
    activity: Activity, results: ActivityResults, preview: ImportPreview
) -> list[CellWrite]:
    """Pure: the cells to write, re-located in `preview` (a fresh parse of the source tab).

    Raises ExportBlocked listing every problem (parse errors, or missing questions / sub-parts
    of units that have a winner). Units without a winner are never looked up (spec Edge Cases).
    The unit's kind from import decides the text format (research R4).
    """
    if preview.errors:
        raise ExportBlocked(
            [
                ExportProblem(kind="parse_error", code=issue.code, message=issue.message)
                for issue in preview.errors
            ]
        )
    parsed = {u.number: u for u in preview.units}
    winners = {u.unit_id: u.winner for u in results.units if u.winner is not None}
    problems: list[ExportProblem] = []
    writes: list[CellWrite] = []
    for unit in sorted(activity.units, key=lambda u: u.position):
        winner = winners.get(unit.id)
        if winner is None:
            continue
        found = parsed.get(unit.number)
        if found is None:
            problems.append(
                ExportProblem(
                    kind="missing_question",
                    question_number=unit.number,
                    message=f"Question {unit.number} can no longer be found in the sheet.",
                )
            )
            continue
        slots = {s.sub_part: s for s in found.slots}
        answers = dict(winner.answers)
        for slot in sorted(unit.slots, key=lambda s: s.sub_part):
            target = slots.get(slot.sub_part)
            if target is None:
                problems.append(
                    ExportProblem(
                        kind="missing_sub_part",
                        question_number=unit.number,
                        sub_part=slot.sub_part,
                        message=(
                            f"Question {unit.number} sub-part （{slot.sub_part}） can no longer "
                            f"be found in the sheet."
                        ),
                    )
                )
                continue
            writes.append(
                CellWrite(
                    a1_ref=target.a1_ref,
                    text=format_cell(unit.kind, slot.sub_part, answers[slot.sub_part]),
                )
            )
    if problems:
        raise ExportBlocked(problems)
    return writes


class SheetExporter:
    def __init__(
        self, adapter: SheetsAdapter, writer: SheetsWriter, results_service: ResultsService
    ) -> None:
        self.adapter = adapter  # read-only scope: the re-read
        self.writer = writer  # write scope: the single batch write
        self.results_service = results_service

    def export(self, activity_id: int) -> ExportReport:
        # 1. Results (DB read; ActivityNotFound / PhaseConflict(action="export") before CLOSED).
        activity, results = self.results_service.load(activity_id, action="export")
        units_written = sum(1 for u in results.units if u.winner is not None)
        units_skipped = len(results.units) - units_written
        if units_written == 0:
            log.info("export: activity=%s cells=0 skipped=%s (no winners)", activity_id, units_skipped)
            return ExportReport(cells_written=0, units_written=0, units_skipped=units_skipped)

        # 2. Re-read the tab by its fixed sheetId (current title comes back with it).
        try:
            tab = self.adapter.read_tab(activity.source_spreadsheet_id, activity.source_sheet_id)
        except SheetNotShared as exc:
            raise ExportNotShared(exc.service_account_email) from None

        # 3. Re-parse and re-locate; any problem stops here with nothing written.
        preview = guided_notes_parser.parse(tab.grid, tab.merges)
        try:
            cells = plan_export(activity, results, preview)
        except ExportBlocked as exc:
            log.info("export blocked: activity=%s problems=%s", activity_id, len(exc.problems))
            raise

        # 4. One write request, RAW.
        written = self.writer.write_cells(tab.spreadsheet_id, tab.sheet_id, tab.title, cells)
        log.info(
            "export: activity=%s cells=%s skipped=%s", activity_id, written, units_skipped
        )
        return ExportReport(
            cells_written=written, units_written=units_written, units_skipped=units_skipped
        )
