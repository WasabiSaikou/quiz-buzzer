# Implementation Plan: Live Buzz-In Activity with Real-Time Phase Sync

**Branch**: `002-live-buzz-activity` (spec directory; work continues on `master`) | **Date**:
2026-11-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-live-buzz-activity/spec.md`

## Summary

The teacher unlocks `/teacher` with `TEACHER_PASSCODE`. They can open the current DRAFT
activity, watch a live dashboard of ranked submissions, and end it, or cancel the activity while
it is still DRAFT. Students join a group at `/student`. While DRAFT they wait, and while OPEN
they submit one answer set per question unit for their group. Every phase change reaches every
screen at once, and a refresh or reconnect recovers state from the server.

Technically:
- A router-level `require_teacher` dependency and an in-memory `TeacherSessions` (HttpOnly
  cookie) guard every `/api/teacher/*` route, including 001's, and `/ws/teacher`.
- A new `ParticipationService` handles join, change group (DRAFT only) and submit. Submit runs
  the phase check, duplicate check, `rank = 1 + count` and insert in one `BEGIN IMMEDIATE`
  transaction, backed by `UNIQUE(unit_id, rank)` and `UNIQUE(unit_id, group_number)`.
- `ActivityService` gains `open_activity`, `end_activity` and `cancel_activity`. Each runs a
  read-check-write in one transaction.
- `RealtimeHub` pushes **full snapshots**: `activity.state` + `dashboard.state` to teachers, and
  `student.state` to students. Every student message is built by one function that passes only
  the recipient's own group's rows to the pure `visibility.student_view` (Principle III).
- No new dependencies and no changes to 001 tables. Three new tables: `participants`,
  `submissions` and `submission_answers`.

## Diagram Blueprint (Principle VIII)

The diagrams are the primary blueprint, and module and class names match them exactly.

| Diagram element | Code |
|---|---|
| Teacher UI | `static/teacher.html`, `teacher.js`: add the passcode form, Open / End / Cancel buttons with confirm dialogs, the dashboard and the closed view |
| Student UI | **new** `static/student.html`, `student.js`, served at `GET /student`; `GET /` redirects there |
| `api/auth_routes.py` | **new**: `POST /api/teacher/session` |
| Teacher guard | **new** `api/auth.py`: `TeacherSessions` (`create(passcode)`, `is_valid(token)`), `require_teacher(conn)`, `TeacherGuardMiddleware` (pure ASGI), `WrongPasscode`, `TeacherRequired` |
| `api/teacher_routes.py` | guarded by `api/auth.py: TeacherGuardMiddleware` (prefix `/api/teacher/`, except `/session`; research R1, changed from a router dependency during implementation); adds `POST /activities/{id}/open`, `POST /activities/{id}/end`, `DELETE /activities/{id}`, `GET /activities/{id}/dashboard`; `GET /activities/current` returns the displayed activity |
| `api/student_routes.py` | **new**: `GET /api/student/state`, `POST /api/student/join`, `DELETE /api/student/membership`, `POST /api/student/submissions` |
| `api/ws_routes.py` | `/ws/teacher` (cookie check → close 4401; on connect `activity.state` + `dashboard.state`); **new** `/ws/student` (`resolve_key` → register → `student.state`) |
| Real-time channel | `realtime/hub.py: RealtimeHub`: `teachers: set`, `students: dict[WebSocket, StudentKey \| None]`, `send_many(pairs)`, `student_sockets(activity_id=None, group_number=None)`, `publish_from_thread(message)` (kept: broadcast to teachers, unchanged 001 signature), `send_from_thread(pairs)` (any socket list); helpers `student_state_message`, `dashboard_state_message`; `StudentKey` NamedTuple in `models.py` |
| Activity service | `services/activity_service.py: ActivityService` + `open_activity`, `end_activity`, `cancel_activity`, `get_displayed_activity`, `get_dashboard`, `publish_teacher_state(activity)` (sends `activity.state` + `dashboard.state` to teacher sockets, after open / end), `publish_dashboard(activity_id)` (`dashboard.state` only); exceptions `PhaseConflict`, `CancelRefused`; constructor takes `student_publisher` (= `ParticipationService.publish_student_states`) |
| Participation service | **new** `services/participation_service.py: ParticipationService`: `resolve_key(token)`, `student_state(key)`, `join`, `leave`, `submit`, `publish_student_states()`, `publish_group_state(activity_id, group_number)`; constructor takes `teacher_publisher` (= `ActivityService.publish_dashboard`; `dashboard.state` only, as the WebSocket contract lists for join / leave / submit), called after each successful join / leave / submit commit (the "PART → RT dashboard.state" arrows in `system-component`, `002-seq-join` and `002-seq-submit`); exceptions `InvalidJoin`, `JoinRefused`, `AlreadyJoined`, `NotAMember`, `GroupChangeRefused`, `InvalidAnswers`, `NotOpen`, `ActivityEnded`, `UnitNotFound`, `AlreadySubmitted` |
| Visibility filter | **new** `services/visibility.py: student_view(activity, participant, members, own_submissions) -> dict` (pure); `validate_display_name`, `validate_answers` helpers live in `participation_service.py` |
| SQLite store | `db.py`: new tables + queries (data-model.md › Queries) |
| Domain classes | `models.py`: `Participant`, `Submission`, `SubmissionAnswer`, `StudentKey`; `Group` is a value (no class needed beyond `group_number: int`) |
| Config | `config.py`: `Settings.teacher_passcode`; `load_settings` raises `ConfigError` when it is blank |

**Diagram changes made during planning** (re-rendered 2026-11-27, exit 0, 12/12 PNGs fresh):
- `domain-class`: `Group` became a `<<value>>` with no `id` (research R4). The constraint names
  are now `UNIQUE(unit_id, group_number)`.
- `system-component`: added `api/auth_routes.py`. ActivityService now calls
  `ParticipationService.publish_student_states()` instead of calling the visibility filter
  directly, so there is one student-bound path (R6). The hub is described as keyed student
  sockets instead of channels.
- `002-seq-open-activity`, `-end-activity`, `-cancel-activity`: student pushes are drawn as a
  per-socket loop through ParticipationService and `student_view`. Removed `opened_at` and
  `closed_at` (R5). Cancel publishes the displayed activity (R7).
- `002-seq-join`, `-submit`: the message names are now `dashboard.state` / `student.state`
  snapshots. Added the `already_joined` branch. `student_view` replaces `group_view`.
- `002-seq-reconnect`, `-teacher-unlock`: `resolve_key` then register then `student_state`, and
  the teacher side gets `get_displayed_activity()` (current, else latest CLOSED).

## Technical Context

**Language/Version**: Python 3.11 (uv-managed project `.venv`, as in 001 research R1).

**Primary Dependencies**: FastAPI, uvicorn + websockets, python-dotenv,
google-api-python-client, google-auth. Dev: pytest, httpx. **No additions**: `hmac`, `secrets`,
`hashlib` and `threading` are stdlib (research R10).

**Storage**: SQLite through stdlib `sqlite3` (WAL, foreign keys, `BEGIN IMMEDIATE` for every
write). New tables are created idempotently at startup (data-model.md).

**Testing**: pytest + FastAPI `TestClient`, with thread-and-barrier concurrency tests on a file
DB. The `client` fixture becomes an unlocked teacher, and separate `TestClient`s act as students
(research R9).

**Target Platform**: Windows 10/11 teacher laptop serving `0.0.0.0:8000`. Student browsers
(phones or laptops) connect over the classroom LAN.

**Project Type**: Local web application (single process: REST, WebSocket, static pages).

**Performance Goals**:
- Phase change visible on 60 student screens plus the teacher tabs within 1 s (SC-001).
- An accepted submission reaches the dashboard and teammates within 1 s (SC-002).
- Reconnect recovery within 3 s (SC-007).

At this scale a snapshot push is one SQLite read per connected group plus about 60 small sends.

**Constraints**:
- Ranks come only from the server's transaction order (Principle I).
- Student data passes only through `student_view` (Principle III).
- Phase lives only in SQLite (Principle IV).
- No secrets or student data in logs (Principle VI).
- No frontend build step.

**Scale/Scope**: 1 teacher (multiple tabs), 1 current activity, up to 12 groups, about 60
student sockets, up to about 200 units per activity.

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1 design.*

| Principle | How this plan complies | Pre | Post |
|---|---|---|---|
| I. Server-authoritative fairness | Submit runs the phase check, duplicate check, `rank = 1 + COUNT` and insert inside one `BEGIN IMMEDIATE` transaction. `UNIQUE(unit_id, rank)` makes a second winner impossible, and `UNIQUE(unit_id, group_number)` a second group submission. `received_at` is display-only, and no client time is read (R3). End and submit serialise on the same lock, so nothing is accepted after CLOSED. A concurrency test runs 100 rounds × 12 groups. | ✅ | ✅ |
| II. Dynamic Guided Notes handling | 002 does not touch the parser or exporter. It uses only the stored units and slots. | ✅ (N/A) | ✅ (N/A) |
| III. Information hiding until close | One function builds student state, passing only the recipient's own group's rows to the pure `visibility.student_view`. Submissions push only to the submitting group. No student response or message carries rank or `isWinner`. Error bodies carry only the student's own data (`already_submitted` → their own submission). A leak test records all of one student's traffic during a full activity (R6, R9). | ✅ | ✅ |
| IV. Single source of truth for phase | Phase is only in SQLite. Every change pushes snapshots to every socket. Connecting sends the same snapshot, so reconnect needs no client logic beyond "render the latest" (R6). Transitions are forward only. Cancel deletes a DRAFT activity; it is not a phase, and the spec defines it (FR-008a). | ✅ | ✅ |
| V. Test-first for core rules | Tests are written and seen failing first for winner selection and ranks, phase transitions (open, end, cancel and all refusals), visibility rules (`student_view` unit tests + leak test), and the teacher guard. Manual records M11–M25 go in `docs/verification.md` (quickstart §5). | ✅ | ✅ |
| VI. Secrets hygiene | `TEACHER_PASSCODE` comes only from `.env` (`.env.example` has an empty placeholder). It is compared in constant time, never stored, echoed or logged. Session and participant tokens are random, and participant tokens are stored hashed. Display names and answers are never logged; logs carry codes and ids. | ✅ | ✅ |
| VII. Consistency and simplicity | No new dependencies, no groups table (R4), no event replay (R6), no new columns on 001 tables (R5). The 001 changes made today (message, scenario 2.6, diagram, tests) were in the same change set. **Gap found**: the README has no dependency/licence table. Tasks add it (R10). | ✅ | ✅ |
| VIII. PlantUML design-first | The blueprint table above maps diagram to code. The diagrams were updated during planning and re-rendered (`java -jar tools/plantuml.jar "./diagrams/*.puml"`, exit 0). `/speckit-implement` ends with a 002 section in `diagrams/VERIFICATION.md`. | ✅ | ✅ |

There are no violations, so Complexity Tracking lists only justified choices.

## Project Structure

### Documentation (this feature)

```text
specs/002-live-buzz-activity/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0: R1–R10
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1: run + manual M11–M25
├── contracts/
│   ├── rest-api.md      # teacher session, activity control, dashboard, student API
│   └── websocket.md     # /ws/teacher (extended), /ws/student
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks (not created here)
```

### Source Code (quiz-buzzer/; new files marked +, changed files marked ~)

```text
.env.example                     ~ TEACHER_PASSCODE= (already in the working tree)
README.md                        ~ run instructions (/teacher, /student, passcode) + dependency/licence table
docs/verification.md             ~ 002 section: M11–M25, test-first record
diagrams/VERIFICATION.md         ~ 002 code-vs-diagram section (end of implement)
src/quizbuzzer/
├── config.py                    ~ Settings.teacher_passcode; ConfigError when blank
├── main.py                      ~ wire TeacherSessions, ParticipationService, new routers, /student, / redirect, error handlers
├── db.py                        ~ participants, submissions, submission_answers + queries
├── models.py                    ~ Participant, Submission, SubmissionAnswer, StudentKey
├── services/
│   ├── activity_service.py      ~ open/end/cancel, displayed activity, dashboard, PhaseConflict, CancelRefused
│   ├── participation_service.py + join/leave/submit, student_state, publish helpers
│   └── visibility.py            + student_view (pure)
├── realtime/hub.py              ~ teacher set + keyed student sockets, send_many
├── api/
│   ├── auth.py                  + TeacherSessions, require_teacher
│   ├── auth_routes.py           + POST /api/teacher/session
│   ├── teacher_routes.py        ~ open/end/cancel/dashboard (guarded by TeacherGuardMiddleware)
│   ├── student_routes.py        + /api/student/*
│   ├── ws_routes.py             ~ /ws/teacher auth + snapshots; + /ws/student
│   └── schemas.py               ~ request/response models (camelCase)
└── static/
    ├── teacher.html, teacher.js ~ passcode form, controls, dashboard, closed view
    ├── student.html             +
    └── student.js               +
tests/
├── conftest.py                  ~ settings.teacher_passcode; client = unlocked teacher; anon_client; student_client()
├── unit/
│   ├── test_config.py           + blank TEACHER_PASSCODE → ConfigError (T003)
│   ├── test_teacher_sessions.py + (T004)
│   ├── test_visibility.py       + student_view rules, no rank / foreign keys (T005)
│   ├── test_db.py               ~ 002 schema constraints + cascades (T006)
│   ├── test_activity_phases.py  + open / end / cancel rules, dashboard, displayed activity (T018, T033, T045)
│   ├── test_participation_service.py + join / leave rules (T025)
│   ├── test_ranking.py          + validation, check order, ranks, time never orders (T026)
│   └── test_group_push.py       + group-only pushes (T040)
└── integration/
    ├── test_import_api.py       ~ log hygiene incl. passcode sentinel (T010); import after CLOSED (done)
    ├── test_teacher_guard.py    + every /api/teacher/* route (001 + 002) → 401; /ws/teacher → 4401 (T007)
    ├── test_ws_student.py       + snapshots, teammates, refresh / reconnect recovery (T008, T042)
    ├── test_ws_teacher.py       ~ cookie required; dashboard.state; displayed CLOSED activity (T036)
    ├── test_phase_concurrency.py + open vs open, open vs cancel, join vs cancel (T019, T046)
    ├── test_live_flow_api.py    + open and cancel endpoints + pushes (T020, T047)
    ├── test_submit_concurrency.py + SC-003, same-group race, submit vs end (T027, T034)
    ├── test_student_api.py      + student REST contract (T028)
    ├── test_dashboard_api.py    + dashboard, end, import after end (T035)
    ├── test_visibility_leak.py  + SC-005 (T041)
    ├── test_logs_002.py         + no passcode / names / answers in logs (T050)
    └── test_push_latency.py     + SC-001 / SC-002 with 60 student sockets (T051)
```

**Structure Decision**: The single src-layout project from 001 continues. The student page is
another static file pair in the package. No frontend or backend split.

## Implementation Notes for Tasks

- **Order** (test-first, Principle V):
  1. Setup: config, the `.env.example` check, fixtures.
  2. Teacher guard: tests first, then make 001's suite green again with the unlocked `client`.
  3. Schema + `visibility` + participation rules: tests first.
  4. Phase transitions and cancel: tests first.
  5. Submit + ranking + concurrency: tests first.
  6. Hub, WebSocket snapshots and the leak test.
  7. Teacher UI.
  8. Student UI.
  9. README, manual records, code-vs-diagram verification.

  Map the user stories to phases: US1 (open + guard), US2 (join/submit), US3 (dashboard/end),
  US4 (group push), US5 (cancel).
- **001 regression**: making `client` an unlocked teacher keeps 001's tests unchanged. Add one
  guard test that iterates over `app.routes` with prefix `/api/teacher`, so any future teacher
  route is automatically checked for 401 (SC-006).
- **Publishing after commit**: every publish happens after `COMMIT`, never inside the
  transaction. A rolled-back change therefore never reaches a client.
- **Logging**: log error codes, activity/unit ids and group numbers only. Never log display
  names, answer text, tokens or the passcode (FR-004, FR-032).
- **`ConfigError` at startup**: `Settings.teacher_passcode` is the last field, with default `""`.
  Both `load_settings()` and `create_app()` reject a blank value. Tests pass
  `Settings(..., teacher_passcode="test-passcode")`. Of the two existing tests that construct
  `Settings` directly:
  - `test_google_sheets_adapter.py` never builds an app, so it stays untouched;
  - the log-hygiene test in `test_import_api.py` builds an app, so it must add the field. That
    test should also gain the passcode as a sentinel that must never appear in the logs.

## Complexity Tracking

No constitution violations. Choices beyond the bare minimum, each justified:

| Choice | Why needed | Simpler alternative rejected because |
|---|---|---|
| `UNIQUE(unit_id, rank)` in addition to the in-transaction count | Makes two winners impossible even if a future code path skips `BEGIN IMMEDIATE` (Principle I: "impossible, not unlikely") | The count alone relies on every writer taking the lock |
| Participant tokens stored as a sha256 hash | A copied DB file cannot be used to act as a student | Storing plain tokens costs nothing to avoid |
| Full snapshots instead of delta events | Reconnect and missed pushes need no replay logic (Principle IV), and every student message passes one filter (Principle III) | Deltas need sequence numbers and resync paths, and they spread student-bound data over several builders |
| Teacher "displayed activity" falls back to the latest CLOSED one | FR-029: the final dashboard must survive a refresh right after End | Holding it only in page memory loses it on refresh |
