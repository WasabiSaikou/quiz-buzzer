---

description: "Task list for feature 002 — Live Buzz-In Activity with Real-Time Phase Sync"
---

# Tasks: Live Buzz-In Activity with Real-Time Phase Sync

**Input**: Design documents from `specs/002-live-buzz-activity/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/rest-api.md](contracts/rest-api.md),
[contracts/websocket.md](contracts/websocket.md), [quickstart.md](quickstart.md)

**Tests**: REQUIRED (Constitution Principle V and the user's instruction). Tests come first for
these core rules:
- **ranking and winner selection**
- **phase transitions**: open, end, cancel and every refusal
- **visibility**: `student_view` and the leak test
- the teacher guard

Write each test task first, **run it, and record that it fails**, before starting the
implementation task it covers. Record the red run in `docs/verification.md` › 002 › test-first
record: test id, date and failing output summary.

**Organization**: Tasks are grouped by user story:
- **US1** (P1, open + every screen switches): needs only the Foundational phase.
- **US2** (P1, join + submit): needs an OPEN activity. Its tests set the phase directly, so it
  can start in parallel with US1, but its UI is easiest to check after US1.
- **US3** (P1, dashboard + end): uses US2's submissions.
- **US4** (P2, teammates' live view): uses US2.
- **US5** (P2, cancel DRAFT): the cancel itself needs only the Foundational phase. The test
  parts that join or submit (in T045 and T046) also need US2's T029 and T030, and the
  open-vs-cancel race needs T021.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: US1 … US5 (user story phases only)
- All paths are relative to `quiz-buzzer/`. Package root: `src/quizbuzzer/`.

## Conventions used by every task

- Module, class and function names come from the plan's **Diagram Blueprint** table and must
  match the diagrams exactly (Principle VIII). The sequence diagrams
  `diagrams/002-seq-*.puml` give the call order of each flow.
- Field constraints are defined once, in [data-model.md](data-model.md). Tasks cite fields as
  `data-model.md › Entity.field` and do not repeat the rules.
- HTTP status, error `code`, check order and payload shapes: [contracts/rest-api.md](contracts/rest-api.md).
  Message types and recipients: [contracts/websocket.md](contracts/websocket.md).
- Every write uses `db.transaction(conn)` (`BEGIN IMMEDIATE`). Every publish happens **after**
  the commit, never inside the transaction (plan › Implementation Notes).
- Student-bound data is built **only** by `ParticipationService.student_state(...)` through
  `visibility.student_view(...)` (research R6, Principle III).
- Never log the passcode, tokens, display names or answer text. Log only codes, ids, phases and
  group numbers (FR-004, FR-032).
- **Do not commit** a test task's red state without its implementation unless the commit
  message says "red".

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: baseline and records.

- [X] T001 Run `uv run pytest` and confirm the 001 baseline (210 passed at commit `ae027be`). Add a `## Feature 002` section skeleton to `docs/verification.md` with three subsections: "Test-first record (002)" (table: test id, date, red output summary, green commit), "Manual verification (M11–M25)" (copy the table from `quickstart.md` §5 with empty Result/Evidence columns), and "Automated test runs"
- [X] T002 [P] Confirm that `.env.example` holds `TEACHER_PASSCODE=` with an empty value and a comment line above it ("Required. Passcode that unlocks /teacher. Never commit the real value."). Add the comment in `.env.example` if it is missing

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: these are needed by every story:
- passcode configuration and the teacher guard (FR-001 – FR-004);
- the new schema;
- the domain types;
- the keyed real-time hub;
- the visibility filter;
- the read-only student state path (`GET /api/student/state`, `/ws/student`);
- the student page shell.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete. After T010, every
001 test must pass again.

### Tests for Foundational (write first, observe failing) ⚠️

- [X] T003 [P] Write `tests/unit/test_config.py`:
  - `load_settings()` with `TEACHER_PASSCODE` missing, empty or whitespace-only raises `ConfigError` whose message names `TEACHER_PASSCODE` and contains no value;
  - with a value set, `Settings.teacher_passcode` equals it;
  - `create_app(settings=Settings(..., teacher_passcode=""))` raises `ConfigError`.

  Use `monkeypatch.delenv` / `setenv` and `env_file=None` (research R1, FR-004).
- [X] T004 [P] Write `tests/unit/test_teacher_sessions.py` for `api/auth.py: TeacherSessions`:
  - `create(wrong)` raises `WrongPasscode`;
  - `create(right)` returns a URL-safe token of at least 43 characters, and `is_valid(token)` is true;
  - `is_valid` is false for an unknown or empty token;
  - two `create` calls return different tokens, and both are valid at once (several tabs, FR-003);
  - a new `TeacherSessions` instance (a restart) does not accept old tokens;
  - the comparison uses `hmac.compare_digest` (monkeypatch it to record the call).
- [X] T005 [P] Write `tests/unit/test_visibility.py` for the pure `services/visibility.py: student_view(activity, participant, members, own_submissions)`. Build plain inputs, with no DB:
  - assert every row of `contracts/rest-api.md › StudentState` › Rules: no activity; no membership; member in DRAFT; member in OPEN (units present with `unitId`, `number`, `kind`, `subParts`, in position order); member of the latest CLOSED activity;
  - for every case, walk the output recursively and assert that **no key** is `rank`, `isWinner`, `groupNumber` (except `membership.groupNumber`), `count` or `total`;
  - assert that `units` is absent outside OPEN;
  - assert that `group.submissions` contains only the `own_submissions` passed in (FR-015, FR-022 – FR-025, Constitution III).
