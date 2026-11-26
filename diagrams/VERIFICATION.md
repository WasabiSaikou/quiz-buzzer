# Code-vs-Diagram Verification — Feature 001 (Principle VIII)

**Date**: 2026-11-26 · **Scope**: `src/quizbuzzer/` at the end of `/speckit-implement` for 001
(T001–T048) · **Diagrams**: `system-component`, `domain-class`, `001-seq-import-preview`,
`001-seq-confirm-create`, `001-seq-reimport` · **Method**: every element, name, call, route and
status code below was checked by reading the code against the `.puml` source.

**Result**: consistent. Four discrepancies were found. In each case the code followed the spec,
so the diagrams were updated (see the end of this document). Re-rendered with
`java -jar tools/plantuml.jar "./diagrams/*.puml"`, exit code 0. Each PNG was regenerated and the
two most-changed ones (`domain-class`, `system-component`) were inspected visually.

## system-component.puml

| Diagram element | Code | Status |
|---|---|---|
| Teacher UI `static/teacher.html + teacher.js` | `src/quizbuzzer/static/teacher.html`, `teacher.js` | ✅ |
| Student UI `static/student.html + student.js` | not built (later feature, as drawn) | ✅ n/a |
| API server `api/teacher_routes.py`, `api/ws_routes.py` | both exist; routers included in `main.create_app` | ✅ |
| Real-time channel `realtime/hub.py: RealtimeHub` | `RealtimeHub` (connect / disconnect / broadcast / publish_from_thread) | ✅ |
| Activity service `services/activity_service.py: ActivityService` | `ActivityService` | ✅ |
| Guided Notes parser `services/guided_notes_parser.py: parse(grid, merges)` | `parse(grid, merges)`, pure (no I/O imports) | ✅ |
| Sheets adapter: `SheetsAdapter` interface | `services/sheets_adapter.py: SheetsAdapter` (Protocol) | ✅ |
| `GoogleSheetsAdapter services/google_sheets_adapter.py` ..\|> `SheetsAdapter` | `GoogleSheetsAdapter` implements `list_tabs`, `read_tab`, `service_account_email` | ✅ |
| URL parsing `services/sheets_url.py: parse_spreadsheet_url` | exists; called only by `ActivityService` | ✅ |
| SQLite store `db.py + quizbuzzer.db` | `db.py`; file at `QUIZBUZZER_DB_PATH` | ✅ |
| API → ACT "all commands and queries" | routes call only `ActivityService`; `/ws/teacher` reads state via `service.get_current_activity` and registers with the hub | ✅ |
| ACT → SAI `list_tabs(spreadsheet_id)` / `read_tab(spreadsheet_id, sheet_id)` | `ActivityService.list_tabs` / `preview_import` | ✅ |
| ACT → PARSER, ACT → URL, ACT → DB, ACT → RT | `guided_notes_parser.parse` + `compute_fingerprint`; `parse_spreadsheet_url`; `db.transaction`; `hub.publish_from_thread` | ✅ |
| GSAD → Google `spreadsheets.get`, `values.get` (import) | `READ_TAB_FIELDS` / `LIST_TABS_FIELDS`, `values().get(valueRenderOption="FORMATTED_VALUE")`; read-only scope | ✅ (`batchUpdate` is 003) |
| RT ..> Teacher UI WebSocket push | `/ws/teacher` → `activity.state` | ✅ |
| Supporting modules, `LazyGoogleSheetsAdapter` | `main.py`, `config.py`, `api/schemas.py`, `models.py` | ⚠ → diagram updated (D3) |

## domain-class.puml

| Diagram element | Code (`models.py`, `db.py`) | Status |
|---|---|---|
| `Phase {DRAFT, OPEN, CLOSED}` | `Phase` enum; SQL CHECK | ✅ |
| `UnitKind {SINGLE, GROUP_SET}` | `UnitKind` enum; SQL CHECK | ✅ |
| `Activity` id, title, phase, groupCount {2..12}, sourceSpreadsheetId, sourceSheetId, sourceTabTitle | `Activity` dataclass + `activities` table (CHECK 2–12) | ✅ |
| `Activity.createdAt / importedAt : datetime` | `str` ISO-8601 UTC (per data-model.md, TEXT column) | ⚠ → diagram updated (D1) |
| `QuestionUnit` id, number {>0}, kind, sourceRow, position | `QuestionUnit` + `question_units` (CHECK number > 0, UNIQUE number/position) | ✅ |
| `AnswerSlot` id, subPart {>0}, cellRow, cellColumn, a1Ref | `AnswerSlot` + `answer_slots` (CHECK sub_part > 0, UNIQUE(unit_id, sub_part)) | ✅ |
| Activity 1 *-- 1..* QuestionUnit 1 *-- 1..* AnswerSlot | FKs with ON DELETE CASCADE; parser guarantees ≥ 1 slot per unit | ✅ |
| Note: at most one non-CLOSED activity | partial unique index `one_current_activity` + in-transaction check | ✅ |
| Group / Participant / Submission | not created (later features, as drawn) | ✅ n/a |
| Transient types (`ImportPreview`, `TabData`, `Issue`, …) | in `models.py` but not drawn | ⚠ → diagram updated (D2) |

