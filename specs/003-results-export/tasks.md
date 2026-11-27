---

description: "Task list for feature 003 — Results, Sheet Export and CSV Download"
---

# Tasks: Results, Sheet Export and CSV Download

**Input**: Design documents from `specs/003-results-export/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/rest-api.md](contracts/rest-api.md),
[quickstart.md](quickstart.md)

**Tests**: REQUIRED (Constitution Principle V and the user's instruction). Tests come first for
these core rules:
- **slot re-location** on ≥ 3 sheet shapes (Principle II)
- **the abort-with-nothing-written path**
- **cell formatting**: single vs 題組
- **CSV**: quoting, BOM, formula prefix
- **CLOSED-only visibility of results** (Principle III)

Write each test task first, **run it, and record that it fails**, before starting the
implementation task it covers. Record the red run in `docs/verification.md` › Test-first record
(003): test id, date and failing output summary.

**Organization**: Tasks are grouped by user story:
- **US1** (P1, students see results): needs only the Foundational phase.
- **US2** (P1, teacher results + export to sheet): needs only the Foundational phase.
- **US3** (P2, CSV): needs the Foundational phase.
- **US4** (P3, past activities): needs the Foundational phase; its UI reuses US2's results panel.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: US1 … US4 (user story phases only)
- All paths are relative to `quiz-buzzer/`. Package root: `src/quizbuzzer/`.

## Conventions used by every task

- Module, class and function names come from the plan's **Diagram Blueprint** table and must
  match the diagrams exactly (Principle VIII). Call order: `diagrams/003-seq-*.puml`.
- Transient type fields are defined once in [data-model.md](data-model.md); tasks cite them as
  `data-model.md › Type.field`.
- HTTP status, error `code`, `details` and payload shapes: [contracts/rest-api.md](contracts/rest-api.md).
- 003 never writes to the database (FR-022). The exporter holds no DB connection during Google
  calls.
- Student-bound data is built **only** by `ParticipationService` through
  `visibility.student_view(...)` (002 research R6, 003 research R5).
- Never log answer text, display names or cell contents. Log only ids, codes and counts
  (FR-024).
- The import adapter stays read-only; only `GoogleSheetsWriter` has the write scope
  (research R1, FR-014).

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Add the transient types `ResultEntry`, `UnitResult` (with `winner` and `no_answer` properties), `ActivityResults`, `PastActivitySummary`, `CellWrite`, `ExportProblem`, `ExportReport` to `src/quizbuzzer/models.py`, as frozen dataclasses (data-model.md › ResultEntry.rank, ResultEntry.group_number, ResultEntry.is_winner, ResultEntry.answers, ResultEntry.submitted_by, ResultEntry.received_at, UnitResult.entries, UnitResult.winner, UnitResult.no_answer, ActivityResults.units, PastActivitySummary, CellWrite.a1_ref, CellWrite.text, ExportProblem.kind, ExportProblem.question_number, ExportProblem.sub_part, ExportProblem.code, ExportProblem.message, ExportReport.cells_written, ExportReport.units_written, ExportReport.units_skipped).
- [X] T002 Add the `SheetsWriter` protocol (`service_account_email`, `write_cells(spreadsheet_id, sheet_id, tab_title, cells) -> int`) and `SheetReadOnly(service_account_email)` to `src/quizbuzzer/services/sheets_adapter.py` (research R1).
- [X] T003 Write tests first in `tests/unit/test_fake_sheets_adapter.py` for the fake writer: `write_cells` stores each `CellWrite.text` verbatim into the tab found by `sheet_id` at `a1_ref` (growing ragged rows), returns the cell count, appends one entry per call to `writes`; `make_read_only(spreadsheet_id)` makes `write_cells` raise `SheetReadOnly` while `read_tab` still works; `fail_with` also applies to writes. Observe failing.
- [X] T004 Implement T003 in `tests/fakes/fake_sheets_adapter.py` (A1 → row/column helper, `writes` list, `make_read_only`), and build the `app` fixture in `tests/conftest.py` with `writer=fake_adapter` (add the `create_app(writer=...)` parameter in `src/quizbuzzer/main.py` now, default `None`, stored on `app.state.writer`; T023 adds the lazy Google default).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Results model and read side used by every story.

### Tests for Foundational (write first, observe failing) ⚠️

- [X] T005 [P] Write `tests/unit/test_results_service.py`:
  - `build_results(activity, submissions)`: units in `position` order; entries in rank order; `winner` is the rank-1 entry; a unit with no submission has `no_answer` true and `winner` None; answers in sub-part order; `submitted_by` / `received_at` carried (data-model.md › ResultEntry.submitted_by, ResultEntry.received_at).
  - `ResultsService.teacher_results(id)`: unknown id → `ActivityNotFound`; DRAFT / OPEN → `PhaseConflict` with `action == "results"` and the contract message; CLOSED → `ActivityResults` matching the DB (use `tests/live_helpers.make_activity` and real submits through `ParticipationService`).
  - `results_out(results)` produces the contract's `TeacherResults` JSON shape exactly.
  Observe failing.

### Implementation for Foundational

- [X] T006 Add messages for `action in {"results", "export", "csv"}` to `PhaseConflict` in `src/quizbuzzer/services/activity_service.py` (contracts › common refusals). Existing open / end messages unchanged.
- [X] T007 Create `src/quizbuzzer/services/results_service.py`: pure `build_results`, `results_out`, and `ResultsService(db_path)` with `teacher_results(activity_id)` and `results_for(activity)` (no phase check; reads `db.list_dashboard_submissions`). Orders per data-model.md › ActivityResults.units (sheet order) and UnitResult.entries (rank order); sets data-model.md › ResultEntry.is_winner, UnitResult.winner, UnitResult.no_answer. Make T005 pass.

**Checkpoint**: `uv run pytest` green; commit.

---

## Phase 3: User Story 1 — Students see the results once the activity ends (Priority: P1) 🎯 MVP

**Goal**: After End, every member's screen shows winners, rank order and 無人作答; nothing before.

**Independent Test**: spec US1 Independent Test.

### Tests for User Story 1 (write first, observe failing) ⚠️

- [X] T008 [P] [US1] Extend `tests/unit/test_visibility.py` (**CLOSED-only visibility**):
  - member + CLOSED + `results=` → `results` key present with every unit, entries `{rank, isWinner, groupNumber, answers}` only (no `submittedBy`, `receivedAt`), including other groups' entries;
  - member + DRAFT or OPEN with `results=` passed anyway → **no** `results` key and the output equals the 002 output without `results` (the filter's own phase re-check);
  - no membership / foreign membership + CLOSED + `results=` → no `results` key;
  - `results=None` + CLOSED → no `results` key (002 tests unchanged).
- [X] T009 [P] [US1] Write `tests/integration/test_results_api.py` › student part:
  - groups 4, 1, 6 submit unit 2 in that order, nobody submits another unit; End; a member of group 3 that never submitted gets `GET /api/student/state` with `results` listing ranks 1–3 (groups 4, 1, 6) and an empty list for the unanswered unit;
  - a connected `/ws/student` socket receives the CLOSED `student.state` with `results` after End;
  - a browser with no membership gets no `results`;
  - while OPEN, a member's state has no `results` key.
- [X] T010 [P] [US1] Extend `tests/integration/test_visibility_leak.py`: over the full recorded traffic of one student, assert no other group's data and no `rank` appear in any message before the CLOSED snapshot, and that the CLOSED snapshot contains the complete results (SC-002).

### Implementation for User Story 1

- [X] T011 [US1] Add the keyword-only `results` parameter to `student_view` in `src/quizbuzzer/services/visibility.py`: emit `results` only when the participant is a member of `activity` and `activity.phase is Phase.CLOSED`; strip `submittedBy` / `receivedAt`, which are teacher only (data-model.md › ResultEntry.submitted_by, ResultEntry.received_at; contracts › StudentState `results`). Make T008 pass.
- [X] T012 [US1] In `src/quizbuzzer/services/participation_service.py`, give `ParticipationService` a `results` collaborator (constructor keyword, default `None`) and make `_member_view` call `results.results_for(activity)` **only** when `activity.phase is Phase.CLOSED`, passing it to `student_view`. Wire `ResultsService` in `src/quizbuzzer/main.py` (`app.state.results`). Make T009 and T010 pass.
- [X] T013 [US1] Student UI in `src/quizbuzzer/static/student.html` and `student.js`: when `state.results` is present, render the results screen (per unit in order: winner group and answer, each 題組 slot labelled （k）; then the rank list group / answer / rank; 無人作答 for an empty unit). Escape all text (no `innerHTML` with answer text).

**Checkpoint**: full suite green; commit "feat(003): US1".

---

## Phase 4: User Story 2 — Teacher sees results and exports winning answers into the sheet (Priority: P1)

**Goal**: Teacher results view; export re-locates slots, writes once, RAW, or aborts with nothing written.

**Independent Test**: spec US2 Independent Test.

### Tests for User Story 2 (write first, observe failing) ⚠️

- [ ] T014 [P] [US2] Write `tests/unit/test_sheet_exporter.py` › `format_cell` (**cell formatting**): SINGLE → answer unchanged; GROUP_SET sub-part k → `"（k）" + answer` with U+FF08/U+FF09 and half-width digits; answers starting with `=` and containing `,` `"` newlines are kept verbatim.
- [ ] T015 [P] [US2] Same file › `plan_export` **slot re-location** on ≥ 3 shapes (Principle II): for each of `template_single.csv`, `template_group.csv` and `shifted_layout.json` tab `練習` (sheetId 918273645): build the activity from the original grid, then re-parse (a) the unchanged grid, (b) the grid with 2 rows inserted above the header, (c) the grid with a blank row inserted between two questions, (d) the grid with one extra column inserted left of the answer column; assert each `CellWrite.a1_ref` equals the slot's **new** cell (computed from the modified grid, not from the stored `AnswerSlot.a1_ref`) and that units without a winner produce no `CellWrite`. Also: a sub-part added after import is ignored; a SINGLE unit that became 題組 in the sheet still writes plain text to its sub-part-1 cell.
- [ ] T016 [P] [US2] Same file › `plan_export` **abort path**: a parse error in the re-read (e.g. duplicate question number, no header) → `ExportBlocked` listing each error as `parse_error` with its 001 code; a winning question deleted → `missing_question`; a winning 題組 sub-part deleted → `missing_sub_part`; several problems → all listed; a deleted question whose unit has **no** winner → not a problem. Warnings in the re-read do not block.
- [ ] T017 [P] [US2] Same file › `SheetExporter.export` with `FakeSheetsAdapter` as adapter and writer (**nothing written** on every failure): blocked plan, view-only (`make_read_only`), not shared (`fail_with(SheetNotShared)` → `ExportNotShared` naming the email), tab gone (`SheetNotFound`), Google down (`SheetsUnavailable`) → each raises, `writes` is empty (or the write raised before changing anything) and `snapshot()` is unchanged. Success: exactly **one** `write_cells` call holding all cells, report counts correct; zero winners → no `read_tab` and no `write_cells` call, report `cells_written == 0`; DRAFT / OPEN → `PhaseConflict(action="export")` and no Google call; a renamed tab (fake tab title changed, same sheetId) still succeeds; a second export writes the same cells and reports the same count.
- [ ] T018 [P] [US2] Write `tests/unit/test_google_sheets_writer.py` with a mocked discovery service: credentials requested with scope `https://www.googleapis.com/auth/spreadsheets`; exactly one `spreadsheets().values().batchUpdate(...)` per `write_cells` with body `valueInputOption == "RAW"` and `data == [{"range": "'<title>'!<a1>", "values": [[text]]}, …]` (title quotes doubled); returns `totalUpdatedCells`; 403 → `SheetReadOnly(email)`; 403 SERVICE_DISABLED → `SheetsUnavailable`; 404 → `SheetNotFound`; 500 / timeout → `SheetsUnavailable`. Also assert `GoogleSheetsAdapter` still uses only the read-only scope (FR-014).
- [ ] T019 [P] [US2] Write `tests/integration/test_export_api.py` end to end on the fake sheet: run an activity (single answered, 題組 answered, one unanswered), End, insert rows in the fake grid, `POST …/export` → 200 `{cellsWritten, unitsWritten, unitsSkipped}` and the fake grid holds the formatted answers at the new cells, the unanswered cell untouched, `=1+1` stored as text; repeat → same result; every failure code in the contract (`export_blocked` with `details.problems`, `export_not_shared` and `sheet_read_only` with `details.serviceAccountEmail`, `not_found`, `sheets_unavailable`, `phase_conflict` before CLOSED, `not_found` for an unknown activity); zero submissions → 0 cells.
- [ ] T020 [P] [US2] Extend `tests/integration/test_results_api.py` › teacher part: `GET …/results` for CLOSED returns the contract `TeacherResults` (names, times, empty list for unanswered units); DRAFT / OPEN → 409 `phase_conflict`; unknown → 404.

