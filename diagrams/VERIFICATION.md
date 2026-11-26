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


---

# Code-vs-Diagram Verification — Feature 002 (Principle VIII)

**Date**: 2026-11-27 · **Scope**: `src/quizbuzzer/` after `/speckit-implement` for 002 (T001–T051;
README T052 and the manual checks T054 left to a human) · **Diagrams**: `system-component`,
`domain-class`, `002-seq-teacher-unlock`, `002-seq-open-activity`, `002-seq-join`, `002-seq-submit`,
`002-seq-end-activity`, `002-seq-cancel-activity`, `002-seq-reconnect` · **Method**: every element,
name, call, route, status code and message type below was checked by reading the code against the
`.puml` source.

**Result**: consistent after 7 diagram corrections (E1–E7) and the earlier implementation-time
change E0. In every case the code follows the spec and contracts, so the diagrams were updated.
Re-rendered with `java -jar tools/plantuml.jar "./diagrams/*.puml"` (exit 0, 12/12 PNGs fresh);
`system-component` and `002-seq-submit` were inspected visually.

## system-component.puml

| Diagram element | Code | Status |
|---|---|---|
| Teacher UI `static/teacher.html + teacher.js` (passcode unlock, import, open / end / cancel, live dashboard) | lock form, Open / End / Cancel with `confirm()`, `renderDashboard`, closed view | ✅ |
| Student UI `static/student.html + student.js` (join, wait, answer, own-group view, closed) | five screens rendered from `student.state`; reconnect 0.5 s → 5 s | ✅ |
| `api/auth_routes.py POST /api/teacher/session` | `create_session` | ✅ |
| `api/teacher_routes.py /api/teacher/*` | 001 routes + `open_activity`, `end_activity`, `cancel_activity`, `get_dashboard` | ✅ |
| `api/student_routes.py /api/student/*` | `get_state`, `join`, `leave`, `submit` | ✅ |
| `api/ws_routes.py /ws/teacher, /ws/student` | `teacher_socket`, `student_socket` | ✅ |
| Teacher guard `api/auth.py: require_teacher (TeacherSessions)`; TR → AUTH "every route, before routing (TeacherGuardMiddleware)" | `TeacherGuardMiddleware` added in `create_app`; `require_teacher` also called by `/ws/teacher` | ✅ (E0) |
| Real-time channel: teacher sockets; student sockets keyed by StudentKey or None | `RealtimeHub.teachers`, `.students: dict[WebSocket, StudentKey \| None]`, `student_sockets(activity_id, group_number)` | ✅ |
| Activity service (import, open, end, cancel DRAFT, dashboard) | `open_activity`, `end_activity`, `cancel_activity`, `get_dashboard`, `get_displayed_activity`, `publish_teacher_state`, `publish_dashboard` | ✅ |
| Participation service (join, leave, submit, group state) | `join`, `leave`, `submit`, `resolve_key`, `student_state`, `publish_student_states`, `publish_group_state` | ✅ |
| Visibility filter `student_view(...)` | `student_view(activity, participant, members, own_submissions)` | ⚠ → diagram updated (E1) |
| ACT → PART `publish_student_states()` after create / re-import / open / end / cancel | `ActivityService._publish_students` → `student_publisher` | ✅ |
| PART → RT "dashboard.state after join / leave / submit" | dashboard goes PART → `teacher_publisher` = `ActivityService.publish_dashboard` → hub | ⚠ → diagram updated (E2) |
| PART → VIS "every student-bound response and push"; ACT never calls VIS | only `participation_service.py` imports `student_view` | ✅ |
| ACT / PART → DB atomic transactions | `db.transaction` (BEGIN IMMEDIATE) in every write | ✅ |
| Notes: passcode required at startup, HttpOnly session cookie, in memory until restart; PART is the sole rank authority; group only from the cookie | `config.load_settings` / `create_app` refuse blank passcode; `TeacherSessions`; `ParticipationService.submit`; `_member_in_tx` | ✅ |

## domain-class.puml

