---

description: "Task list for feature 001 — Import Guided Notes Worksheet"
---

# Tasks: Import Guided Notes Worksheet

**Input**: Design documents from `specs/001-sheets-import/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/rest-api.md](contracts/rest-api.md),
[contracts/websocket.md](contracts/websocket.md), [quickstart.md](quickstart.md)

**Tests**: REQUIRED. Constitution Principle V says core rules must be tested first: Sheets
parsing, the phase rules (create/re-import refusal, one current activity) and fingerprint/confirm.
Write each test task first and **run it to see it fail** before starting the implementation task
it covers.

**Organization**: Tasks are grouped by user story. US1 and US2 are both P1; US2 needs US1's
preview pipeline (confirm re-parses the sheet). US3 (P2) needs US2's stored activity.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: US1 / US2 / US3 (user story phases only)
- All paths are relative to `quiz-buzzer/`. Package root: `src/quizbuzzer/`.

## Conventions used by every task

- Module and class names come from the plan's **Diagram Blueprint** table and must match the
  diagrams exactly (Principle VIII).
- Field constraints are defined once, in [data-model.md](data-model.md). Tasks cite the fields as
  `data-model.md › Entity.field` and do not repeat the rules.
- Issue codes and severities: `data-model.md › Issue codes`. Error envelope and HTTP codes:
  `contracts/rest-api.md › Error envelope`.
- JSON fields are camelCase on the wire and snake_case in Python and SQL.
- Never log cell text or credentials. Log only issue codes and IDs (Principle VI).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and tooling.

- [X] T001 Set up the Python interpreter per research R1. **Do not touch `..\.venv`** (no delete, no recreate, no `UV_PROJECT_ENVIRONMENT`).
  1. Run `uv python find 3.11`.
  2. If it finds nothing, or only MSYS2/mingw interpreters (`C:\msys64\…`, `..\.venv\bin\…`; on 2026-11-26 this machine has only those), run `uv python install 3.11`.
  3. Run `uv python pin 3.11` so that `.python-version` (committed) contains `3.11`.
  4. Verify that `uv python find` now resolves to a uv-managed CPython (under uv's python directory, not `msys64`).

  The project-local `.venv` is created by `uv sync` in T002, as described in quickstart.md §1.
- [X] T002 Create `pyproject.toml` (uv project `quizbuzzer`, `requires-python = ">=3.11"`, src layout with package `src/quizbuzzer`). Runtime deps: fastapi, uvicorn, websockets, python-dotenv, google-api-python-client, google-auth. Dev deps: pytest, httpx. Do **not** use `uvicorn[standard]` (research R10). Set pytest `testpaths = ["tests"]` and `pythonpath = ["src"]`. Run `uv lock` to produce `uv.lock`, then `uv sync` to create the project-local `.venv`. Confirm `uv run python -c "import sys; print(sys.version, sys.platform)"` reports 3.11 on `win32`, not mingw.
- [X] T003 [P] Create the package and test skeleton shown in plan.md › Project Structure: empty `__init__.py` in `src/quizbuzzer/`, `src/quizbuzzer/services/`, `src/quizbuzzer/realtime/` and `src/quizbuzzer/api/`, plus the dirs `src/quizbuzzer/static/`, `tests/fakes/`, `tests/fixtures/sheets/edge_cases/`, `tests/unit/` and `tests/integration/`.
- [X] T004 [P] Create `.env.example` with placeholder values only for `GOOGLE_APPLICATION_CREDENTIALS`, `QUIZBUZZER_DB_PATH` (default `data/quizbuzzer.db`), `QUIZBUZZER_HOST` (default `127.0.0.1`) and `QUIZBUZZER_PORT` (default `8000`), as listed in plan.md › Implementation Notes.
- [X] T005 [P] Extend `.gitignore` with `data/`, `*.db-wal`, `*.db-shm` (SQLite WAL side files are not matched by `*.db`), `.venv/` and `*.egg-info/`. Keep the existing entries.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Domain types, config, DB schema, the adapter interface and its fake, the app factory,
and the test harness. Every story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T006 [P] Implement `src/quizbuzzer/models.py`:
  - enums `Phase` (values per `data-model.md › Activity.phase`) and `UnitKind` (values per `data-model.md › QuestionUnit.kind`);
  - dataclasses `Activity`, `QuestionUnit` and `AnswerSlot`, with the fields of `data-model.md › Activity`, `› QuestionUnit` and `› AnswerSlot` in snake_case;
  - the transient dataclasses `SpreadsheetInfo`, `TabInfo`, `TabData`, `HeaderInfo`, `ParsedSlot`, `ParsedUnit`, `Issue` and `ImportPreview`, per `data-model.md › Transient types`. Field rules come from `data-model.md › Issue.severity`, `› SpreadsheetInfo.requested_gid` (nullable), `› TabData.grid`, `› TabData.merges`, `› ImportPreview.header` (nullable) and `› ImportPreview.can_confirm`.

  No I/O in this module.
- [X] T007 [P] Implement `src/quizbuzzer/config.py`: load `.env` with python-dotenv into a frozen `Settings` (`credentials_path`, `db_path`, `host`, `port`, with the defaults from T004). Read `service_account_email` from the key file's `client_email` (research R5). If the key file is missing, raise a clear error that names the env var, never the file contents.
- [X] T008 Implement `src/quizbuzzer/db.py` `connect(db_path)` and `init_schema(conn)`. Connection settings per research R7: `isolation_level=None`, `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`; create the parent directory if missing. Schema is idempotent `CREATE … IF NOT EXISTS`:
  - table `activities` with the columns and CHECKs of `data-model.md › Activity.id`, `› Activity.phase`, `› Activity.groupCount`, `› Activity.title`, `› Activity.sourceSpreadsheetId`, `› Activity.sourceSheetId`, `› Activity.sourceTabTitle`, `› Activity.createdAt` and `› Activity.importedAt`;
  - the partial unique index `one_current_activity` (`data-model.md › Activity`; exact DDL in research R7);
  - table `question_units` per `data-model.md › QuestionUnit.id`, `› QuestionUnit.activity_id`, `› QuestionUnit.number`, `› QuestionUnit.kind`, `› QuestionUnit.sourceRow` and `› QuestionUnit.position` (FK with cascade, both UNIQUE constraints);
  - table `answer_slots` per `data-model.md › AnswerSlot.id`, `› AnswerSlot.unit_id`, `› AnswerSlot.subPart`, `› AnswerSlot.cellRow`, `› AnswerSlot.cellColumn` and `› AnswerSlot.a1Ref` (FK with cascade, UNIQUE(unit_id, sub_part)).

  Do **not** create the groups/participants/submissions tables (`data-model.md › Later-feature tables`). Add a `transaction(conn)` context manager that runs `BEGIN IMMEDIATE` … `COMMIT`, with `ROLLBACK` on exception.
- [X] T009 [P] Implement `src/quizbuzzer/services/sheets_adapter.py`:
  - a `SheetsAdapter` `Protocol` with `list_tabs(spreadsheet_id) -> SpreadsheetInfo`, `read_tab(spreadsheet_id, sheet_id) -> TabData` and the property `service_account_email`;
  - the exceptions `InvalidSheetUrl`, `SheetNotShared` (carries `service_account_email`), `SheetNotFound` and `SheetsUnavailable`.
- [X] T010 [P] Write `tests/unit/test_sheets_url.py` (must fail first). Cover:
  - an `/edit` URL, an `/edit#gid=918273645` URL, and URLs with `?gid=` / `&gid=` (per research R5);
  - a bare `/d/<id>` URL and surrounding whitespace;
  - rejecting `https://example.com/x`, a Docs (not Sheets) link, a missing id and an empty string.

  Expected: `(spreadsheet_id, gid | None)`, or `InvalidSheetUrl` (FR-002).
