# Feature 002 — Overnight implementation report

**Run**: `/speckit-implement` for `specs/002-live-buzz-activity/tasks.md`, unattended, 2026-11-27.
**Stop reason**: finished. Every phase was completed in the requested order, and no test needed
3 failed fix attempts. Nothing was pushed. `.env` and `secrets/` were never read, printed or
changed.

## Phases and commits

| Phase | Tasks | Commit | Full suite after |
|---|---|---|---|
| Baseline (before 002 code) | — | `35e0ee5` | 210 passed |
| 1 Setup + 2 Foundational | T001–T017 | `f76e580` | 272 passed |
| 3 US1 Open | T018–T024 | `b9ab24e` | 287 passed |
| 4 US2 Join + submit + ranking | T025–T032 | `83ecf66` | 365 passed |
| 5 US3 Dashboard + End | T033–T039 | `7736c66` | 383 passed |
| 7 US5 Cancel DRAFT (run before US4, as asked) | T045–T049 | `4ef7dc4` | 396 passed |
| 6 US4 Teammates' live view + leak test | T040–T044 | `26daae0` | 408 passed |
| 8 Polish | T050, T051, T053, T055, T056 | `9f15bc7` | **410 passed**, 0 skipped, ~63 s |

**Not done, as instructed**: T052 (README) and T054 (manual checks). Both are marked as open in
`tasks.md`.

**Test-first evidence**: one row per phase in `docs/verification.md` › Feature 002 › Test-first
record. Each row gives the red run (failures and collection errors) and the green run.

These tests were **not red**. They passed on their first run, and this is recorded honestly:
- the 3 refresh/reconnect recovery tests in US4. Phase 2's snapshot-on-connect design already
  covered them;
- the 2 polish tests (log hygiene, push latency). They check existing behaviour.

**Key results**:
- SC-003: 100 rounds of 12 groups submitting at once gave ranks exactly 1..12 every round.
- Submit racing End (50 rounds): every submission was either ranked or refused, never half-saved.
- SC-005 leak test passes.
- Push latency at 60 student + 2 teacher sockets: OPEN reached every socket in 0.046–0.063 s,
  and a submission reached the teachers and teammates in 0.015–0.031 s (target < 1 s).

## Decisions and deviations (all recorded in the docs in the same commit)

1. **The teacher guard is an ASGI middleware, not a router dependency.** FastAPI parses a
   malformed JSON body before router dependencies run, so such a request got 422 instead of the
   contract's 401. `TeacherGuardMiddleware` (`api/auth.py`) checks every `/api/teacher/*` path
   except `/session` before routing. Recorded in research R1, the plan, both contracts, tasks
   T010 and the component diagram (`f76e580`).
2. **`Settings.teacher_passcode` has `repr=False`,** so the passcode cannot appear in logs or
   tracebacks. This is not in the task text, but Principle VI requires it.
3. **Hub API.** `publish_from_thread(message)` keeps 001's signature (it broadcasts to teachers).
   `send_from_thread(pairs)` is new. T014 had proposed a different signature. The plan's
   blueprint is updated.
4. **`get_dashboard` moved from US3 to US1,** because Open publishes `dashboard.state`. Its shape
   test was written first, in T018. Noted in tasks.md.
5. **`teacher_publisher` = `ActivityService.publish_dashboard`,** which sends `dashboard.state`
   only. The plan had named `publish_teacher_state`. The WebSocket contract lists only
   `dashboard.state` after join, leave and submit. The plan is updated.
6. **Student error messages, and how an old membership is treated, are now in the contract.** The
   spec didn't cover them (`contracts/rest-api.md` › "Student error messages and membership
   rules"):
   - `join_refused` `details.phase` is the phase of the *requested* activity, or `null`.
   - A member of the latest CLOSED activity, with no newer current one, gets `activity_ended` on
     submit and `group_change_refused` on change group. With a newer current activity they get
     `not_a_member`.