- [X] T006 [P] Extend `tests/unit/test_db.py` with 002 schema tests:
  - `init_schema` is idempotent and adds `participants`, `submissions` and `submission_answers` to a DB that already holds 001 tables and rows, leaving those rows unchanged;
  - the CHECK and UNIQUE constraints reject bad rows: `data-model.md › Participant.group_number`, `Participant.display_name` (0 and 21 characters rejected, 1 and 20 accepted), `Participant.token_hash` (duplicate rejected), `Submission.rank` (0 rejected), `Submission.group_number`, `SubmissionAnswer.text` (0 and 201 characters rejected; 200 CJK characters accepted, so `length()` counts characters);
  - `UNIQUE (unit_id, group_number)` and `UNIQUE (unit_id, rank)` (`data-model.md › Submission`) each reject a second row;
  - deleting an activity cascades to participants, units, slots, submissions and submission_answers (`data-model.md › Participant.activity_id`, `Submission.unit_id`).
- [X] T007 [P] Write `tests/integration/test_teacher_guard.py`:
  - with `anon_client`, iterate over **every** route in `app.routes` whose path starts with `/api/teacher`, except `POST /api/teacher/session`. Call each with its method, a placeholder id `1` and an invalid JSON body. Each must return 401 with exactly `{"error": {"code": "teacher_required", "message": "Teacher passcode required."}}`, never 422 (the guard runs before validation). Assert the 001 routes are in the iterated set by name, so the list cannot silently shrink;
  - `POST /api/teacher/session` with a wrong passcode gives 401 `wrong_passcode` and no `Set-Cookie`;
  - with the right passcode it gives 204, and `Set-Cookie: qb_teacher` has `HttpOnly`, `SameSite=Strict`, `Path=/` and no `Max-Age` or `Expires`;
  - the response body and headers never contain the passcode;
  - `/ws/teacher` without the cookie is accepted and then closed with code 4401 before any message.

  Covers FR-001 – FR-003, SC-006, `contracts/rest-api.md › Teacher access`, and `contracts/websocket.md › /ws/teacher`.
- [X] T008 [P] Write `tests/integration/test_ws_student.py` (state part). Use `student_client()` sockets (cookie passed in headers if the TestClient websocket does not forward its jar):
  - on connect with no activity, `student.state` has `activity: null`;
  - after a teacher creates an activity (001 confirm), every connected student socket receives `student.state` with `{id, phase: "DRAFT", groupCount}` and no membership (FR-008, FR-031);
  - after a re-import, sockets receive a fresh snapshot;
  - `GET /api/student/state` returns the same object as the socket snapshot.

  Covers `contracts/websocket.md › /ws/student`.

### Implementation for Foundational

- [X] T009 Implement the passcode configuration in `src/quizbuzzer/config.py`:
  - `Settings.teacher_passcode: str = ""` as the last field;
  - `load_settings()` reads `TEACHER_PASSCODE`, strips it, and raises `ConfigError("TEACHER_PASSCODE is not set in .env.")` when it is blank.

  In `src/quizbuzzer/main.py`, `create_app()` raises the same error when `settings.teacher_passcode` is blank (research R1). Makes T003 pass.
- [X] T010 Implement the teacher guard (research R1, `diagrams/002-seq-teacher-unlock.puml`):
  - `src/quizbuzzer/api/auth.py`: `TeacherSessions` (lock-guarded set; `create(passcode)` using `hmac.compare_digest` on UTF-8 bytes and `secrets.token_urlsafe(32)`; `is_valid(token)`), `WrongPasscode`, `TeacherRequired`, and the dependency `require_teacher(request)`, which reads the `qb_teacher` cookie;
  - `src/quizbuzzer/api/auth_routes.py`: `POST /api/teacher/session`, which sets the cookie with the attributes in the contract;
  - ~~in `src/quizbuzzer/api/teacher_routes.py`, set `APIRouter(..., dependencies=[Depends(require_teacher)])`~~ **done instead as** `TeacherGuardMiddleware` in `src/quizbuzzer/api/auth.py`, added in `main.py`: a router dependency runs after FastAPI parses the JSON body, so a malformed body got 422 instead of 401 (research R1, changed 2026-11-27);
  - in `src/quizbuzzer/api/ws_routes.py`, `/ws/teacher` checks the cookie first and on failure accepts, then closes with 4401;
  - in `src/quizbuzzer/main.py`, create `app.state.teacher_sessions`, include `auth_routes` before `teacher_routes`, and register the 401 handlers.

  Then update `tests/conftest.py`:
  - `settings` gets `teacher_passcode="test-passcode"`;
  - `client` becomes an unlocked teacher (it posts the passcode);
  - new fixtures `anon_client` and `student_client()` (a factory of separate `TestClient`s on the same `app`), plus a helper `ws_headers(client)` that builds a `cookie` header from a client's jar;
  - the log-hygiene test in `tests/integration/test_import_api.py` passes `teacher_passcode=f"pass-{SENTINEL}"` and asserts the passcode never appears in captured logs.

  Makes T004 and T007 pass, and `uv run pytest` is fully green again, with 001's tests otherwise unchanged.
- [X] T011 [P] Add the domain types to `src/quizbuzzer/models.py`: `Participant`, `Submission` (with `is_winner` property), `SubmissionAnswer` and `StudentKey` (`NamedTuple(activity_id, participant_id, group_number)`). Fields follow `data-model.md › Participant`, `Submission` and `SubmissionAnswer`. Group stays a plain `group_number: int` (research R4).
- [X] T012 Add the 002 tables to `SCHEMA` in `src/quizbuzzer/db.py` (`CREATE … IF NOT EXISTS`; no change to 001 tables, research R5). Each column, CHECK, UNIQUE, FK and cascade follows its canonical definition:
  - `participants`: `data-model.md › Participant.id`, `Participant.activity_id`, `Participant.group_number`, `Participant.display_name`, `Participant.token_hash`, `Participant.joined_at`, plus the `(activity_id, group_number)` index;
  - `submissions`: `data-model.md › Submission.id`, `Submission.unit_id`, `Submission.group_number`, `Submission.participant_id`, `Submission.rank`, `Submission.received_at`, plus `data-model.md › Submission` › Constraints (`UNIQUE (unit_id, group_number)`, `UNIQUE (unit_id, rank)`);
  - `submission_answers`: `data-model.md › SubmissionAnswer.submission_id`, `SubmissionAnswer.slot_id`, `SubmissionAnswer.text`, PK `(submission_id, slot_id)`.

  Update the module docstring. Makes T006 pass.