- [X] T011 Implement `src/quizbuzzer/services/sheets_url.py` `parse_spreadsheet_url(url) -> tuple[str, int | None]` so that T010 passes. Pure; no network.
- [X] T012 [P] Implement `tests/fakes/fake_sheets_adapter.py` `FakeSheetsAdapter(SheetsAdapter)`. It loads both fixture formats from research R9:
  - `*.json` in the shape `{spreadsheetId, title, tabs:[{sheetId, title, index, grid, merges}]}`;
  - `*.csv` as a single-tab spreadsheet (`spreadsheetId` = `title` = file stem, tab `sheetId` 0 / `"Sheet1"` / index 0, `merges` = []), read with `encoding="utf-8-sig"` and `csv.reader`.

  An unknown `spreadsheet_id` raises `SheetNotFound`, and so does an unknown `sheet_id` in `read_tab` (research R5). It returns `TabData` with `spreadsheet_title` and the tab `title` filled (`data-model.md › TabData.merges`). It supports `fail_with(exc)` to raise `SheetNotShared`, `SheetNotFound` or `SheetsUnavailable`, and `replace_tab(spreadsheet_id, sheet_id, grid, merges)` so tests can mutate a sheet between preview and confirm. Every method must be read-only toward the stored fixtures: a test asserts the fixture grids are byte-identical after any call (FR-005).
