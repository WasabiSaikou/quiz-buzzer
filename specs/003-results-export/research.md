# Research: Results, Sheet Export and CSV Download (003)

**Date**: 2026-11-27 · **Spec**: [spec.md](spec.md) · **Builds on**:
[001 research](../001-sheets-import/research.md) (R1 environment, R5 Google client, R7 SQLite,
R8 sync endpoints, R9 testing, R10 dependencies) and
[002 research](../002-live-buzz-activity/research.md) (R1 teacher guard, R6 snapshots through one
student path, R7 displayed activity, R9 testing). All of these still apply.

The Technical Context had no open items: the stack, storage and test tooling are 001/002's. Each
section records a design decision the spec left open.

## R1. A separate write-scoped Sheets client (FR-010, FR-013, FR-014)

- **Decision**:
  - New protocol `SheetsWriter` in `services/sheets_adapter.py` with one method,
    `write_cells(spreadsheet_id, sheet_id, tab_title, cells) -> int`, plus
    `service_account_email`. New error `SheetReadOnly(service_account_email)`.
  - New module `services/google_sheets_writer.py: GoogleSheetsWriter`, which builds its **own**
    credentials with scope `https://www.googleapis.com/auth/spreadsheets` and sends exactly one
    `spreadsheets.values.batchUpdate` with `valueInputOption: "RAW"` and one `ValueRange` per
    cell (`range = '<tab title>'!<A1>`, `values = [[text]]`). It returns
    `totalUpdatedCells` (falls back to `len(cells)` if Google omits it).
  - `GoogleSheetsAdapter` (import) keeps `spreadsheets.readonly` and gains no write method, so
    001 FR-005 stays enforced by the credential.
  - The exporter re-reads with the **read-only adapter** and writes with the **writer**.
  - Error mapping for the write: 403 with `SERVICE_DISABLED` / "has not been used" →
    `SheetsUnavailable`; any other 403 → `SheetReadOnly` (the re-read just succeeded, so the
    account can see the sheet but not edit it); 404 → `SheetNotFound`; anything else, timeouts
    and transport errors → `SheetsUnavailable`.
  - `main.py` wires a `LazyGoogleSheetsWriter` (same lazy pattern as the adapter), and
    `create_app(..., writer=...)` lets tests inject a fake.
- **Rationale**: The user's instruction and FR-014. One client with the write scope for both
  paths would let an import bug write to a teacher's sheet; two clients make that impossible.
  Distinguishing "not shared" (read fails) from "view-only" (read works, write 403) falls out
  naturally from reading first with one client and writing with the other.
- **Alternatives considered**: one adapter with both scopes (rejected: weakens FR-005);
  `spreadsheets.batchUpdate` with `updateCells` + `GridRange(sheetId)` (rejected: the spec names
  `values.batchUpdate` RAW, and `updateCells` can touch formatting unless masked carefully).

## R2. Using the sheetId, not the title (FR-008)

- **Decision**: The exporter calls `adapter.read_tab(source_spreadsheet_id, source_sheet_id)`.
  `read_tab` already finds the tab by `sheetId` and returns its **current** title. The A1 ranges
  sent to `values.batchUpdate` are built from that current title (quoted with
  `quote_tab_title`, single quotes doubled). The stored `source_tab_title` is never used for
  export.
- **Rationale**: `values.batchUpdate` only accepts A1 ranges, which need a title; resolving the
  title from the fixed `sheetId` at export time makes a rename harmless. If the tab is renamed in
  the instant between read and write, Google rejects the unknown range for the whole request
  (400), which maps to `SheetsUnavailable`: nothing is written and nothing is reported as written.
- **Alternatives considered**: storing and trusting `source_tab_title` (fails on rename).

## R3. Re-locating slots with the 001 parser (FR-008, FR-009; Constitution II)

- **Decision**: `services/sheet_exporter.py: plan_export(activity, results, preview)` is a
  **pure** function:
  1. If `preview.errors` is non-empty, every error becomes an `ExportProblem(kind="parse_error",
     code, message)`. Warnings are ignored.
  2. Otherwise, for every unit of the activity that has a winner, find the parsed unit with the
     same `number`; if absent → `missing_question`. For each stored slot `sub_part` of that unit,
     find the parsed slot with the same `sub_part`; if absent → `missing_sub_part`.
  3. Any problem → `ExportBlocked(problems)`; no `CellWrite` is produced.
  4. Otherwise one `CellWrite(a1_ref=<parsed slot a1_ref>, text=...)` per winning slot, in sheet
     order.
  `SheetExporter.export(activity_id)` does the I/O around it (read results, read tab,
  `guided_notes_parser.parse(grid, merges)`, `plan_export`, `write_cells`).
- The stored `AnswerSlot.cell_row/cell_column/a1_ref` are **never** a write target.
- Units without a winner are not looked up, so deleting an unanswered question does not block
  the export (spec Edge Cases).
- Sub-parts or questions added after import are ignored (only stored slots are written).
- **Rationale**: Reusing `parse` means export and import agree on what a question and a
  sub-part are (header search, number formats, full-width markers, merges → top-left cell).
  Keeping `plan_export` pure lets the "≥ 3 differently shaped sheets" gate (Principle II) run as
  fast unit tests on the existing fixtures (`template_single.csv`, `template_group.csv`,
  `shifted_layout.json` tab `練習`) with and without inserted rows.
- **Alternatives considered**: checking that the stored cell still holds a marker (fragile, and
  still a hardcoded address); fuzzy matching (not in spec).

## R4. Cell text format (FR-007)

- **Decision**: `format_cell(kind, sub_part, answer)`: `SINGLE` → `answer`; `GROUP_SET` →
  `"（" + str(sub_part) + "）" + answer`, with U+FF08 / U+FF09 and half-width digits. The unit's
  `kind` stored at import decides the format, not the kind in the re-parsed sheet.