7. **The "latest CLOSED" activity is the CLOSED activity with the highest id.** Only one activity
   is ever non-CLOSED, so no `closed_at` column (or migration) is needed. Documented in `db.py`.
8. **StudentState is returned exactly as the visibility filter builds it** (a plain dict), with no
   second pydantic model, so only one shape can reach students.
9. **The student and teacher pages were written ahead of their phases** (Phase 2 and US1), then
   ticked per phase. They are checked only by `node --check`. No browser test exists.
10. **Four existing 001 tests were adjusted for 002 contract changes.** None was weakened:
    - `tests/conftest.py`: `client` is now an unlocked teacher.
    - `tests/unit/test_db.py`: the "later-feature tables are not created" assertion now checks
      that the 002 tables exist and that no `groups` table exists.
    - `tests/integration/test_reimport_api.py::test_replace_pushes_activity_state`: reads the
      connect-time `dashboard.state` before its unchanged re-import assertions.
    - `tests/integration/test_import_api.py` log test: also asserts that the passcode never appears
      in logs.
11. **Test fixes:**
    - US3's first red run hung on a blocking WebSocket receive. I added a timed `recv()` helper
      (`tests/live_helpers.py`), which uses Starlette TestClient internals (`portal`, `_send_rx`).
      It may need updating after a Starlette upgrade.
    - `test_time_never_orders_ranks` had patched the clock before the joins, which also read the
      clock. The patch now comes after the joins, and the assertions are unchanged.
12. **Code-vs-diagram check (T055).** Seven diagram corrections, E1–E6 plus E0 from Phase 2, and
    the data-model query list aligned (E7). In every case the code followed the spec, so the
    diagrams were changed. All PNGs were re-rendered (exit 0). See `diagrams/VERIFICATION.md` ›
    Feature 002.
13. **Configuration.** The pytest marker `slow` was registered in `pyproject.toml`, and it stays
    in the default run. No new dependencies were added.

## Blockers

None.

## Things to know or check

- **Your local `.env` must now contain `TEACHER_PASSCODE=<something>`, or the app refuses to
  start** (FR-004). I did not open `.env`, so I don't know whether it is set.
- **Possible snapshot ordering race.** A push built just before a socket's on-connect snapshot
  could, in theory, arrive after it, showing a slightly older state until the next push. This
  has not been observed or tested. It would only matter at the exact moment of a reconnect.
- **The tests use several TestClients**, so pushes cross event loops. Production has a single
  loop. Everything passes, but this is a test-only setup.
- **A pre-existing `StarletteDeprecationWarning`** (httpx → httpx2) appears in every test run.
- **History note from yesterday**: commit `ae027be` says "tasks T036 wording", but the line is
  under T038.

## Manual checks for you (Principle V; record in `docs/verification.md` › Feature 002)

1. Make sure `.env` has `TEACHER_PASSCODE`. Start with
   `uv run uvicorn quizbuzzer.main:app --host 0.0.0.0 --port 8000`, and allow Python through the
   Windows firewall for the private network.
2. Run **M11–M25** from `specs/002-live-buzz-activity/quickstart.md` §5, with the teacher laptop
   and at least three student devices or browsers. Prepare a sheet with at least one 題組. Watch
   especially for:
   - M16, M22: screens switch within 1 s.
   - M19: two groups submitting together get ranks 1 and 2, and students see no rank.
   - M20: developer tools on another group's device show nothing about other groups.
   - M21: a refresh, and Wi-Fi off/on, keep the student's screen and group state.
   - M23, M24: cancel.
3. **Browser-only behaviour no test covers:**
   - the teacher passcode form and re-locking after a server restart;
   - the Open / End / Cancel confirm dialogs;
   - the closed view's "Import a new worksheet" button;
   - the student's unsent text being replaced when a teammate submits the same unit.
4. **T052, the README** (left for you): run instructions for `/teacher`, `/student`,
   `TEACHER_PASSCODE` and `0.0.0.0`, plus the dependency/licence table from 001 research R10.