| Diagram element | Code (`models.py`, `db.py`) | Status |
|---|---|---|
| `Group <<value>> {number}`; no table | no `groups` table; `participants.group_number`, `submissions.group_number` | ✅ |
| `Participant {id, displayName, joinedAt, tokenHash}` | `participants` table has all four; the `Participant` dataclass omits `token_hash` on purpose (only db.py and the service see it) and adds `activity_id`, `group_number` (the relationships) | ✅ |
| `Submission {id, rank, receivedAt, isWinner()}` | table + dataclass (`is_winner` property); the dataclass also carries read-only `unit_number`, `submitted_by` from joins | ✅ |
| `SubmissionAnswer {text}`; `for slot` → AnswerSlot | `submission_answers (submission_id, slot_id, text)`; dataclass adds `sub_part` from the join | ✅ |
| Constraints note: `UNIQUE(unit_id, group_number)`, `UNIQUE(unit_id, rank)`, BEGIN IMMEDIATE | `db.SCHEMA` | ✅ |
| Activity note: cancel deletes units, slots, participants | `ON DELETE CASCADE` on `question_units`, `participants`; `test_deleting_an_activity_cascades_to_all_002_rows` | ✅ |
| In memory: `TeacherSessions {tokens, create, is_valid}` | `api/auth.py: TeacherSessions` | ✅ |
| `StudentKey` (in `models.py`, used by the hub) | `models.StudentKey` NamedTuple — not drawn | ⚠ → diagram updated (E3) |

## 002-seq-teacher-unlock.puml

| Step | Code | Status |
|---|---|---|
| GET `/activities/current` without cookie → `require_teacher` → `TeacherRequired` → 401 `teacher_required` | `TeacherGuardMiddleware` (before routing) | ✅ |
| POST `/api/teacher/session` → `create(passcode)` constant-time → `WrongPasscode` 401 / 204 + `Set-Cookie qb_teacher` HttpOnly, SameSite=Strict | `auth_routes.create_session`, `TeacherSessions.create` (`hmac.compare_digest`) | ✅ |
| then GET current → `get_displayed_activity()`; `/ws/teacher` → `require_teacher` → accept; `activity.state` + dashboard | `teacher_routes.current_activity`, `ws_routes.teacher_socket` | ✅ |
| Student calls any teacher route → 401, no data; `/ws/teacher` without cookie → close 4401 | `test_teacher_guard.py` (walks every route) | ✅ |

## 002-seq-open-activity.puml / 002-seq-end-activity.puml

| Step | Code | Status |
|---|---|---|
| POST `…/open` / `…/end` → guard → `open_activity` / `end_activity` | `ActivityService._transition` | ✅ |
| BEGIN IMMEDIATE; read phase; missing → 404; wrong phase → `PhaseConflict` 409 + `details.phase`; else `UPDATE phase`; COMMIT | `_transition` | ✅ |
| 409 message text | per phase: "The activity is already OPEN.", "…CLOSED; a closed activity cannot be opened again.", DRAFT end → "…Use Cancel activity instead." | ⚠ → open diagram label updated (E4) |
| After commit: `activity.state` + `dashboard.state` to teachers, then `publish_student_states()` loop through `student_view` | `publish_teacher_state`, `_publish_students` | ✅ |
| End: a racing submit either commits first (ranked) or sees CLOSED → `activity_ended` | `test_submit_racing_end_is_all_or_nothing` (50 rounds) | ✅ |

## 002-seq-join.puml

| Step | Code | Status |
|---|---|---|
| GET `/api/student/state` → `student_state(key=None)`; no activity → `{activity: null}` | `state_for_token` → `resolve_key` → `student_state` | ✅ |
| Join: name checked before the transaction; inside: no current / other activity → `join_refused`; group outside range → `invalid_join`; `already_joined`; insert with `sha256(token)` | `ParticipationService.join` | ⚠ → branch order and the pre-transaction name check redrawn (E5) |
| After commit: `publish_group_state` (group 3 sockets only), then `dashboard.state` via `teacher_publisher` | `_after_group_change` | ⚠ → order and route via `teacher_publisher` redrawn (E5) |
| 201 + `Set-Cookie qb_participant`; client reconnects `/ws/student`; socket keyed `(activity, participant, group)` | `student_routes.join`; `student.js reconnectNow`; `ws_routes.student_socket` | ✅ |
| Change group: DELETE `/membership` → `leave`; OPEN / CLOSED → 409 `group_change_refused`; DRAFT → delete; 204 + cookie cleared | `ParticipationService.leave`, `student_routes.leave` | ✅ |
| Change group without a valid membership → 401 `not_a_member` | implemented, not drawn | ⚠ → branch added (E5) |

## 002-seq-submit.puml

