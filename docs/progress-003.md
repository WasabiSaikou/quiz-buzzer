# Feature 003 — Unattended run report

**Date**: 2026-11-27 · **Branch**: `master` (not pushed) · **Spec**: [specs/003-results-export](../specs/003-results-export/spec.md)

**Status**: finished. Every phase is done, from specify to Polish. Two tasks are left open on
purpose: T039 (README) and T040 (manual checks), as instructed. No blockers. No test was skipped,
weakened or marked xfail, and none needed three fix attempts.

## Phases and commits

| Phase | Commit | Full suite after |
|---|---|---|
| Spec, checklist, diagrams (`/speckit-specify`) | `e86b4d8` | 410 passed (baseline) |
| Plan, research, data model, contracts, quickstart, tasks; analyze fixes | `01ffa52` | — (docs only) |
| 1 · Setup: result/export types, `SheetsWriter`, fake writer (T001–T004) | `9914a48` | 416 passed |
| 2 · Foundational: `ResultsService`, `build_results`, CLOSED-only refusals (T005–T007) | `164575c` | 427 passed |
| 3 · US1 (P1) students see results after CLOSED (T008–T013) | `855c832` | 439 passed |
| 4 · US2 (P1) teacher results + export to sheet (T014–T024) | `53fa228` | 519 passed |
| 5 · US3 (P2) CSV download (T025–T029) | `72b913f` | 544 passed |
| 6 · US4 (P3) past CLOSED activities (T030–T033) | `3d84633` | 549 passed |
| 7 · Polish: logs, CLOSED push latency, code-vs-diagram, consistency (T034–T038) | `eea2f30` | **550 passed**, 0 skipped, ~77 s |

The red run of every phase is recorded in `docs/verification.md` › Test-first record (003).

## `/speckit-analyze`

- **Run 1**: 0 critical, **1 high (C1)**: constrained-field citations in tasks.md used wildcards
  (`ResultEntry.*`), and T007, T011 and T021 cited no fields. Also 2 medium findings: G1 (no
  latency check for the heavier CLOSED push) and I1 (diagram names `build_results(activity)` and
  `forStudent()` did not match the plan).
- **Fixed**: exact `Entity.field` citations; new task T035 (CLOSED push latency); diagrams renamed
  and re-rendered.
