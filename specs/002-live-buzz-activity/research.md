# Research: Live Buzz-In Activity with Real-Time Phase Sync (002)

**Date**: 2026-11-27 · **Spec**: [spec.md](spec.md) · **Builds on**:
[001 research](../001-sheets-import/research.md) (R1 environment, R7 SQLite, R8 sync endpoints and
WebSocket push, R9 testing, R10 dependencies all still apply).

The Technical Context had no open items. The stack, storage and test tooling are 001's. Each
section below records a design decision that the spec left open.

## R1. Teacher passcode and teacher session (FR-001 – FR-004)

- **Decision**:
  - `config.Settings` gains `teacher_passcode: str`. `load_settings()` raises `ConfigError("TEACHER_PASSCODE is not set in .env.")`
    when it is missing or blank. `create_app()` checks the same, so the app refuses to start
    (FR-004). The message names the variable, never a value.
  - `api/auth.py` holds three things:
    - `TeacherSessions`, an in-memory set of tokens guarded by a lock.
    - `create(passcode)`, which compares the passcode with `hmac.compare_digest` (on UTF-8 bytes)
      and returns `secrets.token_urlsafe(32)`.
    - `require_teacher(conn)`, which raises `TeacherRequired` without a valid cookie.
  - The token goes in the cookie `qb_teacher` with `HttpOnly`, `SameSite=Strict` and `Path=/`.
    It has no `Max-Age`, so it is a browser-session cookie, and every token is lost on server
    restart (FR-003). The cookie is not `Secure`, because the app serves plain HTTP on the LAN.
  - `require_teacher` runs in a pure ASGI middleware, `TeacherGuardMiddleware`, on every
    request whose path is `/api/teacher` or starts with `/api/teacher/`, except
    `POST /api/teacher/session` (which lives on its own `auth_routes` router). Every existing 001
    route, every new 002 teacher route, and even an unknown `/api/teacher/…` path is covered, and a
    new route cannot forget it (FR-002).
    **Changed during implementation (2026-11-27)**: the plan attached `require_teacher` as a router
    dependency (`APIRouter(..., dependencies=[Depends(require_teacher)])`). FastAPI parses a
    malformed JSON body *before* router dependencies run, so such a request got 422
    `invalid_request` (echoing field names) instead of 401. That breaks the contract rule that
    the guard runs before body validation. The middleware runs before routing and body parsing,
    so the rule holds, as `tests/integration/test_teacher_guard.py` checks for every route.
  - `/ws/teacher` checks the cookie before sending anything. If the cookie is invalid it accepts
    and immediately closes with code `4401`. Accepting first is needed, because Starlette cannot
    send a custom close code on a rejected upgrade.
  - Failure response: `401 teacher_required`, with the same body for every route and no
    `details`. A wrong passcode gives `401 wrong_passcode`.
- **Rationale**: Prefix-level enforcement makes "student pages cannot call teacher actions"
  structural rather than per-route. A cookie, unlike a header token kept in JS, is sent
  automatically on WebSocket upgrades and never readable by page scripts (the passcode never
  reaches storage, FR-004). `SameSite=Strict` blocks cross-site form posts.
- **Alternatives considered**:
  - Sending the passcode with every request (as a header): it would have to be stored in the
    browser, which breaks FR-004.
  - Signed stateless tokens: they would need a secret and would survive restarts, which
    contradicts FR-003.
  - A per-route `Depends`: forgettable.
  - HTTP Basic auth: the browser caches it and offers no clean unlock UI.

## R2. Student membership (FR-009 – FR-014)

- **Decision**: Joining creates a `participants` row and a random token
  (`secrets.token_urlsafe(32)`). The token is returned in the cookie `qb_participant`
  (`HttpOnly`, `SameSite=Strict`, `Path=/`, `Max-Age` = 12 h, so reopening the browser during a
  class day still returns the student, FR-012). The DB stores only
  `token_hash = sha256(token).hexdigest()`. Every student request resolves
  `token_hash → participant → (activity_id, group_number)`. A group number is never accepted
  after the join (FR-014).
  - **One membership per browser**: a join while holding a valid membership of the current
    activity is refused (`409 already_joined`). The UI uses "Change group" instead.
  - **Change group** (`DELETE /api/student/membership`): deletes the participant only when the
    phase is DRAFT, then clears the cookie. A DRAFT participant can never have submissions.
  - **Membership of another activity** (a CLOSED or cancelled one, FR-014): treated as "no
    membership" for the current activity. A join then replaces the cookie.
