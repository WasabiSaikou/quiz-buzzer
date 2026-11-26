# Data Model: Results, Sheet Export and CSV Download (003)

**Spec**: [spec.md](spec.md) · **Diagram**: [domain-class.puml](../../diagrams/domain-class.puml)

003 adds **no tables and no columns** (research R8). It reads 001's `activities`,
`question_units`, `answer_slots` and 002's `participants`, `submissions`,
`submission_answers`, and never writes to them (FR-022).

## Transient types (`models.py`, not stored)

### ResultEntry

| Field | Type | Notes |
|---|---|---|
| `rank` | int ≥ 1 | from `submissions.rank` |
| `group_number` | int | |
| `is_winner` | bool | `rank == 1` |
| `answers` | tuple[(sub_part, text)] | sub-part order |
| `submitted_by` | str | display name; **teacher only** |
| `received_at` | str | ISO-8601 UTC ms; **teacher only** |

### UnitResult

| Field | Type | Notes |
|---|---|---|
| `unit_id`, `number`, `kind`, `sub_parts` | | from the unit |
| `entries` | tuple[ResultEntry] | rank order |
| `winner` (property) | ResultEntry \| None | rank-1 entry |
| `no_answer` (property) | bool | `not entries` → UI shows 無人作答 |

### ActivityResults

| Field | Type | Notes |
|---|---|---|
| `activity_id`, `title`, `phase`, `group_count` | | `phase` is always CLOSED when built for output |
| `units` | tuple[UnitResult] | sheet order (`position`) |

The student form (`StudentResults`) is produced by `visibility.student_view`: the same units
with entries reduced to `{rank, isWinner, groupNumber, answers}`.

### PastActivitySummary

`activity_id, title, created_at, group_count, unit_count, submission_count`.

### CellWrite

| Field | Type | Notes |
|---|---|---|
| `a1_ref` | str | from the **re-parsed** slot (e.g. `G9`), never the stored one |
| `text` | str | `answer` (SINGLE) or `（k）answer` (GROUP_SET), sent RAW |

### ExportProblem

| Field | Type | Notes |
|---|---|---|
| `kind` | `parse_error` \| `missing_question` \| `missing_sub_part` | |
| `question_number` | int \| None | |
| `sub_part` | int \| None | |
| `code` | str \| None | the 001 issue code for `parse_error` |
| `message` | str | teacher-facing |

### ExportReport

`cells_written: int`, `units_written: int`, `units_skipped: int` (units with no winner).

## Validation and rules

| Rule | Where |
|---|---|
| Results, export and CSV only when phase = CLOSED | `ResultsService` (teacher), `ParticipationService._member_view` + `student_view` (student) |
| Student entries never carry `submittedBy` / `receivedAt` | `student_view` |
| Export targets come only from a fresh parse of the tab found by `source_sheet_id` | `SheetExporter.export`, `plan_export` |
| Any parse error / missing question / missing sub-part of a winning unit → zero writes | `plan_export` raises `ExportBlocked` before `write_cells` |
| Single write request, RAW | `GoogleSheetsWriter.write_cells` |
| Zero winners → no Google call | `SheetExporter.export` |
| CSV answer starting with `= + - @` → `'` prefix | `csv_export.to_csv` |

## State transitions

None. 003 never changes a phase. CLOSED stays final (002).

## Queries added to `db.py`

| Function | Purpose |
|---|---|
| `list_closed_activities(conn)` | past list with unit and submission counts, `id DESC` |

Existing queries reused: `get_activity_with_units`, `list_dashboard_submissions` (all
submissions of an activity in sheet then rank order, with answers and display names).