- **Run 2**: 0 critical, 0 high. 3 low findings left as they are: U1 (no test that the DB is
  unchanged after export or CSV), U2 (export of a past activity has no test of its own; it uses
  the same code path), U3 (the export `not_found` message reuses the import wording "check the
  link").

## Decisions and deviations

Each one is recorded in the spec, plan, contracts or data model in the same commit.

1. **Separate write client** (your instruction; research R1): new `SheetsWriter` protocol and
   `GoogleSheetsWriter` with its own credentials and the `spreadsheets` scope. The import
   `GoogleSheetsAdapter` stays on `spreadsheets.readonly` and has no write method; a test checks
   both scopes.
2. **Error codes**: `export_blocked` (409, lists every problem), `export_not_shared` (403, the
   re-read failed; asks for **Editor**), `sheet_read_only` (403, the write was refused). Both 403s
   name the service-account email. Gone tab → `not_found`; Google down → `sheets_unavailable`.
3. **Zero winners → no Google call at all**, not even the re-read. The report says 0 cells.
4. **Only winning units are re-located.** A deleted question nobody answered does not block the
   export. Sub-parts or questions added after import are ignored. The unit's kind stored at import
   decides the format (`answer` or `（k）answer`).
5. **Student results** go inside the existing `student.state` snapshot as a new `results` key.
   No new endpoint or message type. `student_view` adds the key only when all three hold: the
   activity is CLOSED, the participant is a member of it, and `results.activity_id` matches (an
   extra guard added during implementation, recorded in the 003 contract). Student entries carry
   `{rank, isWinner, groupNumber, answers}`: no names, no times.
6. **`ResultsService.load(activity_id, action)`** returns the activity and its results from one
   DB read. The exporter needs the stored units and slots. Recorded in plan.md and
   `003-seq-export-sheet`.
7. **CSV**: CRLF line endings; `sub_part` empty for single questions; `submitted_at` written as
   `…+00:00` (the stored value is `…Z`); the `'` prefix applies to the answer column only. The
   file name is `activity-<id>.csv`, with a UTF-8 `filename*` holding the cleaned-up title (at most
   60 characters).
8. **Past list order**: `id DESC` (ids only grow), so no `closed_at` column was needed. No schema
   change in 003 at all.
9. **Two 002 test assertions changed because the spec changed** (003 FR-002 reverses 002's rule
   that a CLOSED student sees only their own group). Recorded in `docs/verification.md` › "002
   tests changed by 003":
   - The end of `test_visibility_leak.py` now requires the full results in the CLOSED snapshot,
     still with no names. Every pre-CLOSED assertion is unchanged.
   - `test_dashboard_api.py::test_end_moves_students_to_closed_with_own_submissions_only`: the
     "other group's answer nowhere" check now covers only the `group` section, plus a new check
     that `results` holds both groups' answers.
10. **Code-vs-diagram** (`diagrams/VERIFICATION.md` › Feature 003). Four diagram corrections:
    - E8: the exporter calls `load`.
    - E9: field names in the result types.
    - E10: results are built per member key inside the publish loop; `state_for_token`.
    - E11: `ORDER BY id DESC`.

    Re-rendered: exit 0, 16/16 PNGs.
11. **No new dependencies.**

## Things to know

- **Your uncommitted edits were swept into one of my commits.** When the run started you had
  uncommitted changes in `specs/001-sheets-import/tasks.md` and
  `specs/002-live-buzz-activity/tasks.md`: ticking 001 T045 and 002 T052, the README tasks.
  `git add specs` in the US1 commit `855c832` included them. The content is yours and unchanged;
  only where it was committed is wrong. Your `README.md` change and `docs/ai-logs/` are still
  uncommitted and untouched. Nothing is pushed. If you want these two files out of `855c832`, it
  can be split with an interactive rebase. I did not rewrite history without asking.
- Performance: the CLOSED push now builds results for each member key. With 60 students in 12
  groups and every unit answered, it reached every socket in 0.265 s (target < 1 s). If classes
  grow a lot, build the results once per publish instead of once per key.
- Not read or touched: `.env`, `secrets/`.

## Manual checks for you (T040; `specs/003-results-export/quickstart.md` §4)

Before you start, share the worksheet with the service account as **Editor**. Record the results
in `docs/verification.md` › 003 › Manual verification.

| # | What to do | What should happen |
|---|---|---|
| M31 | End an activity with students connected | Results on every student screen within 1 s, including a group that never submitted. 無人作答 for unanswered units. No names or times on student screens |
| M32 | Refresh a student page | Results again |
| M33 | Teacher results panel | Names and times shown; Export and Download CSV buttons present |
| M34 | Share the sheet as **Viewer** only, then export | Error names the service-account email and asks for Editor access. Sheet unchanged |
| M35 | Share as Editor, insert 2 rows above the questions, rename the tab, then export | "N cells written". Answers land at the new rows; 題組 cells read `（1）…`. Unanswered cells and formatting unchanged |
| M36 | Export again | Same values, same count |
| M37 | Delete a winning 題組 sub-part row, then export | Refused, listing the missing sub-part. Sheet unchanged |
| M38 | Export an answer `=1+1` | The cell shows the text `=1+1` |
| M39 | Open the CSV in Excel (double-click) and in Google Sheets | Chinese text correct. Commas, quotes and line breaks stay in one cell. `'=1+1` shown as text |
| M40 | Close a second activity, open Past activities | Newest first; the older activity's results open correctly |
| M41 | From a student browser, call `…/results.csv` and `…/export` | 401 `teacher_required` |
| M42 | Check the server log | No answer text, no display names |

Also still open: **T039**, the README section for 003 (results, export needs Editor access, CSV).
The dependency table does not change.

**Update (2026-11-27, after the run)**: T039 (README) is done, and the constitution was amended to 1.1.0 (review rule no longer refers to pull requests). Only T040 (manual checks) remains.