- [X] T013 [P] Implement the pure `src/quizbuzzer/services/visibility.py: student_view(activity, participant, members, own_submissions) -> dict`, producing `contracts/rest-api.md › StudentState` exactly. It takes no DB connection and no other groups' data. Makes T005 pass.
- [X] T014 Refactor `src/quizbuzzer/realtime/hub.py: RealtimeHub` (research R6):
  - `teachers: set[WebSocket]`, plus `connect_teacher` / `disconnect`;
  - `students: dict[WebSocket, StudentKey | None]`, plus `connect_student(ws, key)`;
  - `student_sockets(activity_id=None, group_number=None) -> list[(ws, key)]`;
  - `async send_many(pairs)`, which drops dead sockets without stopping;
  - `broadcast_teachers(message)`;
  - `publish_from_thread(coro_factory)`, which keeps 001's anyio hand-off behaviour.

  Keep `activity_state_message`. Update the existing teacher-socket call sites in `src/quizbuzzer/services/activity_service.py` and `src/quizbuzzer/api/ws_routes.py` and any hub tests (`tests/integration/test_ws_teacher.py` now connects with the teacher cookie).
- [X] T015 Create `src/quizbuzzer/services/participation_service.py: ParticipationService(db_path, hub)` with only the read and publish side for now:
  - `resolve_key(token) -> StudentKey | None`, which hashes with sha256 and matches `data-model.md › Participant.token_hash`;
  - `student_state(key) -> dict`, which reads the activity, the participant, the own group's members and the own group's submissions, then calls `visibility.student_view`. With no current activity it falls back to the participant's activity only when that activity is the latest CLOSED one. A key whose participant no longer exists gets the no-membership view;
  - `publish_student_states()`, which builds one snapshot per connected student socket in the worker thread, then calls one `hub.send_many`;
  - `publish_group_state(activity_id, group_number)`, which sends only to sockets with that key.

  Add the db queries it needs to `src/quizbuzzer/db.py`: `find_participant_by_token_hash`, `list_group_members`, `list_group_submissions` and `find_latest_activity`. Also add `insert_participant(conn, activity_id, group_number, display_name, token_hash, joined_at)` (fields per `data-model.md › Participant.activity_id`, `Participant.group_number`, `Participant.display_name`, `Participant.token_hash`, `Participant.joined_at`) now, so that the US1 and US3 tests can create members before US2's `join` exists.
- [X] T016 Wire the student read path:
  - `src/quizbuzzer/api/student_routes.py`: `GET /api/student/state`;
  - `/ws/student` in `src/quizbuzzer/api/ws_routes.py`: resolve the key, register the socket, then send `student.state` (`diagrams/002-seq-reconnect.puml`);
  - `src/quizbuzzer/api/schemas.py`: response models;
  - `src/quizbuzzer/main.py`: build `ParticipationService` and pass `participation.publish_student_states` to `ActivityService(..., student_publisher=...)`;
  - `src/quizbuzzer/services/activity_service.py`: `create_from_import` and `replace_questions` call `student_publisher()` after their commit.

  Makes T008 pass.
- [X] T017 [P] Create the student page shell:
  - `GET /student` serves `src/quizbuzzer/static/student.html`, and `GET /` redirects (307) to `/student`, both in `src/quizbuzzer/main.py`;
  - `src/quizbuzzer/static/student.js`: one `render(state)` choosing among five screens (no activity / join form / waiting / answering / closed) from `student.state` only;
  - a socket wrapper that reconnects after 0.5 s, doubling up to a 5 s cap, and shows "Reconnecting…" while down (research R8, FR-030, FR-031).

  The join, answer and change-group actions come in US2.

**Checkpoint**: The app requires the passcode, every 001 test passes, student sockets get
snapshots, and the schema is ready.

---

## Phase 3: User Story 1 — Teacher opens the activity and every screen switches (Priority: P1) 🎯 MVP

**Goal**: the teacher unlocks `/teacher`, opens the DRAFT activity, and every teacher tab and
student screen shows OPEN at once (FR-005 – FR-008).

**Independent Test**: create a DRAFT activity, connect two student sockets and two teacher
sockets, and open it from one. All four receive OPEN snapshots within 1 s, and a second open is
refused with 409.

### Tests for User Story 1 (write first, observe failing) ⚠️

- [X] T018 [P] [US1] Write `tests/unit/test_activity_phases.py` (open part; **also the dashboard-shape test**, moved forward from T033 because `open` publishes `dashboard.state`, so `get_dashboard` is implemented in T021) against `ActivityService` with a recording hub and a recording `student_publisher`:
  - `open_activity` on DRAFT returns the activity with phase OPEN and persists it;
  - on OPEN and on CLOSED it raises `PhaseConflict` with `.phase`, and the row is unchanged;
  - on a missing id it raises `ActivityNotFound`;
  - success publishes exactly one `activity.state` (OPEN) and one `dashboard.state` to teachers and calls `student_publisher` once, all after the commit (the recorder checks the DB phase at call time);
  - a refused open publishes nothing;
  - after open, `replace_questions` raises `ReimportRefused` (001 FR-026).
