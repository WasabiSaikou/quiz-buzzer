# Implementation Plan: Results, Sheet Export and CSV Download

**Branch**: `003-results-export` (spec directory; work continues on `master`) | **Date**:
2026-11-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-results-export/spec.md`

## Summary

Once an activity is CLOSED, students see every unit's winner and the full rank order, the
teacher sees the same plus names and times, can write the winning answers back into the
worksheet, download a CSV of all submissions, and open past CLOSED activities.

Technically:
- A new `ResultsService` builds results from the existing 002 rows (pure `build_results`), lists
  CLOSED activities, and produces the CSV through a pure `csv_export.to_csv`.
- Students get results inside their existing `student.state` snapshot: `ParticipationService`
  builds results only when the activity is CLOSED and hands them to `visibility.student_view`,
  which re-checks the phase and strips names and times (Principle III).
- A new `SheetExporter` re-reads the tab by `sheetId` with the existing **read-only** adapter,
  re-parses it with the 001 parser, re-locates each winning slot by question number and
  sub-part (pure `plan_export`), and writes all cells with **one** `values.batchUpdate` RAW
  through a **new, separate write-scoped** `GoogleSheetsWriter`. Any problem aborts before the
  write.
- No new dependencies, no schema change.

## Diagram Blueprint (Principle VIII)

The diagrams are the primary blueprint, and module and class names match them exactly.

| Diagram element | Code |
|---|---|
| Teacher UI | `static/teacher.html`, `teacher.js`: results view (CLOSED current or past), "Export to sheet" with confirm and report/problem display, "Download CSV" link, "Past activities" list |
| Student UI | `static/student.html`, `student.js`: results screen when `state.results` is present (winner, rank order, 無人作答) |
| `api/teacher_routes.py` | adds `GET /activities/closed` (before `/activities/{activity_id}`), `GET /activities/{id}/results`, `POST /activities/{id}/export`, `GET /activities/{id}/results.csv` |
| Teacher guard | unchanged; covers the new routes by prefix |
| Results service | **new** `services/results_service.py`: `build_results(activity, submissions)` (pure), `ResultsService(db_path)` with `teacher_results(activity_id)`, `load(activity_id, action) -> (Activity, ActivityResults)` (added during implementation: the exporter needs the stored units and slots too, read in the same connection), `results_for(activity)`, `list_closed()`, `results_csv(activity_id) -> (bytes, filename)`, `results_out(results)` / `csv_filename(...)` helpers |
| CSV writer | **new** `services/csv_export.py: to_csv(results) -> bytes` (pure) |
| Sheet exporter | **new** `services/sheet_exporter.py`: `format_cell(kind, sub_part, text)`, `plan_export(activity, results, preview) -> list[CellWrite]` (pure; raises `ExportBlocked`), `SheetExporter(adapter, writer, results_service)` with `export(activity_id) -> ExportReport`; exceptions `ExportBlocked(problems)`, `ExportNotShared(email)` |
| Visibility filter | `services/visibility.py: student_view(activity, participant, members, own_submissions, *, results=None)` |
| Participation service | `_member_view` builds results via `ResultsService.results_for` only when phase = CLOSED; constructor gains `results` (wired in `create_app`) |
| SheetsAdapter / SheetsWriter | `services/sheets_adapter.py`: + `SheetsWriter` protocol, + `SheetReadOnly`; `GoogleSheetsAdapter` unchanged (read-only scope) |
| GoogleSheetsWriter | **new** `services/google_sheets_writer.py` (scope `spreadsheets`, one `values.batchUpdate`, `valueInputOption=RAW`) |
| ActivityService | `PhaseConflict` gains messages for actions `results`, `export`, `csv` (reused for the CLOSED-only refusals) |
| SQLite store | `db.py`: + `list_closed_activities(conn)` |
| Domain classes | `models.py`: + `ResultEntry`, `UnitResult`, `ActivityResults`, `PastActivitySummary`, `CellWrite`, `ExportProblem`, `ExportReport` |
| App wiring | `main.py`: `ResultsService`, `SheetExporter`, `LazyGoogleSheetsWriter`, `create_app(..., writer=None)`, error mappings `export_blocked`, `export_not_shared`, `sheet_read_only` |

**Diagram changes made during planning** (re-rendered 2026-11-27, exit 0, 16/16 PNGs):
- `system-component`: the writer is a separate interface `SheetsWriter` implemented by
  `GoogleSheetsWriter` with its own credentials and the write scope; the exporter reads through
  `SheetsAdapter` (read-only) and writes through `SheetsWriter` (research R1). Lazy wiring note.
- `domain-class`: `CellWrite.a1Ref` (from the re-parsed slot), `ExportReport.unitsWritten`,
  `ExportProblem.code`.
- `003-seq-export-sheet`: `SheetsWriter` participant; `plan_export` named as the pure step;
  error codes `export_not_shared` and `not_found` (contracts).
- After `/speckit-analyze` (I1): `003-seq-view-results` and `system-component` call
  `ResultsService.results_for(activity)` (was `build_results(activity)`); `domain-class` drops
  `ActivityResults.forStudent()`: the student form is produced by `student_view`.

**Diagram changes made during implementation** (re-rendered, exit 0):
- US2: `003-seq-export-sheet`: `EXP -> RES` is `load(activity_id, action="export")`, which returns
  the activity (units and slots) with its results; was `teacher_results(activity_id)`.

## Technical Context

**Language/Version**: Python 3.11 (uv-managed `.venv`), as in 001/002.

**Primary Dependencies**: FastAPI, uvicorn + websockets, python-dotenv,
google-api-python-client, google-auth (+ httplib2 / google-auth-httplib2 already used). Dev:
pytest, httpx. **No additions** (`csv`, `io`, `urllib.parse` are stdlib; research R10).

**Storage**: SQLite (stdlib `sqlite3`). No schema change (research R8). 003 only reads.

**Testing**: pytest + FastAPI `TestClient`; `FakeSheetsAdapter` extended to also act as the
writer; mocked discovery service for `GoogleSheetsWriter` (research R9).

**Target Platform**: Windows 10/11 teacher laptop serving the classroom LAN (unchanged).

**Project Type**: Local web application (single process: REST, WebSocket, static pages).

**Performance Goals**: results on 60 student screens within 1 s of End (SC-001, same push as
002); export of ≤ 50 units within 10 s (SC-005: two Google calls to read plus one to write).

**Constraints**: Principle II (no stored addresses as write targets, ≥ 3 sheet shapes);
Principle III (results only after CLOSED, only through `student_view`); FR-014 (import
read-only by credential); no answer text or names in logs (FR-024); no frontend build step.

**Scale/Scope**: up to 50 units × 12 groups × a few slots: at most a few thousand CSV rows and a
few hundred cells per export.

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1 design.*

| Principle | How this plan complies | Pre | Post |
|---|---|---|---|
| I. Server-authoritative fairness | 003 only reads ranks assigned by 002's transaction; nothing re-ranks or uses client time. | ✅ | ✅ |
| II. Dynamic Guided Notes handling | Export re-reads the tab by `sheetId`, re-parses with the 001 parser and finds slots by (question number, sub-part); stored cell addresses are never write targets; no hardcoded addresses in `sheet_exporter.py`. `plan_export` tests run on ≥ 3 differently shaped fixtures (`template_single`, `template_group`, `shifted_layout/練習`), each with inserted rows (research R3, R9). | ✅ | ✅ |
| III. Information hiding until close | Results are built for students only after a CLOSED check in `_member_view`, and `student_view` re-checks the phase before adding them; student entries have no names or times. 002's leak test is extended: nothing before CLOSED, full results after. | ✅ | ✅ |
| IV. Single source of truth for phase | No phase changes. The existing CLOSED push carries the results, and reconnect gets them from the same snapshot. | ✅ | ✅ |
| V. Test-first for core rules | Failing-first tests for visibility (CLOSED-only results), Sheets export (re-location, abort with nothing written, formatting, single RAW call), CSV rules. Manual records M31–M42 (quickstart §4) are listed for the user. | ✅ | ✅ |
| VI. Secrets hygiene | The writer reads the same key path from `.env` settings; no new secret. The service-account email is not secret (001). Logs carry activity ids and counts only, never answer text or names; a log test checks it. | ✅ | ✅ |
| VII. Consistency and simplicity | No schema change, no new dependency, no export history, no new message type. Spec, contracts, data model and diagrams updated together. | ✅ | ✅ |
| VIII. PlantUML design-first | Blueprint table above; diagrams updated during planning and re-rendered; `/speckit-implement` ends with a 003 section in `diagrams/VERIFICATION.md`. | ✅ | ✅ |

No violations.

## Project Structure

### Documentation (this feature)

```text
specs/003-results-export/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0: R1–R10
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1: tests + manual M31–M42
├── contracts/rest-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (quiz-buzzer/; new files marked +, changed files marked ~)