- [X] T013 Implement `src/quizbuzzer/api/schemas.py` (pydantic, camelCase aliases via `alias_generator`). Define the request models `ImportTabsRequest`, `PreviewRequest`, `CreateActivityRequest` and `ReplaceQuestionsRequest`; the response models `TabsResponse`, `PreviewResponse`, `ActivityResponse` and `CurrentActivityResponse`; and the `ErrorEnvelope`. All exactly as in `contracts/rest-api.md`. `groupCount` is validated in the service, not in pydantic, so the 422 code is `invalid_group_count` (`data-model.md › Activity.groupCount`).
- [X] T014 Implement `src/quizbuzzer/main.py` `create_app(adapter=None, db_path=None)`. It builds `Settings`, runs `init_schema` at startup, sets `app.state.hub = None` (the real `RealtimeHub` is wired in T037), mounts `static/` and serves `GET /teacher` → `static/teacher.html`. It registers exception handlers that map the adapter and service exceptions to the error envelope and status codes in `contracts/rest-api.md › Error envelope`; `SheetNotShared` includes `details.serviceAccountEmail` (FR-004). Module-level `app = create_app()` builds a `GoogleSheetsAdapter` lazily, only when no adapter is injected.
- [X] T015 Implement `tests/conftest.py` fixtures:
  - `fake_adapter` (a `FakeSheetsAdapter` loaded from `tests/fixtures/sheets/`);
  - `db_path` (a file under `tmp_path`, so concurrency tests can open several connections);
  - `app` / `client` (`create_app(adapter=fake_adapter, db_path=db_path)` + `TestClient`);
  - `load_grid(name)` for edge-case grids.

**Checkpoint**: `uv run pytest tests/unit/test_sheets_url.py` passes and the app factory starts
with the fake adapter.

---

## Phase 3: User Story 1 — Preview the questions detected in a worksheet (Priority: P1) 🎯 MVP

**Goal**: Paste a link and pick a tab (the `#gid=` tab or the first tab). The teacher then sees
every detected question with its number, type, sub-part count and answer cell, plus the errors
and warnings. The sheet is never written.

**Independent Test**: Run `uv run pytest tests/unit/test_guided_notes_parser.py
tests/integration/test_import_api.py`. Then do manual M2–M5 in quickstart.md: paste a course
template link and compare the preview with the known questions, sub-parts and cells.

### Fixtures for User Story 1

- [X] T016 [P] [US1] Create `tests/fixtures/sheets/shifted_layout.json` (synthetic; research R9). It needs:
  - a header that is lower and further right, with tab title `練習`;
  - merged question-text cells, a horizontally merged answer cell and a vertically merged 題號 cell;
  - full-width markers `（１）` and mixed `（1)`, and blank spacer rows inside a 題組;
  - a numbered row that is an implicit sub-part 1 (next marker `（2）`);
  - a numbered row followed by `（1）` (so it is not a slot);
  - every number form `1`, `2.`, `3、`, `Q4`, `q5` and `６`.

  Add a second tab so tab selection is tested. Write the expected results by hand in `tests/fixtures/sheets/shifted_layout.expected.json` (format in research R9).
- [X] T017 [P] [US1] Write the hand-checked expected results for the two team-supplied course templates, `tests/fixtures/sheets/template_single.csv` and `template_group.csv` (present; no personal data per the team; research R9). Do not edit the CSVs. Use the format from research R9. Values, read from the CSVs:
  - `template_single.expected.json`: header `{row: 4, numberColumn: 2, answerColumn: 7}`; units 1–6, all `SINGLE`, `sourceRow` 5, 7, 9, 11, 13, 15, each with one slot `subPart` 1 at `G5`, `G7`, `G9`, `G11`, `G13`, `G15`; totals `{units: 6, slots: 6}`; `issueCodes: []`.
  - `template_group.expected.json`: the same header. Unit 1 is `GROUP_SET`, `sourceRow` 5, slots (1, `G5`), (2, `G6`); the numbered row holds its own `（1）` marker (research R4 rule 1). Unit 2 is `GROUP_SET`, `sourceRow` 8, slots (1, `G8`), (2, `G9`). Unit 3 is `SINGLE` at `G11`; unit 4 is `SINGLE` at `G13`. Totals `{units: 4, slots: 6}`; `issueCodes: []`. A marker-only cell gives no `slot_cell_has_text`, and the title row 2 above the header is not scanned.
- [X] T018 [P] [US1] Create small edge-case grids, one per file, in `tests/fixtures/sheets/edge_cases/`:
  - header: `no_header`, `header_whitespace` (`題 號`, `作　答`, a line break inside a label), `header_extra_chars` (`作答區`), `header_split_rows`, `header_duplicate_label`;
  - question numbers: `duplicate_numbers`, `number_gap`, `numbers_out_of_order`, `unrecognised_numbers` (`備註`, `0`, `-1`, `1.5`, `一`), `fullwidth_q_and_dot` (`Ｑ1`, `1．`; research R3), `zero_questions`;
  - sub-parts: `stray_answer_text`, `slot_cell_has_text` (`答：`, `______`, `（2）______`, plus a marker-only cell that must produce no warning), `duplicate_sub_part`, `sub_part_gap`, `orphan_sub_part`;
  - layout: `single_empty_answer`, `spacer_rows_in_group`, `merged_answer_cell`, `ragged_rows`.

### Tests for User Story 1 (write first, observe failing) ⚠️

