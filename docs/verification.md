# Verification Record — Feature 001 Import Guided Notes Worksheet

Constitution Principle V: a core feature needs executed tests **and** a recorded manual check.
"The AI says it works" is not verification.

## 1. Manual verification (M1–M10)

Scenarios come from [quickstart.md §6](../specs/001-sheets-import/quickstart.md). Run them against
a real Google sheet shared with the service account, with the app started as described in
quickstart §3. Fill in **Result** (pass / fail, with what was observed) and **Evidence** (a
screenshot path, timing, or log excerpt with no secrets or personal data, per Principle VI).

**Date**: ______ · **Tester**: ______ · **Commit**: ______ · **Sheet(s) used**: ______

| # | Steps | Expected | Result | Evidence |
|---|---|---|---|---|
| M1 | Paste a link to a sheet **not** shared with the service account | Error shows the service account email and says to share as Viewer (FR-004) | | |
| M2 | Paste `https://example.com/x` | "Not a Google Sheets link"; no Google request in the server log (FR-002) | | |
| M3 | Share a course template, paste its link. Time from paste to preview. | First tab preselected; preview lists every question with type, sub-part count and answer cell (`tab!A1`); preview appears within 5 s (SC-001) | | |
| M4 | Paste the same link with `#gid=` of the second tab | Second tab preselected (FR-003) | | |
| M5 | Add `備註` in the 題號 column, refresh the preview | Warning names the row and `備註`, and says what to change (FR-008a, FR-016, SC-004) | | |
| M6 | Confirm with 6 groups (acknowledging warnings). Time from M3's paste to the DRAFT activity. | DRAFT activity shown with 6 groups and the same slots; a second open `/teacher` tab updates without reloading; under 2 minutes (SC-003) | | |
| M7 | Try to create another activity | Refused: names the current DRAFT activity and suggests re-import (FR-020a) | | |
| M8 | Edit the sheet (add a question), re-import, confirm | The activity now has the new question set; phase and group count unchanged (FR-024, FR-025) | | |
| M9 | Preview, then edit the sheet structure, then confirm | Refused with the updated preview (FR-022) | | |
| M10 | Open the sheet's version history after M3–M9 | No edits by the service account (FR-005, SC-005) | | |

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