```text
diagrams/VERIFICATION.md               ~ 003 code-vs-diagram section (end of implement)
src/quizbuzzer/
├── main.py                            ~ wire ResultsService, SheetExporter, LazyGoogleSheetsWriter; writer=; error mappings
├── db.py                              ~ list_closed_activities
├── models.py                          ~ results / export transient types
├── services/
│   ├── results_service.py             + build_results, ResultsService
│   ├── csv_export.py                  + to_csv
│   ├── sheet_exporter.py              + format_cell, plan_export, SheetExporter, ExportBlocked, ExportNotShared
│   ├── google_sheets_writer.py        + GoogleSheetsWriter (write scope)
│   ├── sheets_adapter.py              ~ SheetsWriter protocol, SheetReadOnly
│   ├── visibility.py                  ~ results= (CLOSED only, no names / times)
│   ├── participation_service.py       ~ results in _member_view when CLOSED
│   └── activity_service.py            ~ PhaseConflict messages for results / export / csv
├── api/teacher_routes.py              ~ closed list, results, export, results.csv
└── static/
    ├── teacher.html, teacher.js       ~ results view, export, CSV, past list
    └── student.html, student.js       ~ results screen
tests/
├── fakes/fake_sheets_adapter.py       ~ write_cells, writes log, make_read_only
├── conftest.py                        ~ app built with writer=fake_adapter
├── unit/
│   ├── test_sheet_exporter.py         + re-location (≥ 3 shapes), abort paths, format_cell
│   ├── test_csv_export.py             + quoting, BOM, CRLF, prefix, empty
│   ├── test_results_service.py        + build_results, list_closed, phase refusals
│   ├── test_google_sheets_writer.py   + scope, one batchUpdate RAW, error mapping
│   ├── test_fake_sheets_adapter.py    ~ write_cells / read-only behaviour
│   └── test_visibility.py             ~ results only for CLOSED members, stripped fields
└── integration/
    ├── test_results_api.py            + teacher results, student CLOSED state + push, never-joined
    ├── test_export_api.py             + export endpoint end-to-end on the fake sheet
    ├── test_csv_api.py                + headers, body, refusals
    ├── test_past_activities_api.py    + list + open
    ├── test_visibility_leak.py        ~ results appear only after CLOSED
    ├── test_teacher_guard.py          ~ assert the new routes are in the guarded set
    └── test_logs_003.py               + no answers / names in logs during export / CSV
```