### Implementation for User Story 2

- [ ] T021 [US2] Create `src/quizbuzzer/services/sheet_exporter.py`: `format_cell`, pure `plan_export(activity, results, preview)` (research R3, R4; data-model.md › CellWrite.a1_ref, CellWrite.text, ExportProblem.kind), the report per data-model.md › ExportReport.units_skipped, `ExportBlocked(problems)`, `ExportNotShared(email)`, and `SheetExporter(adapter, writer, results_service).export(activity_id)` in the order of `diagrams/003-seq-export-sheet.puml`. Log ids and counts only. Make T014–T017 pass.
- [ ] T022 [P] [US2] Create `src/quizbuzzer/services/google_sheets_writer.py: GoogleSheetsWriter` (own credentials, write scope, one `values.batchUpdate` RAW, error mapping per research R1; reuse `quote_tab_title`). Make T018 pass.
- [ ] T023 [US2] Wire in `src/quizbuzzer/main.py`: `LazyGoogleSheetsWriter`, `create_app(..., writer=None)` defaulting to it, `app.state.exporter`; error mappings `export_blocked` (409, `details.problems`), `export_not_shared` (403), `sheet_read_only` (403), both with `details.serviceAccountEmail`. Add `GET /activities/{id}/results` and `POST /activities/{id}/export` to `src/quizbuzzer/api/teacher_routes.py`. Make T019 and T020 pass.
- [ ] T024 [US2] Teacher UI in `src/quizbuzzer/static/teacher.html` and `teacher.js`: when the displayed activity is CLOSED, a results panel (from `GET …/results`): units in order, winner, rank list with names and times, 無人作答; an "Export to sheet" button with a confirm stating the answer cells of answered units will be overwritten; show the report ("N cells written, M units had no answer") or the error message with the problem list / service-account email. Escape all text.