- [X] T019 [P] [US1] Write `tests/unit/test_guided_notes_parser.py`.
  - **Fixtures:** parametrize over the 3 reference sheets `template_single.csv`, `template_group.csv` and `shifted_layout.json` (T016, T017), loaded through `FakeSheetsAdapter`. For each, assert the header, units, kinds, sub-part counts, slot `(sub_part, a1_ref)`, totals and issue codes against `<stem>.expected.json` (SC-002, FR-012, FR-017, FR-018; Principle II ≥ 3 shapes).
  - **Edge-case grids:** for each T018 grid, assert the exact issue `code` and `severity` (`data-model.md › Issue codes`), plus the `rows` and `cells`. Also assert the message names the row or cell and the fix (FR-016, SC-004).
  - **Header rules:** the topmost header row wins, labels match exactly after removing whitespace, and `header_not_found` names both 題號 and 作答 (FR-006). `header_split_rows` gives `header_not_found` naming both found cells, and `header_duplicate_label` gives `header_ambiguous` naming the duplicate cells (`data-model.md › Issue codes`).
  - **Detection rules:** the number forms of FR-008 and research R3, and the 4 sub-part rules of research R4 (FR-009–FR-011).
  - **Cell behaviour:** blank rows don't end a question (FR-014); stray text gives a warning and no slot (FR-014a); a slot cell with extra text gives a warning, a marker-only or empty cell none (FR-011a).
  - **Merges:** a merged answer cell resolves to its top-left; a vertical 題號 merge counts once (research R2).
  - **No fixed addresses:** the same grid shifted by +3 rows and +2 columns yields the same units with shifted cells (FR-007).
  - **Kind and confirmability:** `kind = GROUP_SET` ⇔ slot count ≥ 2 (`data-model.md › QuestionUnit.kind`); `can_confirm` is false exactly when an error exists.
- [X] T020 [P] [US1] Write `tests/unit/test_fingerprint.py`. The fingerprint (research R6):
  - is stable across calls;
  - changes when any unit number, kind, source row, slot sub-part, row or column changes, or when `spreadsheetId` or `sheetId` changes;
  - does **not** change when only issue messages or warnings change, or when unrelated cell text (e.g. question text) changes.
- [X] T021 [P] [US1] Write the preview cases in `tests/unit/test_activity_service.py`:
  - `list_tabs` preselects the `#gid=` tab when it exists, otherwise index 0, and an unknown gid falls back to index 0 (FR-003);
  - `preview_import` returns the parser result enriched with `spreadsheet_id`, `sheet_id`, `tab_title`, `spreadsheet_title` and `fingerprint`;
  - an invalid URL raises `InvalidSheetUrl` and the fake records zero calls (FR-002);
  - the adapter receives the `spreadsheet_id` parsed from the URL, never the raw URL;
  - an unknown `sheet_id` raises `SheetNotFound`;
  - the adapter errors propagate unchanged.
- [X] T022 [P] [US1] Write `tests/integration/test_import_api.py` against `contracts/rest-api.md`:
  - `POST /api/teacher/import/tabs` gives 200 with `preselectedSheetId`;
  - `POST /api/teacher/import/preview` gives 200 with the full preview shape, including a preview that contains errors (`canConfirm: false`);
  - picking another tab rebuilds the preview from that tab only (US1 AS4);
  - error statuses: 400 `invalid_url`, 403 `not_shared` with `details.serviceAccountEmail`, 404 `not_found`, 502 `sheets_unavailable`;
  - after every call the fake's fixture grids are unchanged (FR-005, US1 AS8).

### Implementation for User Story 1

- [X] T023 [US1] Implement `src/quizbuzzer/services/guided_notes_parser.py` `parse(grid, merges) -> ImportPreview` so that T019 passes. Keep it pure (no I/O, no Google types). Follow research R2 (merge handling), R3 (NFKC normalisation and the regexes) and R4 (sub-part assignment). Compute `a1Ref` from the 1-based row/column with a `to_a1(row, col)` helper (`data-model.md › AnswerSlot.a1Ref`, `› AnswerSlot.cellRow`, `› AnswerSlot.cellColumn`); never use literal addresses. `sourceRow` is the numbered row (`data-model.md › QuestionUnit.sourceRow`). Units keep sheet row order (`data-model.md › QuestionUnit.position`). `header` is `None` when `header_not_found` (`data-model.md › ImportPreview.header`), and `can_confirm` is true iff there are no error-severity issues (`data-model.md › ImportPreview.can_confirm`).
- [X] T024 [US1] Add the pure helper `compute_fingerprint(spreadsheet_id, sheet_id, units) -> str` in `src/quizbuzzer/services/guided_notes_parser.py` (SHA-256 of canonical JSON per research R6) so that T020 passes. `parse()` does not call it; `ActivityService` does (sequence diagrams).
- [X] T025 [US1] Implement `src/quizbuzzer/services/google_sheets_adapter.py` `GoogleSheetsAdapter(SheetsAdapter)` per research R5:
  - read-only scope credentials from `Settings.credentials_path`;
  - `list_tabs(spreadsheet_id)` and `read_tab(spreadsheet_id, sheet_id)` with the exact `fields`, quoted ranges and `FORMATTED_VALUE` rendering. `read_tab` makes one `spreadsheets.get` (titles + merges) and one `values.get`, and an unknown `sheet_id` raises `SheetNotFound`;
  - a 10 s timeout. It maps HttpError 403 → `SheetNotShared`, 404 → `SheetNotFound`, and anything else or a timeout → `SheetsUnavailable`. Convert the API merges to 0-based half-open tuples (`data-model.md › TabData.merges`). No unit test hits Google; it is verified manually (M1, M3).