**Structure Decision**: The single src-layout project continues; new services are modules next
to 001/002's.

## Implementation Notes for Tasks

- **Order** (test-first, Principle V): Setup (fake writer, conftest, models) → Foundational
  (`build_results`, `ResultsService` read side, PhaseConflict messages) → US1 (student results
  through the filter) → US2 (teacher results + export) → US3 (CSV) → US4 (past list) → Polish
  (log test, leak test extension, verification). Manual checks and README are not in the
  unattended run.
- **Exporter I/O order**: results (DB, then close the connection) → zero winners? return →
  `read_tab` → `parse` → `plan_export` → `write_cells`. No DB connection is held during Google
  calls; CLOSED is final, so nothing can change underneath.
- **Error mapping**: `SheetNotShared` raised during the export re-read is converted to
  `ExportNotShared` inside `SheetExporter` (Editor wording); the import path keeps its Viewer
  wording.
- **Logging**: `export: activity=<id> cells=<n> skipped=<m>`; `export blocked: activity=<id>
  problems=<n>`; never answer text, names, or cell contents.
- **Teacher UI**: the 002 dashboard keeps showing the final dashboard after End. 003 adds a
  results panel (fed by `GET …/results`) with Export and CSV controls when the displayed
  activity is CLOSED, plus a past-activities panel that loads any CLOSED activity's results.

## Complexity Tracking

No constitution violations. Choices beyond the bare minimum:

| Choice | Why needed | Simpler alternative rejected because |
|---|---|---|
| Separate `GoogleSheetsWriter` with its own credentials | Keeps import read-only by credential (001 FR-005, FR-014); user instruction | One client with write scope would let any import bug write to a teacher's sheet |
| Phase re-check inside `student_view` in addition to the caller's check | Defence in depth for Principle III | A single upstream check would leak results if a future caller forgets it |
| Pure `plan_export` split from `SheetExporter.export` | Principle II's ≥ 3-shapes gate as fast unit tests; the abort path is provable without I/O | A single I/O method needs a fake for every parser case |