- [X] T019 [P] [US1] Write `tests/integration/test_phase_concurrency.py` (open part). Two threads with their own `ActivityService` on the same file DB call `open_activity` behind a `threading.Barrier`: exactly one succeeds, the other raises `PhaseConflict(OPEN)`. Repeat 20 times (FR-006).
- [X] T020 [P] [US1] Write `tests/integration/test_live_flow_api.py` (open part):
  - `POST /api/teacher/activities/{id}/open` gives 200 with an `Activity` of phase OPEN;
  - repeating it gives 409 `phase_conflict` with `details.phase == "OPEN"` and a message containing "already OPEN";
  - an unknown id gives 404 `not_found`;
  - two `/ws/teacher` sockets both receive `activity.state` OPEN;
  - a joined student socket (participant created with `db.insert_participant` from T015 and a known token, so that the cookie resolves) receives `student.state` with phase OPEN and `units`;
  - an unjoined student socket receives phase OPEN **without** `units`.

  Covers `contracts/rest-api.md › POST …/open` and `contracts/websocket.md`.

### Implementation for User Story 1

- [X] T021 [US1] Implement `ActivityService.open_activity(activity_id)` and `PhaseConflict(phase)` in `src/quizbuzzer/services/activity_service.py`, following `diagrams/002-seq-open-activity.puml`:
  1. `BEGIN IMMEDIATE`;
  2. `db.get_activity_phase`;
  3. `db.set_phase(conn, id, OPEN)`;
  4. commit;
  5. publish teacher snapshots, then `student_publisher()`.

  Add `set_phase` to `src/quizbuzzer/db.py`. Makes T018 and T019 pass.
- [X] T022 [US1] Add `POST /activities/{activity_id}/open` to `src/quizbuzzer/api/teacher_routes.py` and the `phase_conflict` 409 handler (with `details.phase`) to `src/quizbuzzer/main.py`. Makes T020 pass.
- [X] T023 [US1] Extend `src/quizbuzzer/static/teacher.html` and `teacher.js`:
  - a passcode form shown on any 401 `teacher_required` or a `/ws/teacher` close with 4401, which posts to `/api/teacher/session` and then reloads state;
  - an "Open" button, visible only in DRAFT, with a `confirm()` stating it cannot be undone (FR-007);
  - phase shown from `activity.state` only (Principle IV).
- [X] T024 [US1] Complete the waiting and answering screens in `src/quizbuzzer/static/student.js`. Waiting shows the group number. Answering lists units by number in the given order, with one input per sub-part labelled （k） for a 題組 and one input for a single question, and no question text (FR-015). Rendering comes only from `student.state`, and the submit buttons are wired in US2.

**Checkpoint**: US1 works on its own: unlock, open, and every screen switches.

---

## Phase 4: User Story 2 — Student joins a group, waits, then answers for the group (Priority: P1)

**Goal**: join, change group (DRAFT only), and submit a unit as a whole, with server ranking
(FR-009 – FR-020).

**Independent Test**: with an OPEN activity of 3 units (one 題組 with 2 sub-parts), join group 2
and submit each unit. Each is accepted with no rank in the response, and a second submission of
the same unit is refused with `already_submitted`.

### Tests for User Story 2 (write first, observe failing) ⚠️

- [X] T025 [P] [US2] Write `tests/unit/test_participation_service.py` (join and leave):
  - names `" 小明 "` (stored trimmed), a 20-character name and a 21-character name (refused), and `"　"` (full-width space only, refused), per `data-model.md › Participant.display_name`;
  - group numbers 0, 1, `group_count`, `group_count + 1` and `13`, per `data-model.md › Participant.group_number` and 001 `Activity.group_count`;
  - join is allowed in DRAFT and OPEN; `JoinRefused` in CLOSED, with no current activity, and when `activity_id` is not the current one;
  - `AlreadyJoined` when the token already belongs to this activity, but a token of an older activity is allowed;
  - the DB holds only `sha256(token)`, never the token (`data-model.md › Participant.token_hash`);
  - duplicate names are allowed (FR-011);
  - `leave` deletes the participant in DRAFT, raises `GroupChangeRefused(phase)` in OPEN and CLOSED, and raises `NotAMember` for an unknown token (FR-013).
- [X] T026 [P] [US2] Write `tests/unit/test_ranking.py`, the **core ranking rules**, tests first (Constitution I, FR-016 – FR-020):
  - answer validation runs before the transaction: empty, `"  "`, `"　"`, `"\n"` and 201 characters are refused, and 200 characters are accepted; `details.subParts` lists every failing k; text is stored trimmed (`data-model.md › SubmissionAnswer.text`);
  - a `subPart` set that is missing, unknown or duplicated gives `InvalidAnswers` (`data-model.md › SubmissionAnswer.slot_id`);
  - the check order follows research R3: `NotAMember`, then `NotOpen` (DRAFT) / `ActivityEnded` (CLOSED), then `UnitNotFound` (another activity's unit), then `AlreadySubmitted` (whose `.submission` is the group's own);
  - sequential submissions from groups 4, 1 and 6 to one unit get ranks 1, 2, 3 in that order, and `is_winner` is true only for rank 1 (`data-model.md › Submission.rank`);
  - another unit's ranks start again at 1;
  - `group_number` is copied from the participant (`data-model.md › Submission.group_number`), and `participant_id` is the submitter (`Submission.participant_id`);
  - `received_at` is server UTC ISO-8601 with milliseconds and is not taken from any input (`Submission.received_at`);
  - a monkeypatched clock that returns an *earlier* time for the second submission does not change the ranks (time never orders);
  - the returned dict has no `rank` or `isWinner` key;
  - a failure after the insert (monkeypatched) leaves no submission and no answers (all-or-nothing).