**Checkpoint**: full suite green; commit "feat(003): US2".

---

## Phase 5: User Story 3 — Teacher downloads a CSV of all submissions (Priority: P2)

**Goal**: A spreadsheet-safe CSV of every submission slot.

**Independent Test**: spec US3 Independent Test.

### Tests for User Story 3 (write first, observe failing) ⚠️

- [ ] T025 [P] [US3] Write `tests/unit/test_csv_export.py` (**CSV quoting / BOM / formula prefix**): output starts with the UTF-8 BOM bytes `EF BB BF`; header row exact; CRLF line endings; one row per answer slot ordered unit → rank → sub-part; `sub_part` empty for SINGLE; `is_winner` `true`/`false`; `submitted_at` `…+00:00`; answers with `,`, `"`, `\n`, `\r\n` round-trip through `csv.reader` as one field each; each of `=`, `+`, `-`, `@` as the first character gets a leading `'` (and a `-` later in the text does not); Chinese text survives `decode("utf-8-sig")`; zero submissions → header only.
- [ ] T026 [P] [US3] Write `tests/integration/test_csv_api.py`: CLOSED → 200, `text/csv; charset=utf-8`, `Content-Disposition` with `attachment`, `filename="activity-<id>.csv"` and a `filename*=UTF-8''…` whose decoded name has no `\ / : * ? " < > |`; body equals `to_csv` of the results; DRAFT / OPEN → 409 `phase_conflict`; unknown → 404.