- **Rationale**: Hashing means a DB copy cannot be used to impersonate students. sha256 without
  salt is enough for 256-bit random tokens. Cookies make the WebSocket carry the membership
  without JS handling the secret.
- **Alternatives considered**: `localStorage` + header (readable by scripts, and WebSocket
  needs a query-string token); remembering group number + name only (anyone could claim any
  membership).

## R3. Ranking and the submit transaction (FR-016 – FR-020, Constitution I)

- **Decision**: `ParticipationService.submit()` does two things:
  1. **Before the transaction**, it validates the shape: answers are a non-empty list, there are
     no duplicate `subPart`s, and every text, after `str.strip()`, has 1–200 characters
     (Python `len`, code points). `str.strip()` removes all Unicode whitespace, including U+3000
     and line breaks (FR-016).
  2. **Then, inside one `db.transaction()`** (`BEGIN IMMEDIATE`), in this order:
     1. resolve the participant, or fail with `NotAMember`;
     2. read the activity phase: DRAFT gives `NotOpen`, CLOSED gives `ActivityEnded`;
     3. load the unit, which must belong to the participant's activity (else `UnitNotFound`),
        and check that the set of `subPart`s equals the unit's slots (else `InvalidAnswers`);
     4. check the duplicate `SELECT 1 FROM submissions WHERE unit_id=? AND group_number=?`
        (else `AlreadySubmitted`);
     5. compute `rank = 1 + COUNT(*) FROM submissions WHERE unit_id=?`;
     6. insert the submission (`received_at` = server UTC with milliseconds) and one
        `submission_answers` row per slot;
     7. `COMMIT`.
  - **Schema backstops**: `UNIQUE(unit_id, group_number)`, `UNIQUE(unit_id, rank)` and
    `CHECK(rank >= 1)`. An `IntegrityError` maps to `AlreadySubmitted` (the group one) or is a
    bug (the rank one). The concurrency tests prove the rank one never fires.
  - 001 research R7 recorded a global `arrival_seq` for this feature. **It is replaced by a
    per-unit `rank`**. Ranking within a unit is what the spec needs, and a second ordering
    column would be redundant (Principle VII). `received_at` (server UTC, milliseconds) is
    **kept**: the dashboard shows it, and feature 003's CSV export needs it. It is never used to
    order or rank.
- **Rationale**: `BEGIN IMMEDIATE` takes SQLite's single write lock before the first read. All
  submit, end and cancel transactions are serialised in server arrival order, so a
  read-count-insert sequence cannot interleave. Two "rank 1" rows are impossible, not unlikely.
  An end that commits first makes every later submit see CLOSED, which covers the
  submit-at-close race (FR-017).
- **Alternatives considered**:
  - A Python lock: process-local, and lost if a code path skips it.
  - Computing rank at read time from `received_at`: millisecond ties break on client-invisible
    but non-deterministic order.
  - `AUTOINCREMENT` id as the order: correct, but it gives a global sequence rather than a rank
    and needs a query to turn into one.

## R4. Groups are values, not rows

- **Decision**: there is **no `groups` table**. A group is identified by
  `(activity_id, group_number)`, with `group_number` in `1..activities.group_count` checked in
  the join transaction. `participants.group_number` and `submissions.group_number` carry it.
  The dashboard lists groups 1..group_count, including empty ones, from `group_count` (FR-028).
- **Rationale**: A group has no attributes of its own, so creating 2–12 rows per activity (and
  keeping them in step with re-import and cancel) adds writes and code with no information.
  This is the simplest design that meets the spec (Principle VII). `domain-class.puml` was
  updated: `Group` is now shown as a value with no `id`.
- **Alternatives considered**: create group rows at activity creation (this touches 001's
  create path, and its only benefit is foreign keys); create them lazily at first join (rows
  appear in some groups and not others, so the dashboard still needs `group_count`).

## R5. Phase changes and cancel (FR-005 – FR-008c)