- [X] T026 [US1] Implement `ActivityService.list_tabs(url)` and `ActivityService.preview_import(url, sheet_id)` in `src/quizbuzzer/services/activity_service.py`, following `diagrams/001-seq-import-preview.puml`. The constructor takes `(adapter, db_path, hub=None)`; the hub is first used in US2. Both methods first call `sheets_url.parse_spreadsheet_url(url)`, so an invalid URL raises before any adapter call. Then they call the adapter with the `spreadsheet_id`. `preview_import` then calls `guided_notes_parser.parse`, adds identity from `TabData`, and calls `compute_fingerprint` (`data-model.md` › parse note). T021 must pass.
- [X] T027 [US1] Implement `POST /api/teacher/import/tabs` and `POST /api/teacher/import/preview` in `src/quizbuzzer/api/teacher_routes.py`. Use an `APIRouter` with prefix `/api/teacher` and plain `def` handlers (research R8). Wire the router and the `ActivityService` instance in `create_app` in `src/quizbuzzer/main.py`. T022 must pass.
- [X] T028 [US1] Build the preview part of `src/quizbuzzer/static/teacher.html` and `src/quizbuzzer/static/teacher.js` (no build step, plain ES modules):
  - URL input → `/import/tabs` → a tab `<select>` that defaults to `preselectedSheetId`;
  - a tab change → `/import/preview`;
  - a table of the units (number, SINGLE/題組, sub-part count, each slot as `tabTitle!A1`, FR-017) and the totals (FR-018);
  - an issue list split into errors and warnings, each showing its message, rows and cells;
  - error envelope messages displayed as text, including the service account email for `not_shared` (FR-004).

  Render all sheet text with `textContent`, never `innerHTML`.

**Checkpoint**: US1 is fully functional. Tests T019–T022 pass (except the template fixtures still
skipped under T017), and the teacher can preview any shared sheet.

---

## Phase 4: User Story 2 — Confirm the preview to create a DRAFT activity (Priority: P1)

**Goal**: With an error-free preview, the teacher picks 2–12 groups and confirms, after
acknowledging any warnings. This atomically creates the single current DRAFT activity, holding
exactly the confirmed questions and slots, and pushes `activity.state` to teacher sockets.

**Independent Test**: Run `uv run pytest tests/unit/test_activity_service.py
tests/integration/test_one_current_activity_concurrency.py tests/integration/test_ws_teacher.py`.
Then do manual M6, M7 and M9: confirm with 6 groups, reopen the activity and compare it with the
preview.

### Tests for User Story 2 (write first, observe failing) ⚠️

- [X] T029 [P] [US2] Add the create cases to `tests/unit/test_activity_service.py`:
  - **Success (US2 AS1):** `create_from_import` stores exactly the re-parsed units and slots, with phase DRAFT, the chosen group count, the title format and source fields (`data-model.md › Activity.title`, `› Activity.sourceSheetId`, `› Activity.sourceTabTitle`), and server-clock `createdAt` = `importedAt` (`data-model.md › Activity.createdAt`).
  - **Refusals:**
    - group count 1, 13 or a non-int raises `InvalidGroupCount` (FR-019, `data-model.md › Activity.groupCount`, US2 AS4);
    - an import with errors raises `ImportHasErrors` with the preview attached (US2 AS2);
    - warnings without acknowledgement raise `WarningsNotAcknowledged`, and with acknowledgement it succeeds (US2 AS3);
    - a sheet changed after the preview (via `replace_tab`) raises `PreviewChanged` with the new preview, and no rows are written (FR-022, US2 AS5). If the changed sheet now has errors, `ImportHasErrors` is raised instead (errors are checked first, per `diagrams/001-seq-confirm-create.puml`);
    - an existing DRAFT or OPEN activity raises `CurrentActivityExists` carrying `{id, title, phase}` (FR-020a, US2 AS6).
  - **Other activities:** CLOSED activities exist and stay byte-identical after a create (US2 AS7).
  - **Atomicity:** a failure injected after the unit inserts leaves zero rows (FR-023).
  - **Reads:** `get_current_activity` returns `None` or the activity; `get_activity(id)` raises not-found for an unknown id.