### Implementation for User Story 3

- [ ] T027 [US3] Create `src/quizbuzzer/services/csv_export.py: to_csv(results)` (research R6). Make T025 pass.
- [ ] T028 [US3] Add `ResultsService.results_csv(activity_id) -> (bytes, filename)` and `csv_filename(activity_id, title)` in `src/quizbuzzer/services/results_service.py`, and `GET /activities/{id}/results.csv` in `src/quizbuzzer/api/teacher_routes.py`. Make T026 pass.
- [ ] T029 [US3] Teacher UI: a "Download CSV" link in the results panel in `src/quizbuzzer/static/teacher.js`.

**Checkpoint**: full suite green; commit "feat(003): US3".

---

## Phase 6: User Story 4 — Teacher opens results of past CLOSED activities (Priority: P3)

**Goal**: A newest-first list of CLOSED activities whose results can be opened.

**Independent Test**: spec US4 Independent Test.

### Tests for User Story 4 (write first, observe failing) ⚠️

- [ ] T030 [P] [US4] Extend `tests/unit/test_results_service.py` with `list_closed()`: only CLOSED activities, newest first, each with `unit_count` and `submission_count` (data-model.md › PastActivitySummary); empty list when none.
- [ ] T031 [P] [US4] Write `tests/integration/test_past_activities_api.py`: close A, create and close B, create a DRAFT C; `GET /api/teacher/activities/closed` lists B then A (not C) with the contract fields; `GET …/A/results` returns A's results, not B's; empty list when no CLOSED activity. Assert in `tests/integration/test_teacher_guard.py` that `/api/teacher/activities/closed`, `…/results`, `…/export`, `…/results.csv` are in the guarded route set.

