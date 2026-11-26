# Quickstart: Live Buzz-In Activity (002) — Windows

Run and validation guide. Payloads are in [contracts/](contracts/), and tables are in
[data-model.md](data-model.md). Environment setup (uv, `.venv`, Google key) is unchanged from
[001 quickstart §1–2](../001-sheets-import/quickstart.md).

## 1. Configuration (new in 002)

Add the teacher passcode to `.env`. `.env.example` lists the key with an empty value. Never
commit the real value (Principle VI):

| Variable | Meaning |
|---|---|
| `TEACHER_PASSCODE` | passcode that unlocks `/teacher`. **Required**: the app refuses to start without it, and the startup error names the variable, never a value |
| `QUIZBUZZER_HOST` | `0.0.0.0` (or the laptop's LAN IP) so that student devices can connect |

## 2. Run

```powershell
uv run uvicorn quizbuzzer.main:app --host 0.0.0.0 --port 8000
```

- Teacher: `http://127.0.0.1:8000/teacher`. Enter the passcode.
- Students: `http://<laptop-LAN-IP>:8000/` (redirects to `/student`).

Allow Python through the Windows firewall on the private network if student devices cannot
connect.

## 3. Automated tests (no Google access needed)

```powershell
uv run pytest                                            # everything (001 + 002)
uv run pytest tests/unit -q                              # visibility filter, validation, sessions, service rules
uv run pytest tests/integration -q                       # REST + WebSocket, teacher guard, full flow, leak test
uv run pytest tests/integration/test_submit_concurrency.py -q   # SC-003 (100 rounds × 12 groups), submit-vs-end, open-vs-cancel
```

Expected: all pass, with 001's tests unchanged. The suite's `client` fixture is an unlocked
teacher (research R9).

## 4. Diagrams (Principle VIII)

```powershell
java -jar tools/plantuml.jar "./diagrams/*.puml"
```

Expected: exit code 0, with a fresh `.png` next to every `.puml`.

## 5. Manual validation scenarios

Use one laptop (teacher) and at least three student browsers. Phones, or private windows of
different browsers, give separate cookies. Prepare a sheet with at least one 題組. Record each
run in `docs/verification.md` under the 002 section: date, tester, commit, steps, observed result,
and evidence without secrets or student data (Principle V/VI).

| # | Steps | Expected |
|---|---|---|
| M11 | Remove `TEACHER_PASSCODE` from `.env`, start the app | Startup fails, and the message names `TEACHER_PASSCODE` (FR-004) |
| M12 | Open `/teacher`, enter a wrong passcode, then the right one | Wrong: stays locked, no activity data. Right: controls unlock (US1 AS1–2) |
| M13 | In a student browser, request `http://<ip>:8000/api/teacher/activities/current` and `…/open` with no cookie | 401 `teacher_required`, no data (FR-002, SC-006) |
| M14 | Student page with no activity, then the teacher imports and confirms one | "No activity available yet", then the join form appears without a reload (FR-031) |
| M15 | Student A joins group 1, B joins group 1 with the **same** name, C joins group 2. A changes to group 3 and back to 1 | All accepted. The dashboard shows the members, including the duplicate names. Change group works in DRAFT (FR-011, FR-013, FR-028) |
| M16 | Teacher clicks Open (confirm). Time how long until every student screen changes | All screens switch to answering within 1 s (US1 AS3, SC-001). Change group is now refused (US2 AS9) |
| M17 | A submits the 題組 with one field of spaces only, then with all fields filled | First: refused, naming the sub-part. Second: accepted. B's screen shows the unit as submitted by A within 1 s. C's screen shows no change (US2 AS4, US4, SC-002) |
| M18 | B (same group) submits the same unit | Refused: "Your group has already submitted question N" (FR-018) |
| M19 | A and C press Submit on the same unit at about the same moment | Dashboard: ranks 1 and 2, exactly one winner. Neither student sees a rank (FR-019, FR-023) |
| M20 | On C's device, open developer tools: Network and WS frames during M17–M19 | No answer text, group number, name or rank from group 1 ever appears (SC-005) |
| M21 | Refresh A's page mid-activity, then turn Wi-Fi off and on | Back on the answering screen with the group's submissions, without retyping; "Reconnecting…" shown while offline (FR-030, SC-007) |
| M22 | Teacher clicks End (confirm) while C keeps pressing Submit | All screens show closed within 1 s. C gets "The activity has ended" or the submission appears on the final dashboard, never both. A refresh of `/teacher` still shows the final dashboard (US3 AS4–7, FR-029) |
| M23 | Create a new DRAFT activity with students joined, then click Cancel activity (confirm). Then import again | Students see "No activity available yet". The new import succeeds (US5, SC-009) |
| M24 | With an OPEN activity, try Cancel from a second teacher tab | Refused: "An OPEN activity can only be ended" (US5 AS4) |
| M25 | Server log after M11–M24 | No passcode, display names or answer text in the log (FR-004, FR-032) |