- [X] T027 [P] [US2] Write `tests/integration/test_submit_concurrency.py` (ranking part, SC-003). On a file DB, run 100 rounds. Each round, 12 threads (one per group, each with its own `ParticipationService`) submit the same unit behind a `threading.Barrier(12)`. Assert that every round gives exactly ranks {1..12} with no gaps or repeats, exactly one rank 1, and 12 rows. Add a same-group race: two members of one group submit one unit 50 times on fresh units, and exactly one is accepted, while the other gets `AlreadySubmitted` showing the accepted answer. Mark the 100-round test `@pytest.mark.slow` but keep it in the default run.
- [X] T028 [P] [US2] Write `tests/integration/test_student_api.py`:
  - `POST /api/student/join` gives 201 with `StudentState`, and `Set-Cookie: qb_participant` has `HttpOnly`, `SameSite=Strict`, `Path=/` and `Max-Age=43200`;
  - each 422 `invalid_join` (`details.field`, `details.max`), 409 `join_refused` and 409 `already_joined`;
  - `DELETE /api/student/membership` gives 204 and clears the cookie in DRAFT, 409 `group_change_refused` in OPEN, and 401 `not_a_member` with no cookie;
  - `POST /api/student/submissions` gives 201 in the contract shape, and a recursive key walk finds no `rank` or `isWinner`;
  - each error code in the contract's check order;
  - sending an extra `groupNumber` field in the submit body is ignored, and the group comes from the cookie (FR-014).

  Covers `contracts/rest-api.md › Student API`.

### Implementation for User Story 2

- [X] T029 [US2] Implement `join` and `leave` in `src/quizbuzzer/services/participation_service.py`, following `diagrams/002-seq-join.puml`. Use `validate_display_name`, exceptions `InvalidJoin(field, max)`, `JoinRefused(phase)`, `AlreadyJoined`, `GroupChangeRefused(phase)` and `NotAMember`, and checks per `data-model.md › Participant.display_name`, `Participant.group_number` and `Participant.token_hash`. Reuse `db.insert_participant` (T015) and add `delete_participant` to `src/quizbuzzer/db.py`. Makes T025 pass.
- [X] T030 [US2] Implement `submit(token, unit_id, answers)` in `src/quizbuzzer/services/participation_service.py`, following `diagrams/002-seq-submit.puml` and research R3 exactly:
  - `validate_answers` runs first, outside the transaction;
  - then, in one `db.transaction`: participant, phase, unit + `subPart` set, duplicate, `rank = 1 + count`, insert submission + answers;
  - map an `IntegrityError` on `UNIQUE(unit_id, group_number)` to `AlreadySubmitted`, and re-raise any other;
  - exceptions `InvalidAnswers(sub_parts, reasons)`, `NotOpen`, `ActivityEnded`, `UnitNotFound` and `AlreadySubmitted(submission)`.

  Add the db queries `get_unit_for_activity`, `count_unit_submissions`, `group_has_submitted`, `get_group_submission` and `insert_submission` to `src/quizbuzzer/db.py`. Field rules:
  - `data-model.md › Submission.unit_id`: the unit must belong to the participant's activity;
  - `Submission.group_number` and `Submission.participant_id`: from the resolved participant;
  - `Submission.rank`: `1 + count`;
  - `Submission.received_at`: server UTC with milliseconds, set inside the transaction and kept for 003's CSV;
  - `SubmissionAnswer.slot_id`: one row per slot of the unit;
  - `SubmissionAnswer.text`: trimmed.

  Makes T026 and T027 pass.
- [X] T031 [US2] Add `POST /api/student/join`, `DELETE /api/student/membership` and `POST /api/student/submissions` to `src/quizbuzzer/api/student_routes.py`, with the cookie handling from `contracts/rest-api.md › Cookies`. Add request and response models to `src/quizbuzzer/api/schemas.py` (extra fields ignored), and the error handlers with exact codes and messages (`"Answer （k） is empty."`, `"Your group has already submitted question N."`, `"The activity has not opened yet."`, `"The activity has ended."`) to `src/quizbuzzer/main.py`. Makes T028 pass.
- [X] T032 [US2] Add the student actions to `src/quizbuzzer/static/student.js`:
  - a join form (group 1..groupCount select; name input, `maxlength=20`) that posts `activityId`;
  - "Change group" shown only in DRAFT;
  - a submit per unit, which posts `unitId` and `answers`;
  - inline error messages from `error.message`;
  - the unit turns read-only with its answers and submitter after a 201 or `already_submitted`;
  - after a join or leave, close and reopen `/ws/student`, so that the new cookie takes effect (`contracts/websocket.md › /ws/student`).

**Checkpoint**: US2 works with an OPEN activity: join, answer and rank.

---

## Phase 5: User Story 3 — Teacher watches the live dashboard and ends the activity (Priority: P1)

**Goal**: live dashboard of ranked submissions and groups. End moves every screen to CLOSED, and
the final dashboard survives a refresh (FR-026 – FR-029, FR-005, FR-017).

**Independent Test**: OPEN activity, three groups submit to one unit. The dashboard shows ranks
1–3 in arrival order in two teacher tabs. Ending gives every socket CLOSED, a later submit gets
409 `activity_ended`, a refresh still shows the final dashboard, and a new import then succeeds.

### Tests for User Story 3 (write first, observe failing) ⚠️