- **Decision**: `ActivityService` gains three methods: `open_activity(id)`, `end_activity(id)`
  and `cancel_activity(id)`. Each one runs a `BEGIN IMMEDIATE` read-check-write:
  - **open**: DRAFT → OPEN, else `PhaseConflict(phase)` 409.
  - **end**: OPEN → CLOSED, else `PhaseConflict(phase)` 409. For DRAFT, the message suggests
    Cancel.
  - **cancel**: DRAFT → `DELETE FROM activities WHERE id=?`, else `CancelRefused(phase)` 409.
  - A missing activity gives `ActivityNotFound` 404.

  A cancel deletes everything because units, slots and participants cascade through
  `ON DELETE CASCADE`. Submissions cannot exist in DRAFT, and they would cascade through units
  anyway. No `opened_at` or `closed_at` columns are added, because the spec never shows them,
  and leaving them out avoids an `ALTER TABLE` on existing 001 databases.
- **Rationale**: This follows 001's re-check-inside-the-transaction pattern (001 FR-026).
  Because the open, cancel and submit transactions serialise, exactly one of a simultaneous
  Open and Cancel succeeds. The loser sees OPEN (409) or a missing activity (404), as drawn in
  `002-seq-cancel-activity`.
- **Schema migration**: the new tables use `CREATE TABLE IF NOT EXISTS`, so an existing 001
  database gains them at startup. No 001 table changes.

## R6. Real-time design: full snapshots through one student path (FR-008, FR-021, FR-023, FR-030)

- **Decision**:
  - **Snapshots, not deltas**. Every push is a complete state message: teachers get
    `activity.state` and `dashboard.state`, students get `student.state`. On connect, a socket
    gets the same snapshot. The client simply renders the latest message, so reconnect,
    missed pushes and ordering need no extra logic (Principle IV).
  - **`RealtimeHub`** grows from one set of teacher sockets to:
    - `teachers: set[WebSocket]`;
    - `students: dict[WebSocket, StudentKey | None]`, where
      `StudentKey = (activity_id, participant_id, group_number)` is resolved once, at connect,
      from the cookie.

    A participant's group never changes (changing group creates a new participant, R2). The
    socket key stays valid until the client reconnects, which the UI does after join and
    change group.
  - **Only one code path builds student-bound data**:
    `ParticipationService.student_state(conn, key) → dict`. It reads the activity, the
    participant, its group's members and its group's submissions, then passes them to the pure
    `visibility.student_view(...)`. That function decides the output and never receives other
    groups' rows. Two publishing helpers sit on top:
    - `publish_student_states(activity_id=None)`: one `student.state` per connected student
      socket. ActivityService calls it after open, end, cancel and create, and after
      re-import, via an injected callback.
    - `publish_group_state(activity_id, group_number)`: sent only to that group's sockets
      after a join, leave or submit.

    A socket whose participant no longer exists (cancelled activity, left group) gets the
    no-membership view.
  - **Teacher pushes**: after every change that affects them, `ActivityService` publishes
    `activity.state` plus `dashboard.state`. The changes are open, end, cancel, create,
    re-import, and join/leave/submit (published by ParticipationService through the same
    helper).
  - **Threading**: unchanged from 001 R8. Services are synchronous and run in FastAPI worker
    threads, and publish through `anyio.from_thread.run(hub.send_many, [(ws, msg), …])`.
    Snapshots are built in the worker thread (DB reads), then sent in one hop.
- **Rationale**:
  - Snapshots make Principle IV recovery trivial, and the 60-socket scale makes their size
    irrelevant (a few KB).
  - Building every student message through one function that is never handed foreign rows
    makes Principle III auditable in one place, and testable as a pure function plus a leak
    test (R9).
  - Keying sockets at connect avoids a DB lookup per push to find groups.
- **Alternatives considered**:
  - Delta events (`submission.accepted`, `phase.changed`): they need replay or versioning
    after a reconnect.
  - Per-group "channels" as hub objects: extra lifecycle for no gain over filtering the
    dict.
  - Server-Sent Events: they would need a second push mechanism next to the existing teacher
    WebSocket.

## R7. Teacher view after End (FR-029)

- **Decision**: The teacher's "displayed activity" is the current (DRAFT/OPEN) activity. If
  there is none, it is the **most recently closed activity**, read by the new
  `db.find_latest_activity()`. `/ws/teacher` on connect, and `GET /api/teacher/activities/current`,
  return it with its phase, plus `dashboard.state`. When it is CLOSED, the teacher page shows the
  final dashboard and an "Import a new worksheet" button. This replaces 001's
  "`activity: null` → import form" behaviour **only when a CLOSED activity exists**.
  `GET /activities/current` therefore now returns a CLOSED activity in that case. 001's contract
  and spec record the change, and 001's tests that assert `null` run on a fresh DB, so they are
  unaffected.
  - **The displayed activity never blocks an import.** `get_displayed_activity()` is used only
    for display. `create_from_import` keeps using `db.find_current_activity()` (DRAFT/OPEN only)
    and the `one_current_activity` partial index, both unchanged, so the last CLOSED activity
    can never cause `current_activity_exists`. Tests:
    - 001's `test_create_after_previous_activity_closed_201` (phase set directly, added
      2026-11-27);
    - 002's import-after-end test, which ends through `POST /activities/{id}/end` and then
      imports through the API.