- [X] T030 [P] [US2] Write `tests/integration/test_one_current_activity_concurrency.py`. Two threads, each with its own `ActivityService` connection to the same file DB, call `create_from_import` simultaneously behind a `threading.Barrier`. Exactly one succeeds, the other gets `CurrentActivityExists`, and `SELECT count(*) … WHERE phase IN ('DRAFT','OPEN')` = 1. Also assert that a raw second DRAFT `INSERT` that bypasses the service fails on the `one_current_activity` index (research R7).
- [X] T031 [P] [US2] Add the create API cases to `tests/integration/test_import_api.py`:
  - `POST /api/teacher/activities` gives 201 with the `Activity` shape;
  - error statuses: 422 `invalid_group_count`, 422 `import_errors`, 422 `warnings_not_acknowledged`, 409 `preview_changed` with `details.preview`, 409 `current_activity_exists` with `details.activity`;
  - `GET /api/teacher/activities/current` returns `{activity: null}` or the activity, and `GET /api/teacher/activities/{id}` returns the activity or 404.
- [X] T032 [P] [US2] Write `tests/integration/test_ws_teacher.py` against `contracts/websocket.md`:
  - on connect, `/ws/teacher` immediately receives `activity.state` (`null` when there is none);
  - after `POST /api/teacher/activities`, every connected teacher socket (two sockets) receives `activity.state` with the summary shape;
  - client frames are ignored;
  - a disconnected socket is dropped from the hub without errors.

### Implementation for User Story 2

- [X] T033 [US2] Add the activity queries to `src/quizbuzzer/db.py`: `insert_activity`, `insert_units_and_slots`, `find_current_activity`, `get_activity_with_units` (ordered by `position`, then `sub_part`) and `list_closed_activity_ids` (for tests). Column mapping per `data-model.md › Activity`, `› QuestionUnit` and `› AnswerSlot`. Timestamps are ISO-8601 UTC from the server clock (`data-model.md › Activity.createdAt`, `› Activity.importedAt`).
- [X] T034 [US2] Implement `src/quizbuzzer/realtime/hub.py` `RealtimeHub`:
  - `connect(ws)`, `disconnect(ws)`, `async broadcast(message)` (skips and drops dead sockets);
  - `publish_from_thread(message)` using `anyio.from_thread.run` (research R8);
  - `activity_state_message(activity | None)` building the `contracts/websocket.md` summary.
- [X] T035 [US2] In `src/quizbuzzer/services/activity_service.py`, define the exceptions `InvalidGroupCount`, `ImportHasErrors`, `PreviewChanged`, `WarningsNotAcknowledged` and `CurrentActivityExists` (plan › Diagram Blueprint). Then implement `create_from_import(url, sheet_id, group_count, fingerprint, acknowledge_warnings)` following `diagrams/001-seq-confirm-create.puml`:
  1. Validate the group count (`data-model.md › Activity.groupCount`).
  2. Re-read the sheet and re-parse it; never trust client-sent cells (research R6).
  3. Check, in the diagram's order: errors (`ImportHasErrors`), then the fingerprint (`PreviewChanged`), then the warning acknowledgement (`WarningsNotAcknowledged`).
  4. Inside `db.transaction` (`BEGIN IMMEDIATE`), check for a current activity and insert the activity, units and slots. The title is built per `data-model.md › Activity.title` from `TabData.spreadsheet_title` and the tab title.
  5. Commit, then `hub.publish_from_thread(activity.state)`. Skip the publish when `hub is None`, so unit tests can run without a hub.

  Also implement `get_current_activity()` and `get_activity(id)`. T029 and T030 must pass.
- [X] T036 [US2] Implement `POST /api/teacher/activities`, `GET /api/teacher/activities/current` and `GET /api/teacher/activities/{id}` in `src/quizbuzzer/api/teacher_routes.py`. Add handlers for the new service exceptions in `src/quizbuzzer/main.py`, mapped per `contracts/rest-api.md › Error envelope`. T031 must pass.
- [X] T037 [US2] Implement `src/quizbuzzer/api/ws_routes.py` `/ws/teacher`: accept the connection, register it with `RealtimeHub`, send the current `activity.state` from the DB, ignore incoming frames, and unregister on disconnect. Create the hub in `create_app` (`src/quizbuzzer/main.py`) and pass it to `ActivityService`. T032 must pass.
- [X] T038 [US2] Extend `src/quizbuzzer/static/teacher.html` and `teacher.js` with:
  - a group-count number input prefilled with 4, range 2–12 (spec Assumptions); the server is still authoritative;
  - a confirm button disabled while `canConfirm` is false, and a warnings acknowledgement checkbox that is required when warnings exist;
  - handling for `preview_changed`, which re-renders `details.preview`, and for `current_activity_exists`, which names the activity and its phase and suggests re-import (DRAFT) or closing it (OPEN);
  - a "current activity" panel driven by `/ws/teacher` `activity.state` that fetches details via `GET /activities/{id}`, so a second tab updates without reloading (M6).

  When an activity is current, show it instead of the new-import form.