- [X] T033 [P] [US3] Extend `tests/unit/test_activity_phases.py` with the end, dashboard and displayed-activity parts:
  - `end_activity` on OPEN returns phase CLOSED;
  - **closing with zero submissions** (US3 AS6, edge case): `end_activity` on an OPEN activity with no submissions succeeds, and `get_dashboard` then lists every unit with `submissions: []` and every group;
  - on DRAFT it raises `PhaseConflict(DRAFT)`, and the message contains "Cancel activity";
  - on CLOSED it raises `PhaseConflict(CLOSED)`; on a missing id, `ActivityNotFound`;
  - success publishes teacher snapshots and calls `student_publisher` after the commit, and a refusal publishes nothing;
  - `get_dashboard(id)` matches `contracts/rest-api.md › Dashboard`: units in position order, submissions in rank order with `isWinner` only on rank 1, `receivedAt` present, groups 1..group_count including empty ones, members in join order with duplicates kept;
  - `get_displayed_activity()` returns the DRAFT/OPEN activity, else the latest CLOSED one, else `None`;
  - **import after end**: after `end_activity`, `create_from_import` succeeds (a new DRAFT), the CLOSED activity's rows are unchanged, and `get_displayed_activity()` returns the new DRAFT (FR-020a, research R7).
- [X] T034 [P] [US3] Extend `tests/integration/test_submit_concurrency.py` with the submit-vs-end race (FR-017, SC-004). In 50 rounds, 6 threads submit to distinct units while one thread calls `end_activity`, all behind one barrier. After each round:
  - every accepted submission is in the DB with a rank, and those ranks are contiguous per unit;
  - every rejection is `ActivityEnded`;
  - no exception other than those two occurs;
  - the activity is CLOSED.
- [X] T035 [P] [US3] Write `tests/integration/test_dashboard_api.py`:
  - `GET /api/teacher/activities/{id}/dashboard` gives 200 in the contract shape (404 for an unknown id);
  - two `/ws/teacher` sockets receive `dashboard.state` after a join, a leave (DRAFT), each accepted submission, open and end;
  - `POST …/end` gives 200 CLOSED; 409 `phase_conflict` on a DRAFT activity, with the Cancel hint; 409 on CLOSED; 404 on an unknown id;
  - after end, every student socket receives a CLOSED `student.state` holding only its own group's submissions, and `POST /api/student/submissions` gives 409 `activity_ended`;
  - `GET /api/teacher/activities/current` and a fresh `/ws/teacher` connect return the CLOSED activity plus `dashboard.state`;
  - **import after end through the API**: `POST /api/teacher/activities` gives 201 DRAFT, `GET /activities/current` returns the new DRAFT, and the old CLOSED one is unchanged through `GET /activities/{id}`.
- [X] T036 [P] [US3] Update `tests/integration/test_ws_teacher.py` (001):
  - connect with the teacher cookie;
  - on connect, `activity.state` and then `dashboard.state` when a displayed activity exists;
  - `activity: null` and no `dashboard.state` on a fresh DB;
  - `activity.state` with phase CLOSED after end when no current activity exists.

### Implementation for User Story 3

- [X] T037 [US3] Implement `end_activity`, `get_dashboard` and `get_displayed_activity` in `src/quizbuzzer/services/activity_service.py`, following `diagrams/002-seq-end-activity.puml`. Add the db queries `list_dashboard_submissions` and `list_members_by_group` to `src/quizbuzzer/db.py` (`find_latest_activity` already exists from T015). `create_from_import` keeps using `db.find_current_activity` (do not change it). Makes T033 and T034 pass.
- [X] T038 [US3] Add `POST /activities/{activity_id}/end` and `GET /activities/{activity_id}/dashboard` to `src/quizbuzzer/api/teacher_routes.py`, and make `GET /activities/current` return the displayed activity (`contracts/rest-api.md › Change to 001`). In `src/quizbuzzer/api/ws_routes.py`, `/ws/teacher` on connect sends `activity.state` for the displayed activity plus `dashboard.state`. Add `ActivityService.publish_teacher_state(activity_id)` and pass it to `ParticipationService` as a `teacher_publisher` callback, which join, leave and submit call after their commit (`contracts/websocket.md › /ws/teacher`). Makes T035 and T036 pass.
- [X] T039 [US3] Extend `src/quizbuzzer/static/teacher.js` and `teacher.html` with the dashboard and End:
  - render `dashboard.state`: units in order, submissions as rank, group, submitter, answers labelled （k）, and the receive time shown in local time; a winner badge on rank 1; "No submissions yet" for units without any; a group list with members and counts;
  - an "End" button, visible only in OPEN, with `confirm()`;
  - when the displayed activity is CLOSED, show the final dashboard plus an "Import a new worksheet" button that opens 001's import form;
  - clear the dashboard when `activity` is `null` or its `id` changes.

**Checkpoint**: US1 + US2 + US3 give a complete class run.

---

## Phase 6: User Story 4 — Teammates see their group's submissions live (Priority: P2)

**Goal**: an accepted submission, join or leave reaches only the same group's sockets, and other
groups receive nothing (FR-021, FR-022, FR-023).

**Independent Test**: two sockets in group 3 and one in group 5. Group 3 submits unit 1: both
group 3 sockets receive `student.state` with unit 1 submitted, and the group 5 socket receives
no message at all.

### Tests for User Story 4 (write first, observe failing) ⚠️

- [ ] T040 [P] [US4] Write `tests/unit/test_group_push.py` with a recording hub holding sockets keyed for (a, 3), (a, 3), (a, 5) and `None`:
  - after `submit`, `join` and `leave` in group 3, `send_many` targets exactly the two (a, 3) sockets;
  - each payload's `group.submissions` and `members` belong to group 3 only;
  - the (a, 5) and `None` sockets receive nothing;
  - a refused submit sends nothing to any student.