- **Rationale**: FR-029 needs the final dashboard to survive a refresh or reconnect right after
  End. The student side already does the same for its own group (FR-025). Browsing older
  activities stays out of scope (003).
- **Alternatives considered**: keep `null` and hold the final dashboard only in page memory
  (lost on refresh); a separate "last closed" endpoint (two sources for one view).

## R8. Student page

- **Decision**: `static/student.html` + `student.js` (vanilla JS, no build, like 001). They are
  served at `GET /student`, with `GET /` redirecting to `/student` so that students can type the
  shortest URL. The page renders `student.state` as one of five screens: no activity / join
  form / waiting (DRAFT) / answering (OPEN) / closed. While the socket is down it shows
  "Reconnecting…" and retries with exponential backoff (0.5 s doubling to a 5 s cap, FR-030).
  Text typed but not submitted is kept in memory only (spec Assumptions).
- **Rationale**: same toolchain as the teacher page. One snapshot-driven render function keeps
  the UI a pure view of server state (Principle IV).
- **LAN note**: students reach the server through `QUIZBUZZER_HOST=0.0.0.0` (already documented
  in `.env.example`). Deployment beyond the LAN is a non-goal.

## R9. Testing approach for 002 (Constitution V)

- **Decision** (tests are written and seen failing before the code, for the core rules):
  - **Unit, pure**: `visibility.student_view` (every phase × membership; it never emits rank or
    foreign fields), answer and name validation (trim, U+3000, line breaks, 200/20 limits),
    and `TeacherSessions` (wrong or right passcode, constant-time compare used).
  - **Service**:
    - phase transitions, including all refusals, open/cancel/end on a missing activity, and
      cancel cascades;
    - join, leave and change-group rules;
    - submit rules and ranks.
  - **Concurrency (file DB, threads + `threading.Barrier`)**:
    - SC-003: 100 rounds of 12 groups submitting the same unit, giving exactly ranks 1..12 with
      no gaps or repeats;
    - two members of one group, so exactly one is accepted;
    - submit vs end, so every accepted submission is in the DB with a rank and every rejection
      is `ActivityEnded`;
    - open vs cancel, so exactly one wins.
  - **API/WS integration (`TestClient`)**:
    - every `/api/teacher/*` route, including the 001 ones, returns 401 without the cookie, and
      `/ws/teacher` closes with 4401 (SC-006);
    - the full flow: unlock, open, join, submit, end;
    - reconnect snapshots;
    - teammates receive `student.state` and other groups receive nothing.
  - **Leak test (SC-005, Principle III)**: one student socket records every message, and every
    HTTP response to that student is recorded too, during a full OPEN activity in which all
    other groups submit. The test asserts that no other group's answer text, group number,
    submitter name, count or rank appears before CLOSED. Answers use unique marker strings so
    the search is exact.
  - **Fixtures**:
    - `settings` gets `teacher_passcode="test-passcode"`;
    - `client` becomes an **unlocked teacher** client (it posts the passcode), so 001's tests
      keep passing unchanged;
    - new `anon_client` and `student_client()` factories build separate `TestClient`s (separate
      cookie jars) on the same app;
    - WebSocket tests pass the cookie explicitly in headers when the TestClient's websocket
      does not forward its jar.
- **Manual verification** (Principle V): quickstart §5 M11–M25, recorded in
  `docs/verification.md` under a 002 section.

## R10. Dependencies and licences

- **Decision**: **no new dependencies**. `hmac`, `secrets`, `hashlib` and `threading` are
  stdlib, and cookies and dependencies come with FastAPI/Starlette.
- **Pre-existing gap found**: `README.md` is only a title. The dependency/licence table from 001
  research R10, which Principle VII requires, was never added. 002's tasks add it (unchanged
  list) together with run instructions for `/student` and `TEACHER_PASSCODE`.