- **Rationale**: 001's recorded decision. Half-width digits inside full-width parentheses match
  the 001 fixtures (`（1）`) and are recognised again by the parser, so a re-import after export
  still detects the same sub-parts.

## R5. Results shape and the student path (FR-001 – FR-005; Constitution III)

- **Decision**:
  - `services/results_service.py: build_results(activity, submissions) -> ActivityResults` is
    pure. Units in `position` order, each with its submissions in rank order; `winner` = the
    rank-1 entry or `None`.
  - `ResultsService(db_path)` reads the rows and exposes `teacher_results(activity_id)`,
    `results_for(activity)` (no phase check, used by ParticipationService only after it has
    checked CLOSED), `list_closed()` and `results_csv(activity_id)`.
  - Teacher endpoints refuse DRAFT/OPEN with the existing `PhaseConflict` (409
    `phase_conflict`, `details.phase`), with new messages for the actions `results`, `export`
    and `csv`: "Results are available once the activity is CLOSED; it is <phase>."
  - **Students**: `ParticipationService._member_view` builds results **only** when the activity
    is CLOSED and passes them to `visibility.student_view(..., results=...)` (new keyword-only
    parameter, default `None`). `student_view` adds a `results` key **only** for a member whose
    activity is CLOSED, re-checking the phase itself, and strips `submittedBy` and `receivedAt`
    from every entry. In DRAFT/OPEN the output is byte-for-byte 002's.
  - The CLOSED push already happens: `end_activity` → `publish_student_states()` → every
    socket's snapshot through `_member_view`. No new message type.
- **Rationale**: Keeps the single student-bound path of 002 R6. Building results only after the
  CLOSED check, and the filter re-checking the phase, are two independent guards against a leak.
- **Alternatives considered**: a separate `GET /api/student/results` (rejected: a second
  student-bound path outside the snapshot, and the client would need extra reconnect logic).

## R6. CSV format (FR-015 – FR-019)

- **Decision**: `services/csv_export.py: to_csv(results) -> bytes`, pure:
  - `csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")` (RFC 4180). Python's
    minimal quoting quotes any field with `,`, `"`, `\r` or `\n` and doubles inner quotes.
  - Output = `"﻿"` + text, encoded UTF-8 (BOM so Excel detects UTF-8).
  - Rows: units in sheet order → submissions in rank → answers in sub-part order.
  - `sub_part`: the number for `GROUP_SET`, empty for `SINGLE`. `is_winner`: `true`/`false`.
  - `submitted_at`: the stored `received_at` (`…Z`, UTC, milliseconds) rewritten as
    `…+00:00`, i.e. ISO 8601 with an explicit offset.
  - Formula guard: if the answer's first character is one of `= + - @`, prefix `'`. Applied to
    `answer` only (other columns are numbers, booleans and timestamps the app generates).
- **File name** (FR-019): `Content-Disposition: attachment; filename="activity-<id>.csv";
  filename*=UTF-8''<percent-encoded "activity-<id>-<title>.csv">`, where the title has
  `\ / : * ? " < > |` and control characters replaced by `_`, is trimmed, and is cut to 60
  characters. The ASCII `filename` is the fallback for old browsers.
- **Media type**: `text/csv; charset=utf-8`.

## R7. Past activities (FR-023)

- **Decision**: `db.list_closed_activities(conn)` returns `id, title, created_at, group_count,
  unit_count, submission_count` for `phase = 'CLOSED'`, ordered `id DESC` (ids only grow, so
  newest first, the same reasoning as 002 R7). Route `GET /api/teacher/activities/closed`,
  declared before `/activities/{activity_id}`.
- **Rationale**: No new column (no `closed_at`) is needed for "newest first".

## R8. No schema change

- **Decision**: 003 adds no table and no column. Results, export reports and CSV are derived on
  request. Export history is not stored (spec Assumptions).
- **Rationale**: Principle VII (simplest design).

## R9. Testing approach for 003 (Constitution V)

- Test-first, observed failing, for:
  - slot re-location on ≥ 3 sheet shapes, with rows inserted above and between questions, a
    renamed tab, and a moved answer column (`tests/unit/test_sheet_exporter.py`);
  - the abort-with-nothing-written path: parse errors, a missing question, a missing sub-part,
    view-only, not shared, tab gone, Google unavailable — the fake writer records **zero**
    calls and the fake sheet is unchanged;
  - cell formatting single vs 題組, RAW (the fake stores text verbatim; the Google writer test
    checks the request body), one write call per export;
  - CSV quoting, BOM, line endings, formula prefix, empty CSV (`tests/unit/test_csv_export.py`);
  - CLOSED-only visibility of results (`tests/unit/test_visibility.py` extension and
    `tests/integration/test_visibility_leak.py` extension: nothing before CLOSED, full results
    after).
- `FakeSheetsAdapter` gains `write_cells` (writes into its own grid by sheet id, so a repeated
  export can be checked against the updated sheet), a `writes` log, and
  `make_read_only(spreadsheet_id)` to simulate a Viewer share.
- `tests/unit/test_google_sheets_writer.py` uses a mocked discovery service (as
  `test_google_sheets_adapter.py` does) to check the scope, the single `batchUpdate`, `RAW`,
  ranges built from the given title, and error mapping. No real Google access in tests.
- The existing route-iterating guard test (`test_teacher_guard.py`) covers the new teacher
  routes automatically; a test asserts they appear in its set.

## R10. Dependencies

- No new dependencies: `csv`, `io`, `urllib.parse` are stdlib; the Google client libraries are
  already listed. The README dependency table is unchanged.