- [ ] T041 [P] [US4] Write `tests/integration/test_visibility_leak.py` (SC-005, Constitution III, **visibility test first**):
  - one recording student in group 1 keeps every `/ws/student` message and every HTTP response it receives;
  - during a full OPEN activity, the other 5 groups each submit every unit with unique marker answers (`LEAK-g{n}-u{m}`) and unique display names;
  - group 1 also triggers its own errors: `already_submitted`, and `invalid_answers` while another group's submission exists;
  - until end, assert that the recorded text contains no other group's markers or names, no `"rank"` or `"isWinner"` key, and no group number other than 1;
  - assert that the number of messages the recorder received did not change when another group submitted, by comparing counts before and after each foreign submission (FR-023: even timing must not leak).
- [ ] T042 [P] [US4] Extend `tests/integration/test_ws_student.py`:
  - teammates on two sockets see unit 1 submitted with answers and the submitter's display name within the same test step;
  - the member list updates after a teammate joins;
  - after a DRAFT leave, the old group's sockets get the updated member list;
  - **refresh/reconnect recovery** (FR-012, FR-030, Constitution IV): a student joins and submits one unit, then closes its socket. A **new** socket with the same cookie, with no new join and no request body, and `GET /api/student/state`, both return the same membership (group number, display name), phase, units and the group's submitted unit. Repeat across a phase change made while disconnected (open, then end), and assert that the new snapshot shows the new phase;
  - a teacher socket closed and reopened with the same cookie gets `activity.state` and `dashboard.state` equal to the live ones;
  - each recovery snapshot arrives within 3 s of connecting (SC-007).

### Implementation for User Story 4

- [ ] T043 [US4] In `src/quizbuzzer/services/participation_service.py`, call `publish_group_state(activity_id, group_number)` after the commit of every successful `join`, `leave` and `submit`, and never on refusal. Makes T040 – T042 pass.
- [ ] T044 [US4] In `src/quizbuzzer/static/student.js`, when a `student.state` marks a unit as submitted, make that unit read-only. Replace any unsent text with the group's submitted answers and show "Submitted by <name>" (US4 AS2). Show the own group's member list on the waiting and answering screens (FR-022).

**Checkpoint**: teammates stay in sync, and the leak test proves isolation.

---

## Phase 7: User Story 5 — Teacher cancels a DRAFT activity (Priority: P2)

**Goal**: cancel deletes a DRAFT activity and frees the slot. OPEN and CLOSED activities are
refused (FR-008a – FR-008c).

**Independent Test**: create DRAFT, join one student, cancel. The student socket gets
`activity: null`, the membership is invalid, and a new import succeeds. Cancel on an OPEN
activity gives 409.

### Tests for User Story 5 (write first, observe failing) ⚠️

- [X] T045 [P] [US5] Extend `tests/unit/test_activity_phases.py` with the cancel part:
  - `cancel_activity` on DRAFT deletes the activity, its units, slots and participants (row counts 0 for that id);
  - on OPEN it raises `CancelRefused(OPEN)` with "can only be ended"; on CLOSED, `CancelRefused(CLOSED)` (rows unchanged); on a missing id, `ActivityNotFound`;
  - success publishes `activity.state` for the displayed activity (the latest CLOSED one, or `None`) and calls `student_publisher`, and a refusal publishes nothing;
  - after a cancel, `create_from_import` succeeds;
  - `replace_questions` on the cancelled id raises `ActivityNotFound`;
  - a student token from the cancelled activity resolves to no membership, and `submit` raises `NotAMember`.
- [X] T046 [P] [US5] Extend `tests/integration/test_phase_concurrency.py` with the open-vs-cancel race. In 20 rounds, `open_activity` and `cancel_activity` run behind a barrier: exactly one succeeds. Either the activity is OPEN and the cancel raised `CancelRefused(OPEN)`, or it is gone and the open raised `ActivityNotFound`. Add a join-vs-cancel race: the join either succeeds and is then deleted, or raises `JoinRefused`, and no participant row survives.
- [X] T047 [P] [US5] Extend `tests/integration/test_live_flow_api.py` with cancel:
  - `DELETE /api/teacher/activities/{id}` gives 204 on DRAFT, 409 `cancel_refused` on OPEN (message "An OPEN activity can only be ended.") and CLOSED, and 404 on an unknown id;
  - after a cancel, a connected student socket receives `student.state` with `activity: null`, and `GET /api/student/state` with the old cookie shows no membership;
  - a new `POST /api/teacher/activities` gives 201.

### Implementation for User Story 5

- [X] T048 [US5] Implement `ActivityService.cancel_activity(activity_id)` and `CancelRefused(phase)` in `src/quizbuzzer/services/activity_service.py`, following `diagrams/002-seq-cancel-activity.puml`. Add the db query `delete_activity`. Publish the displayed activity to teachers and call `student_publisher()` after the commit. Makes T045 and T046 pass.
- [X] T049 [US5] Add `DELETE /activities/{activity_id}` to `src/quizbuzzer/api/teacher_routes.py` and the `cancel_refused` 409 handler to `src/quizbuzzer/main.py`. Add a "Cancel activity" button, visible only in DRAFT, with a `confirm()` that names what is deleted, to `src/quizbuzzer/static/teacher.js`. Makes T047 pass.

**Checkpoint**: all five stories work independently.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T050 [P] Extend the log-hygiene test in `tests/integration/test_import_api.py`, or add `tests/integration/test_logs_002.py`. Run a full flow with sentinel display names, answers and passcode, and assert that none appears in captured logs at any level (FR-004, FR-032). Fix any log call that fails it.
- [ ] T051 [P] Write `tests/integration/test_push_latency.py` (SC-001, SC-002). Connect 60 student sockets across 12 groups and 2 teacher sockets. Assert that every socket receives the OPEN snapshot within 1 s of `POST …/open` returning, and that the teacher sockets and the submitting group's sockets receive the post-submit snapshots within 1 s.
- [ ] T052 [P] Rewrite `README.md`:
  - project summary;
  - run instructions: `uv sync`, `.env` with `TEACHER_PASSCODE`, `QUIZBUZZER_HOST=0.0.0.0`, the `/teacher` and `/student` URLs, and the firewall note from `quickstart.md`;
  - test and diagram commands;
  - the dependency/licence table from 001 `research.md › R10` (unchanged list, plus the pointer to `uv.lock`), as required by Principle VII and noted in research R10.