**Checkpoint**: US1 and US2 both work. One current DRAFT activity can be created from a confirmed
preview, and concurrent confirms cannot create two.

---

## Phase 5: User Story 3 — Re-import into a DRAFT activity (Priority: P2)

**Goal**: While the activity is DRAFT, the teacher can preview any sheet or tab and confirm. This
replaces the entire question set atomically and leaves phase and group count unchanged. Re-import
is refused for OPEN or CLOSED activities, checked again at confirm time.

**Independent Test**: Run `uv run pytest tests/integration/test_reimport_api.py` and the re-import
cases in `tests/unit/test_activity_service.py`. Then do manual M8.

### Tests for User Story 3 (write first, observe failing) ⚠️

- [X] T039 [P] [US3] Add the re-import cases to `tests/unit/test_activity_service.py`:
  - **Success:** with 5 questions stored, re-importing a 7-question tab stores exactly those 7, with no old unit or slot ids left (US3 AS1). The source fields update to the new sheet and tab, `importedAt` updates, and `createdAt`, phase and `groupCount` are unchanged (FR-025, US3 AS2; `data-model.md › Activity.importedAt`, `› Activity.groupCount`).
  - **Phase refusals:** an OPEN or CLOSED activity (set via direct SQL as test setup) raises `ReimportRefused` from both `check_reimport_allowed`/`preview_reimport` and `replace_questions`, and the questions stay unchanged (US3 AS3, SC-006). An activity switched to OPEN between `preview_reimport` and `replace_questions` is refused at confirm time (FR-026, US3 AS4).
  - **Other refusals:** `PreviewChanged`, `ImportHasErrors` and `WarningsNotAcknowledged` apply exactly as in create.
  - **Atomicity:** an injected failure mid-replace leaves the old question set intact (FR-024).
- [X] T040 [P] [US3] Write `tests/integration/test_reimport_api.py`:
  - `POST /api/teacher/activities/{id}/reimport/preview` gives 200 with the preview shape, or 409 `reimport_refused` with `details.phase`;
  - `PUT /api/teacher/activities/{id}/questions` gives 200 with the updated `Activity`, or 409 `reimport_refused`, 409 `preview_changed`, 422 `import_errors`, 422 `warnings_not_acknowledged`, or 404 for an unknown id. An unknown id also gives 404 on `reimport/preview`;
  - a connected `/ws/teacher` socket receives `activity.state` after a successful replace.

### Implementation for User Story 3

- [X] T041 [US3] Add `replace_activity_questions(conn, activity_id, source fields, imported_at, units)` to `src/quizbuzzer/db.py`. It deletes the units (slots cascade), inserts the new units and slots, and updates the source fields and `imported_at` only, never phase or group count (`data-model.md › Activity.sourceSpreadsheetId`, `› Activity.sourceSheetId`, `› Activity.sourceTabTitle`, `› Activity.importedAt`). It does not run a transaction itself; the caller wraps it in one.
- [X] T042 [US3] Implement the exception `ReimportRefused` (carries the phase), then `check_reimport_allowed(activity_id)`, `preview_reimport(activity_id, url, sheet_id)` and `replace_questions(activity_id, url, sheet_id, fingerprint, acknowledge_warnings)` in `src/quizbuzzer/services/activity_service.py`, following `diagrams/001-seq-reimport.puml`. `replace_questions` re-checks the phase **inside** `db.transaction` before writing (FR-026), then publishes `activity.state` after commit. T039 must pass.
- [X] T043 [US3] Implement `POST /api/teacher/activities/{id}/reimport/preview` and `PUT /api/teacher/activities/{id}/questions` in `src/quizbuzzer/api/teacher_routes.py`. Map `ReimportRefused` → 409 `reimport_refused` with `details.phase` in `src/quizbuzzer/main.py`. T040 must pass.
- [X] T044 [US3] Extend `src/quizbuzzer/static/teacher.js` and `teacher.html`. On the current-activity panel, show a "Re-import" action only when the phase is DRAFT. It reuses the URL, tab and preview UI against the re-import endpoints, shows a replace-confirmation with the old and new totals, and displays `reimport_refused` with the phase.

**Checkpoint**: All three stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Constitution gates (Principles V–VIII), documentation, and validation.