| Step | Code | Status |
|---|---|---|
| Before the transaction: trim, non-empty, ≤ 200, no duplicate sub-part → 422 | `validate_answers` | ⚠ → label corrected; "every slot present" moved inside (E6) |
| BEGIN IMMEDIATE; participant → 401 `not_a_member`; phase DRAFT → `not_open`; CLOSED → `activity_ended` | `submit`, `_member_in_tx` | ✅ |
| Unit not in the student's activity → 404 `unit_not_found`; sub-part set ≠ slots → 422 | `get_unit_for_activity`; in-transaction set check | ⚠ → branches added (E6) |
| Duplicate → `already_submitted` with the group's own submission (no rank) | `get_group_submission`, `submission_out` | ✅ |
| `rank = 1 + COUNT`, insert submission + answers, COMMIT; `IntegrityError` backstop | `count_unit_submissions`, `insert_submission` | ✅ |
| After commit: group push, then `dashboard.state` via `teacher_publisher`; 201 without rank | `_after_submission`, `student_routes.submit` | ⚠ → order and route redrawn (E6) |

## 002-seq-cancel-activity.puml

| Step | Code | Status |
|---|---|---|
| DELETE `/activities/{id}` → guard → `cancel_activity`; BEGIN IMMEDIATE; missing → 404; OPEN / CLOSED → `CancelRefused` 409 (messages as drawn); DRAFT → `DELETE` (cascade); COMMIT | `ActivityService.cancel_activity`, `db.delete_activity` | ✅ |
| After commit: `activity.state` (displayed: latest CLOSED or null), no dashboard; `publish_student_states()` → `{activity: null}`; 204 | `cancel_activity`; `test_cancel_publishes_the_displayed_activity_after_commit` | ✅ |
| Open vs cancel: exactly one wins; join vs cancel leaves no participant | `test_phase_concurrency.py` | ✅ |

## 002-seq-reconnect.puml

| Step | Code | Status |
|---|---|---|
| `/ws/student`: `resolve_key(token)` → register with key → `student_state(key)` → four alt branches (member of current; member of latest CLOSED with no current; no membership + current; neither) | `student_socket`, `ParticipationService._student_state` | ✅ |
| `/ws/teacher`: guard (4401 after restart) → register → `get_displayed_activity()` + `get_dashboard(id)` → `activity.state` + `dashboard.state` | `teacher_socket` (also tolerates a cancel between the two reads) | ✅ |
| Recovery within 3 s, same state over HTTP | `test_student_recovers_state_after_refresh_and_missed_phase_changes`, `test_teacher_recovers_the_live_state_on_reconnect` | ✅ |

## Discrepancies and resolutions (002)

| # | Diagram | Discrepancy | Resolution |
|---|---|---|---|
| E0 | system-component | (found during Phase 2) the guard was planned as a router dependency, which FastAPI runs after parsing a malformed JSON body (422 instead of the contract's 401) | Implemented as `TeacherGuardMiddleware`; research R1, plan, contracts, tasks and the diagram updated in commit `f76e580` |
| E1 | system-component | `student_view(phase, group, ...)` | Label now shows `student_view(activity, participant, members, own_submissions)` |
| E2 | system-component | dashboard pushes drawn as PART → RT directly | New PART → ACT edge "teacher_publisher = publish_dashboard (after join / leave / submit)"; PART → RT now "student.state snapshots" |
| E3 | domain-class | `StudentKey` (models.py) not drawn | Added to the in-memory package with a note |
| E4 | 002-seq-open-activity | 409 text drawn as "activity is already <phase>" for all phases | Label lists the exact messages |
| E5 | 002-seq-join | name check drawn inside the transaction; `invalid_join` drawn before `join_refused`; group push and dashboard order; no `not_a_member` branch on change group | Redrawn to match `join` / `leave` (the contract's codes were unchanged) |
| E6 | 002-seq-submit | "every slot present" drawn before the transaction; no `unit_not_found` or in-transaction set branch; dashboard drawn before the group push | Redrawn to match research R3's order, which the code follows |
| E7 | data-model.md (not a diagram) | query list named `get_phase_for_update` and `group_has_submitted`, which were not needed | List updated to the implemented names |

Not discrepancies: `/student` and the `/` redirect have no sequence diagram (research R8); the
teacher and student pages are covered by the component diagram and the manual checks M11–M25.
