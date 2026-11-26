# Verification Record — Feature 001 Import Guided Notes Worksheet

Constitution Principle V: a core feature needs executed tests **and** a recorded manual check.
"The AI says it works" is not verification.

## 1. Manual verification (M1–M10)

Scenarios come from [quickstart.md §6](../specs/001-sheets-import/quickstart.md). Run them against
a real Google sheet shared with the service account, with the app started as described in
quickstart §3. Fill in **Result** (pass / fail, with what was observed) and **Evidence** (a
screenshot path, timing, or log excerpt with no secrets or personal data, per Principle VI).

**Date**: 20261126 · **Tester**: WasabiSaikou · **Commit**: e135676 · **Sheet(s) used**: [single](https://docs.google.com/spreadsheets/d/1T35mUGwxOpfsltzi1YurilbgpXpirtrjkRsfbFtH0dk/edit?usp=sharing), [group](https://docs.google.com/spreadsheets/d/1if3VDYXT8NL9d5DS_jNzQVIswmFJlbuhG1BW8jSkHbo/edit?usp=sharing), [mixed](https://docs.google.com/spreadsheets/d/13NBGj5KTc5F4sklJdHcjDJxtU1s8pPEx90F9Rq_cCwc/edit?usp=sharing)

| # | Steps | Expected | Result | Evidence |
|---|---|---|---|---|
| M1 | Paste a link to a sheet **not** shared with the service account | Error shows the service account email and says to share as Viewer (FR-004) | Works | ss N/A |
| M2 | Paste `https://example.com/x` | "Not a Google Sheets link"; no Google request in the server log (FR-002) | works | ss N/A |
| M3 | Share a course template, paste its link. Time from paste to preview. | First tab preselected; preview lists every question with type, sub-part count and answer cell (`tab!A1`); preview appears within 5 s (SC-001) | about 2s | |
| M4 | Paste the same link with `#gid=` of the second tab | Second tab preselected (FR-003) | works | ss N/A |
| M5 | Add `備註` in the 題號 column, refresh the preview | Warning names the row and `備註`, and says what to change (FR-008a, FR-016, SC-004) | works | |
| M6 | Confirm with 6 groups (acknowledging warnings). Time from M3's paste to the DRAFT activity. | DRAFT activity shown with 6 groups and the same slots; a second open `/teacher` tab updates without reloading; under 2 minutes (SC-003) | under 30s | |
| M7 | Try to create another activity | Refused: names the current DRAFT activity and suggests re-import (FR-020a) | works | |
| M8 | Edit the sheet (add a question), re-import, confirm | The activity now has the new question set; phase and group count unchanged (FR-024, FR-025) | works | |
| M9 | Preview, then edit the sheet structure, then confirm | Refused with the updated preview (FR-022) | works | |
| M10 | Open the sheet's version history after M3–M9 | No edits by the service account (FR-005, SC-005) | correct | |

## 2. Automated tests

Run with `uv run pytest` (no Google access needed). Final run for this record: **209 passed,
0 skipped** (2026-11-26).

### Test-first record (Principle V)

Each core-rule test file was written first and run against stubs that raised
`NotImplementedError`, and **observed failing**, before the implementation:

| Phase | Tests written first | Red run | Green run | Commit |
|---|---|---|---|---|
| 2 · URL parsing | `tests/unit/test_sheets_url.py` | 22 failed | 22 passed | `5be808d` |
| 3 · US1 parser, fingerprint, preview service + API | `test_guided_notes_parser.py`, `test_fingerprint.py`, `test_activity_service.py` (preview), `test_import_api.py` (US1) | 62 failed, 12 errors | 138 passed | `9bb27b6` |
| 4 · US2 create rules, one current activity, WebSocket | `test_activity_service.py` (create), `test_one_current_activity_concurrency.py`, `test_import_api.py` (US2), `test_ws_teacher.py` | 44 failed | 183 passed | `d0f7001` |
| 5 · US3 re-import phase rules | `test_activity_service.py` (re-import), `test_reimport_api.py` | 23 failed | 207 passed | `96ef16d` |

Not test-first, recorded honestly:
- The FR-010 edge case `numbered_row_text_then_marker_1` was added after the behaviour already
  existed, when the decision was written into the spec; it passed on its first run.
- The polish tests (log hygiene, 200-row preview timing) and the foundation tests (`test_db.py`,
  `test_fake_sheets_adapter.py`, `test_app_factory.py`, `test_google_sheets_adapter.py`) check
  supporting code, not the Principle V core rules; they were written alongside it.

## 3. Requirement traceability (T051)

Every FR and SC maps to at least one passing test, a pending manual check above, or both.

| Requirement | Automated evidence (`tests/…`) | Manual |
|---|---|---|
| FR-001 paste a link | `integration/test_import_api.py::test_tabs_*` | M3 |
| FR-002 reject non-Sheets URLs without Google | `unit/test_sheets_url.py`; `unit/test_activity_service.py::test_invalid_url_never_reaches_adapter`; `integration/test_import_api.py::test_invalid_url_400` | M2 |
| FR-003 list tabs, #gid= preselect | `unit/test_activity_service.py::test_list_tabs_*`; `integration/test_import_api.py::test_tabs_preselects_*` | M3, M4 |
| FR-004 not shared → service account email | `integration/test_import_api.py::test_adapter_errors[…not_shared…]`; `unit/test_google_sheets_adapter.py::test_error_mapping` | M1 |
| FR-005 read-only | `*::test_*never_writes_to_sheet`, `unit/test_activity_service.py::test_preview_is_read_only` (fake); read-only scope in `google_sheets_adapter.py` | M10 |
| FR-006 header detection | `unit/test_guided_notes_parser.py::test_edge_case[header_*|no_header]`, `test_header_*` | — |
| FR-007 no fixed addresses | `test_no_fixed_addresses_shifted_grid_gives_shifted_cells`; 3 reference sheets | — |
| FR-008 number forms | `test_edge_case[number_forms|fullwidth_q_and_dot]` | — |
| FR-008a unrecognised / duplicate numbers | `test_edge_case[unrecognised_numbers|duplicate_numbers]` | M5 |
| FR-009 markers | `test_edge_case[marker_forms]`; reference sheets | — |
| FR-010 numbered row as sub-part 1 or not | `test_edge_case[numbered_row_then_marker_1|numbered_row_text_then_marker_1]`; `template_group`, `shifted_layout` | — |
| FR-011 single vs 題組 | `test_kind_iff_two_or_more_slots`; `test_edge_case[single_empty_answer]` | — |
| FR-011a slot cell has text | `test_edge_case[slot_cell_has_text]`, `test_slot_cell_warning_quotes_existing_text` | — |
| FR-012 count = numbered rows | `test_reference_sheet_matches_expected` (totals) | — |
| FR-013 no question text needed | `unit/test_fingerprint.py::test_ignores_text_and_warnings` | — |
| FR-014 / FR-014a spacer rows, stray text | `test_edge_case[spacer_rows_in_group|stray_answer_text]` | — |
| FR-015 error vs warning | `test_edge_case` (`can_confirm`); create/re-import `ImportHasErrors` / `WarningsNotAcknowledged` tests | — |
| FR-016 messages name row/cell + fix | `test_edge_case` (every message names its cells and rows) | M5 (wording) |
| FR-017 / FR-018 preview content, totals | `integration/test_import_api.py::test_preview_shape` | M3 (UI) |
| FR-019 group count 2–12 | `test_invalid_group_count`, `test_group_count_bounds`, `test_create_invalid_group_count_422` | M6 |
| FR-020 create DRAFT | `test_create_stores_exactly_the_confirmed_preview`, `test_create_activity_201` | M6 |
| FR-020a one current activity | `test_current_activity_blocks_create`, `integration/test_one_current_activity_concurrency.py`, `test_closed_activities_are_kept_unchanged` | M7 |
| FR-021 cell locations stored | `test_create_stores_exactly_the_confirmed_preview` | — |
| FR-022 sheet changed → nothing created | `test_preview_changed_creates_nothing`, `test_create_preview_changed_409` | M9 |
| FR-023 all-or-nothing | `test_create_is_all_or_nothing` | — |
| FR-024 / FR-025 re-import replaces; phase and group count kept | `test_reimport_replaces_the_whole_question_set`, `test_reimport_is_all_or_nothing`, `test_put_questions_replaces_set` | M8 |
| FR-026 phase re-checked at confirm | `test_reimport_rechecks_phase_at_confirm`, `test_put_rechecks_phase_at_confirm` | — |
| SC-001 preview < 5 s | `test_preview_of_200_row_sheet_is_fast` (local part < 1 s) | M3 (real Google) |
| SC-002 100% on ≥ 3 sheet shapes | `test_reference_sheet_matches_expected` ×3 | — |
| SC-003 paste → DRAFT < 2 min | — | M6 |
| SC-004 messages actionable | `test_edge_case` message checks | M5 |
| SC-005 zero sheet changes | read-only tests above | M10 |
| SC-006 re-import refused when OPEN/CLOSED | `test_reimport_refused_when_not_draft`, `test_reimport_refused_409` | — |

### Gaps (open until section 1 is filled in)

- **Real Google behaviour** (M1, M3, M4, M10): only exercised through a stub API object and the
  fake adapter so far.
- **SC-001 end to end, SC-003, SC-004 wording**: need the timings and judgement from M3, M5, M6.
- **Teacher page in a browser**: the JavaScript is syntax-checked and the API it calls is fully
  tested, but no browser test exists; M3 and M6–M8 cover the page by hand.
- **Code-vs-diagram check**: done, see [diagrams/VERIFICATION.md](../diagrams/VERIFICATION.md).

---

# Feature 002 — Live Buzz-In Activity

Spec: [specs/002-live-buzz-activity/spec.md](../specs/002-live-buzz-activity/spec.md) ·
Tasks: [tasks.md](../specs/002-live-buzz-activity/tasks.md). Baseline before 002 work: **210
passed** at `35e0ee5` (2026-11-27).

## Test-first record (002)

Each core-rule test was written first, run, and **observed failing** before its implementation.

| Phase | Tests written first | Red run (summary) | Green run | Commit |
|---|---|---|---|---|
| 2 · Foundational: passcode config, teacher guard, schema, visibility filter, student state | `unit/test_config.py`, `unit/test_teacher_sessions.py`, `unit/test_visibility.py`, `unit/test_db.py` (002 part), `integration/test_teacher_guard.py`, `integration/test_ws_student.py` (state part) | 41 failed, 2 collection errors (`api.auth`, `services.visibility` missing), 11 passed (pre-existing `test_db` tests) | 272 passed (full suite) | `f76e580` |
| 3 · US1 open + dashboard shape | `unit/test_activity_phases.py` (open, dashboard shape), `integration/test_phase_concurrency.py` (open vs open, 20 rounds), `integration/test_live_flow_api.py` (open) | 5 failed, 2 collection errors (`PhaseConflict` missing) | 287 passed (full suite) | `b9ab24e` |
| 4 · US2 join, change group, submit + ranking | `unit/test_participation_service.py`, `unit/test_ranking.py`, `integration/test_submit_concurrency.py` (100 rounds × 12 groups; same-group race ×50), `integration/test_student_api.py` | 17 failed, 3 collection errors (service exceptions missing) | 365 passed (full suite) | `83ecf66` |
| 5 · US3 dashboard + end + displayed activity | `unit/test_activity_phases.py` (end, zero submissions, displayed activity, import after end), `integration/test_submit_concurrency.py` (submit vs end, 50 rounds), `integration/test_dashboard_api.py`, `integration/test_ws_teacher.py` (002 part) | 16 failed (first attempt hung on a blocking WebSocket receive; added a timed `recv` helper, then re-ran red) | 383 passed (full suite) | `7736c66` |
| 7 · US5 cancel a DRAFT activity (run before US4, as instructed) | `unit/test_activity_phases.py` (cancel), `integration/test_phase_concurrency.py` (open vs cancel, join vs cancel), `integration/test_live_flow_api.py` (cancel) | 4 failed, 1 collection error (`CancelRefused` missing) | 396 passed (full suite) | `4ef7dc4` |
| 6 · US4 teammates' live view + leak test | `unit/test_group_push.py`, `integration/test_visibility_leak.py` (SC-005), `integration/test_ws_student.py` (US4 part) | 7 failed; **3 reconnect-recovery tests passed on first run** (snapshot-on-connect from Phase 2 already covers FR-030), recorded as not red | 408 passed (full suite) | `26daae0` |
| 8 · Polish: log hygiene, push latency | `integration/test_logs_002.py`, `integration/test_push_latency.py` | **not red**: both passed on their first run (they verify existing behaviour; not Principle V core rules) | 410 passed | Polish commit |

## Manual verification (M11–M25)

Scenarios from [quickstart.md §5](../specs/002-live-buzz-activity/quickstart.md). To be run by a
human tester on real devices on the classroom LAN (Principle V). Fill in Result and Evidence (no
secrets, no student data, Principle VI).

**Date**: · **Tester**: · **Commit**: · **Devices**:

| # | Steps (short) | Expected | Result | Evidence |
|---|---|---|---|---|
| M11 | Start without `TEACHER_PASSCODE` | Startup fails naming `TEACHER_PASSCODE` (FR-004) | check | |
| M12 | Wrong then right passcode on `/teacher` | Locked, then unlocked (US1 AS1–2) | check | |
| M13 | Student device calls `/api/teacher/…` | 401 `teacher_required`, no data (FR-002, SC-006) | check | |
| M14 | Student page before / after import | "No activity available yet", then join form without reload (FR-031) | check| |
| M15 | Join, duplicate names, change group in DRAFT | Accepted; dashboard lists members (FR-011, FR-013, FR-028) | check | |
| M16 | Open; time screen switch | All screens switch within 1 s; change group refused (SC-001) | check | |
| M17 | Whitespace answer, then valid 題組 | Refused naming sub-part; then accepted; teammate updates, other group unchanged (SC-002) | check | |
| M18 | Teammate resubmits | "Your group has already submitted question N" (FR-018) | check | |
| M19 | Two groups submit together | Ranks 1 and 2, one winner; no rank on student screens (FR-019, FR-023) | check | |
| M20 | DevTools on another group's device | No foreign answer, group, name or rank (SC-005) | check | |
| M21 | Refresh; Wi-Fi off/on | Same screen and group state; "Reconnecting…" (FR-030, SC-007) | check | |
| M22 | End while a student keeps submitting | Closed everywhere within 1 s; refused or ranked, never both; refresh keeps final dashboard (FR-029) | check | |
| M23 | Cancel a DRAFT with students joined, re-import | Students see "No activity available yet"; import succeeds (US5) | check | |
| M24 | Cancel an OPEN activity from a second tab | "An OPEN activity can only be ended" (US5 AS4) | check | |
| M25 | Server log after M11–M24 | No passcode, names or answers (FR-004, FR-032) | check | |

## Automated test runs (002)

| Date | Commit | Result | Notes |
|---|---|---|---|
| 2026-11-27 | `26daae0` + Polish | **410 passed**, 0 skipped, ~63 s | Includes SC-003 (100 rounds × 12 groups), submit vs end (50 rounds), the SC-005 leak test. Push latency at 60 student + 2 teacher sockets: OPEN 0.046–0.063 s, submission 0.015–0.031 s (3 runs; SC-001 / SC-002 target < 1 s) |