### Implementation for User Story 4

- [ ] T032 [US4] Add `db.list_closed_activities(conn)` in `src/quizbuzzer/db.py`, `ResultsService.list_closed()`, and `GET /activities/closed` (declared before `/activities/{activity_id}`) in `src/quizbuzzer/api/teacher_routes.py`. Make T030 and T031 pass.
- [ ] T033 [US4] Teacher UI: a "Past activities" panel in `src/quizbuzzer/static/teacher.html` / `teacher.js` listing title, created date, groups, units, submissions; opening one loads it into the US2 results panel (export and CSV included); "No past activities" when empty.

**Checkpoint**: full suite green; commit "feat(003): US4".

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T034 [P] Write `tests/integration/test_logs_003.py`: run results, export (success and blocked) and CSV with sentinel answers and display names; assert none appears in captured logs at any level (FR-024). Fix any log call that fails it.
- [ ] T035 [P] Extend `tests/integration/test_push_latency.py` (SC-001): with 60 student sockets across 12 groups and submissions in several units, every socket receives the CLOSED `student.state` (members with `results`) within 1 s of `POST …/end` returning. If it fails, cache results once per publish instead of per socket.
- [ ] T036 Run `uv run pytest` and record the result (count, duration, commit) in `docs/verification.md` › Automated test runs (003). Confirm every test-first row has its red entry and its green commit.
- [ ] T037 Code-vs-diagram verification (Principle VIII): compare `src/quizbuzzer/` with `diagrams/system-component.puml`, `domain-class.puml` and every `003-seq-*.puml` (names, calls, routes, status codes) using the plan's Diagram Blueprint. Record a "Feature 003" section in `diagrams/VERIFICATION.md` in the same table format as 001/002. Fix diagrams (or code, when the code breaks the spec), re-render with `java -jar tools/plantuml.jar "./diagrams/*.puml"` (exit 0, a PNG next to every `.puml`), and update `plan.md` › Diagram changes if anything changed.
- [ ] T038 Final consistency pass (Principle VII): `spec.md`, `plan.md`, `contracts/rest-api.md`, `data-model.md`, `quickstart.md` match the shipped behaviour; mark finished tasks done in this file.
- [ ] T039 *(Not in the unattended run.)* `README.md`: add the 003 features (results, export needs Editor access, CSV) to the run instructions. Dependency table unchanged (research R10).
- [ ] T040 *(Human tester; the AI does not mark this done.)* Manual verification M31–M42 from `quickstart.md` §4 on real devices and a real sheet, recorded in `docs/verification.md` › 003 (Principle V).

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (T001–T004) → Foundational (T005–T007) → US1, US2, US3, US4 (any order after Foundational; run in priority order: US1, US2, US3, US4) → Polish.

### Within each story

- Test tasks first, observed failing, then the implementation tasks; the UI task last.

### Key task dependencies

- T004 needs T002 (protocol / `SheetReadOnly`) and adds the `writer` parameter that T023 completes.
- T012 needs T007 (`results_for`) and T011.
- T021 needs T007 and T001; T023 needs T021 and T022.
- T028 needs T027 and T007. T033 needs T024 (results panel).
- T037 needs every implementation task.

### Parallel Opportunities

- T005 with the Setup tests; within each story every test task marked [P]; T022 alongside T021.

## Parallel Example: User Story 2

```text
T014, T015, T016, T017 (tests/unit/test_sheet_exporter.py — one file, write together)
T018 (tests/unit/test_google_sheets_writer.py)
T019 (tests/integration/test_export_api.py)
T020 (tests/integration/test_results_api.py)
then T021 ‖ T022 → T023 → T024
```

## Implementation Strategy

### MVP First (US1 + US2)

Setup → Foundational → US1 (students see results) → US2 (teacher results + export). This
delivers the two P1 stories: the race's outcome is visible and the worksheet gets filled.

### Incremental Delivery

US3 (CSV) and US4 (past activities) each add value independently; commit per phase with the
full suite green.

## Notes

- Never weaken or skip a test to make it pass; after 3 genuine failed fix attempts on one test,
  stop and record it as a blocker.
- Record every decision beyond the task text in spec / contracts / data-model in the same commit.