- [ ] T053 Run `uv run pytest` and record the result (count, duration, commit) in `docs/verification.md` › 002 › Automated test runs. Confirm every test-first row has its red entry and its green commit.
- [ ] T054 Manual verification (human tester): run `quickstart.md` §5 M11–M25 with real devices on the classroom LAN, and record the date, tester, commit, results and evidence (no secrets, no student data) in `docs/verification.md` › 002 (Principle V). The AI does not mark this task done.
- [ ] T055 Code-vs-diagram verification (Principle VIII). Compare `src/quizbuzzer/` with `diagrams/system-component.puml`, `domain-class.puml` and every `002-seq-*.puml` (names, calls, routes, status codes, message types), using the plan's Diagram Blueprint. Record a "Feature 002" section in `diagrams/VERIFICATION.md`, in the same table format as 001. Fix the diagrams (or the code, when the code breaks the spec), re-render with `java -jar tools/plantuml.jar "./diagrams/*.puml"` (exit 0, a PNG next to every `.puml`), and update `plan.md` › Diagram changes if anything changed.
- [ ] T056 Final consistency pass (Principle VII). Check that `spec.md`, `plan.md`, `contracts/`, `data-model.md` and `quickstart.md` match the shipped behaviour, including 001's `contracts/rest-api.md` and `websocket.md` notes on the displayed activity. Mark `T001`–`T055` done in this file.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: needs Setup. Blocks every story. T009 → T010 must land together
  with the `conftest.py` change, so that 001's suite stays green.
- **US1 (Phase 3)**: needs Foundational.
- **US2 (Phase 4)**: needs Foundational. Its service tests set the phase directly, so US2 can run
  in parallel with US1, but T032's UI check is easiest after T024.
- **US3 (Phase 5)**: needs US2's `submit` (T030) for dashboard data. T037's end can be written
  in parallel with US2.
- **US4 (Phase 6)**: needs US2 (T029, T030).
- **US5 (Phase 7)**: T048 and T049 need Foundational only. The test parts that use join or submit
  need T029 and T030: in T045, the old token gives `NotAMember`; in T046, the join-vs-cancel race.
  T046's open-vs-cancel race needs T021. Write those parts after US2, or mark them `skip` until
  then.
- **Polish (Phase 8)**: needs every story you intend to ship.

### Within each story

Tests (red, recorded) → db queries and models → service → routes and handlers → UI.

### Key task dependencies

- T003 → T009; T004, T007 → T010; T006 → T012; T005 → T013; T008 → T014, T015, T016.
- T011 → T012 → T015 (queries) → T016.
- T018, T019 → T021; T020 → T022.
- T025 → T029; T026, T027 → T030; T028 → T031.
- T033, T034 → T037; T035, T036 → T038.
- T040 – T042 → T043. T042's reconnect-recovery part also needs T030 (submit) and T037 (end).
- T020 and T035 create members with `db.insert_participant` from T015, so they do not wait for
  US2's `join`.
- T045, T046 → T048; T047 → T049.
- T015's `publish_student_states` is used by T021, T037 and T048. T038's `teacher_publisher` is
  used by T043's call sites, which also publish teacher state.

### Parallel Opportunities

- Phase 2 tests T003 – T008 are all [P]: separate files.
- T011, T013 and T017 are [P] after the tests: separate files.
- Each story's test tasks are [P] with each other.
- US1 and US5 implementation can proceed in parallel after Foundational (different methods, but
  both in `activity_service.py`: serialise the commits).
- T050 – T052 are [P].

---

## Parallel Example: User Story 2

```text
# Write the core ranking and join tests together (separate files), run them, record red:
Task: "T025 tests/unit/test_participation_service.py (join/leave)"
Task: "T026 tests/unit/test_ranking.py (validation, check order, ranks, time never orders)"
Task: "T027 tests/integration/test_submit_concurrency.py (100 rounds × 12 groups; same-group race)"
Task: "T028 tests/integration/test_student_api.py (contract)"
```

## Parallel Example: Foundational

```text
Task: "T005 tests/unit/test_visibility.py"
Task: "T006 tests/unit/test_db.py (002 schema)"
Task: "T007 tests/integration/test_teacher_guard.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3)

All three P1 stories make a usable class session: open, answer and rank, then end. The order is:
1. Phase 1 and Phase 2, with 001 green behind the guard;
2. US1 (open);
3. US2 (join and submit);
4. US3 (dashboard and end).

**Stop and validate** with quickstart M11–M22.

### Incremental Delivery

1. Foundation, then US1: the teacher can open, and screens switch.
2. Add US2: students race, and ranks are correct (SC-003 proven).
3. Add US3: the teacher sees the results live and closes the activity.
4. Add US4: teammates sync, and the leak test proves isolation.
5. Add US5: the teacher can discard a DRAFT.
6. Polish: logs, latency, README, manual records, diagram verification.

---

## Notes

- [P] = different files, no dependency on unfinished tasks.
- Commit after each green task or logical group, with messages in the repo's style
  (`feat(002): …`, `test(002): …`, `docs(002): …`).
- Constitution gates for every PR: test-first evidence (V), no secrets or student data in the
  diff (VI), and spec, plan, tasks and diagrams updated together (VII, VIII).