## 001-seq-import-preview.puml

| Step | Code | Status |
|---|---|---|
| `POST /api/teacher/import/tabs {url}` → `list_tabs(url)` | `teacher_routes.import_tabs` → `ActivityService.list_tabs` | ✅ |
| `parse_spreadsheet_url(url)`; invalid → `InvalidSheetUrl` → 400 `invalid_url`, no adapter call | `ActivityService.list_tabs`; handler in `main._register_core_errors` | ✅ |
| `list_tabs(spreadsheet_id)`; 403 → `SheetNotShared` → 403 `not_shared` + email; 404 → `SheetNotFound` → 404; unreachable → `SheetsUnavailable` → 502 | `GoogleSheetsAdapter._execute` + handlers | ✅ (plus: Sheets API disabled → 502, recorded in the contract) |
| 200 tabs + `preselectedSheetId` (#gid= match, else first) | `SpreadsheetInfo.preselected_sheet_id` | ✅ |
| `POST /import/preview {url, sheetId}` → `preview_import(url, sheet_id)` → `read_tab(spreadsheet_id, sheet_id)` (titles + merges, then values) | `ActivityService.preview_import`; `GoogleSheetsAdapter.read_tab` (2 calls) | ✅ |
| `parse(grid, merges)` steps (header, rows, warnings, kinds, issues) | `guided_notes_parser.parse` | ✅ |
| ACT adds identity, `compute_fingerprint(...)` | `ActivityService.preview_import` | ✅ |
| 200 units, slots, issues, totals, fingerprint, canConfirm | `PreviewResponse.from_preview` | ✅ |

## 001-seq-confirm-create.puml

| Step | Code | Status |
|---|---|---|
| `POST /api/teacher/activities` → `create_from_import(...)` | `teacher_routes.create_activity` | ✅ |
| groupCount outside 2–12 → `InvalidGroupCount` → 422 (checked first) | `_validate_group_count` before any read | ✅ |
| `read_tab` → `parse` → identity + fingerprint | `preview_import` | ✅ |
| errors → `ImportHasErrors` 422; fingerprint differs → `PreviewChanged` 409 + preview; warnings unacknowledged → 422 — in this order | `_check_confirmable` (same order) | ✅ |
| `BEGIN IMMEDIATE`; DRAFT/OPEN exists → `ROLLBACK`, `CurrentActivityExists` 409 | `db.transaction` + `_refuse_if_current_exists` (+ IntegrityError fallback = the partial index in the DB note) | ✅ |
| insert activity (DRAFT), units + slots, `COMMIT` | `db.insert_activity`, `db.insert_units_and_slots` | ✅ |
| publish `activity.state` after commit → all teacher sockets; 201 | `_publish` after the transaction; `status_code=201` | ✅ |

## 001-seq-reimport.puml

| Step | Code | Status |
|---|---|---|
| `POST /activities/{id}/reimport/preview` → `preview_reimport` → `check_reimport_allowed` → read phase | `ActivityService.preview_reimport` / `check_reimport_allowed` | ✅ |
| OPEN/CLOSED → `ReimportRefused(phase)` → 409 `reimport_refused` | handler with `details.phase` | ✅ |
| activity missing → `ActivityNotFound` → 404 | implemented, not drawn | ⚠ → diagram updated (D4) |
| DRAFT → `read_tab` → `parse` → 200 preview | `preview_import` | ✅ |
| `PUT /activities/{id}/questions` → `replace_questions` → read, parse, then errors / fingerprint / warnings | `replace_questions` → `_check_confirmable` | ✅ |
| `BEGIN IMMEDIATE`; re-check phase; changed → `ROLLBACK`, 409 | `db.get_activity_phase` inside `db.transaction` | ✅ |
| delete units (slots cascade), insert new, update source + `imported_at`, `COMMIT` | `db.replace_activity_questions` (never touches phase / group_count) | ✅ |
| publish `activity.state`; 200 updated activity | `_publish`; `ActivityResponse` | ✅ |

## Discrepancies and resolutions

| # | Diagram | Discrepancy | Resolution |
|---|---|---|---|
| D1 | domain-class | `createdAt` / `importedAt` typed `datetime`; code and data-model store ISO-8601 UTC strings | Diagram changed to `str {ISO-8601 UTC}` |
| D2 | domain-class | Title says `models.py`, but the transient import types defined there were not drawn | Added a "Transient import types (not stored)" package |
| D3 | system-component | `LazyGoogleSheetsAdapter` (main.py) and the supporting modules (`config.py`, `api/schemas.py`, `models.py`) were not shown | Added two notes; they are wiring/support, not new components |
| D4 | 001-seq-reimport | No branch for a missing activity (`ActivityNotFound` → 404), which the contract specifies | Added the branch at preview time and inside the confirm transaction |

Not discrepancies: the `/ws/teacher` on-connect state and `GET /activities/current` / `/{id}` have
no sequence diagram; they are fully specified in `contracts/websocket.md` and
`contracts/rest-api.md`.