- [ ] T045 [P] Write `README.md`: purpose, Windows setup (the venv per research R1, `uv sync`, `.env` from `.env.example`, sharing sheets with the service account), and run and test commands (from quickstart.md). Include the direct-dependency/licence table from research R10, with a pointer to `uv.lock` (Principle VII). **Open — deferred by the team (2026-11-26): README kept minimal until the end; the licence table is still required before merge.**
- [X] T046 [P] Add a log-hygiene test in `tests/integration/test_import_api.py`. Use `caplog` across the preview, create and re-import flows with a fixture containing a sentinel cell text, and assert that neither the sentinel nor the credentials path appears in any log record (Principle VI).
- [X] T047 [P] Add a performance check in `tests/integration/test_import_api.py`. A synthetic 200-row grid through `/import/preview` with the fake adapter must finish in well under 5 s (parse budget for SC-001). Record the real-Google timing during manual M3 in `docs/verification.md`.
- [X] T048 Run `uv run pytest` and confirm that everything passes, with no skips; the parser suite covers all 3 reference sheets. Each Principle V test file must have been seen failing before its implementation: note this in the commit messages or in `docs/verification.md`.
- [X] T049 Run manual scenarios M1–M10 from `quickstart.md` against a real shared sheet. Record each one (date, tester, steps, observed result) in `docs/verification.md`, including M10, the version-history check for zero service-account edits (FR-005, SC-005), and SC-003 (paste → DRAFT activity in under 2 minutes). **Done 2026-11-26: all ten recorded as passing on `e135676` (commit `8336eec`).**
- [X] T050 Code-vs-diagram check (Principle VIII). Compare `src/quizbuzzer/` with `diagrams/system-component.puml`, `domain-class.puml` and `001-seq-*.puml`: module, class, method and exception names, participants and HTTP routes and codes. Fix the code or update the diagrams, then re-render with `java -jar tools/plantuml.jar "./diagrams/*.puml"` (exit 0) and record the result in `diagrams/VERIFICATION.md`.
- [X] T051 Run `/speckit-analyze`, or review by hand that every FR-001–FR-026 and SC-001–SC-006 maps to at least one passing test or `docs/verification.md` record. List any gaps in `docs/verification.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 (interpreter + pin) comes before T002's `uv lock`/`uv sync`. T003–T005
  can be done at any time.
- **Foundational (Phase 2)**: depends on Setup and blocks every story.
- **US1 (Phase 3)**: depends on Foundational.
- **US2 (Phase 4)**: depends on Foundational, plus US1's parser, fingerprint and `preview_import`
  (T023, T024, T026), because confirm re-parses the sheet. US2 test writing (T029–T032) can
  start as soon as Phase 2 is done.
- **US3 (Phase 5)**: depends on US2 (a stored DRAFT activity, `db.transaction` writes, the hub
  publish).
- **Polish (Phase 6)**: depends on all three stories.

### Within-story order

Fixtures → tests (see them fail) → db and models → service → routes and WebSocket → static UI.

### Key task dependencies

- T008 → T033 → T041 (all edit `db.py`; run them in sequence)
- T011, T012, T015 → T021, T022
- T016/T018 → T019 → T023 → T024 → T026 → T027 → T028
- T026 + T033 + T034 → T035 → T036 → T037 → T038
- T035 → T042 → T043 → T044
- Several tasks edit `activity_service.py`, `teacher_routes.py`, `main.py`, `teacher.js` and
  `test_activity_service.py`. Tasks that touch the same file are never marked [P] against each
  other.

### Parallel Opportunities

- Phase 1: T003, T004, T005
- Phase 2: T006, T007, T009, T010, T012 (then T011, T013, T014, T015)
- US1: fixtures T016, T017, T018 together; then tests T019, T020, T021, T022 together
- US2: tests T029, T030, T031, T032 together (T029 and T031 add to existing files but don't
  conflict with the other two)
- US3: tests T039, T040 together
- Polish: T045, T046, T047

---

## Parallel Example: User Story 1

```text
# Fixtures together:
Task: "T016 Create tests/fixtures/sheets/shifted_layout.json"
Task: "T018 Create edge-case grids in tests/fixtures/sheets/edge_cases/"

# Then all US1 tests together (each must fail first):
Task: "T019 tests/unit/test_guided_notes_parser.py"
Task: "T020 tests/unit/test_fingerprint.py"
Task: "T021 preview cases in tests/unit/test_activity_service.py"
Task: "T022 tests/integration/test_import_api.py"
```

## Parallel Example: User Story 2

```text
Task: "T029 create cases in tests/unit/test_activity_service.py"
Task: "T030 tests/integration/test_one_current_activity_concurrency.py"
Task: "T031 create API cases in tests/integration/test_import_api.py"
Task: "T032 tests/integration/test_ws_teacher.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup.
2. Phase 2 Foundational.
3. Phase 3 US1. **Stop and validate**: the parser passes against `shifted_layout` and all
   edge-case grids, and the preview works on a real shared sheet (M2–M5). This already delivers
   value as a check that a worksheet is compatible.

### Incremental Delivery

1. Add US2 → validate M6, M7, M9 and the concurrency test. A teacher can now create the activity
   (the minimum needed for a class session, together with later features).
2. Add US3 → validate M8.
3. Polish → full M1–M10 records, README, diagram check.

---

## Notes

- Commit after each task or logical group, using Conventional Commits (e.g. `test(001): parser
  edge cases (red)`, `feat(001): guided notes parser`).
- Access control is **not** part of this feature: feature 002 adds the passcode as a router
  dependency on `/api/teacher` and `/ws/teacher`.
- Do not create the student page, the student socket or the groups/submissions tables here.
