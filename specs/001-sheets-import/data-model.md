# Data Model: Import Guided Notes Worksheet (001)

**Blueprint**: [diagrams/domain-class.puml](../../diagrams/domain-class.puml) — class and field
names below match it (diagram camelCase ↔ Python/SQL snake_case). Domain types live in
`src/quizbuzzer/models.py`; tables in `src/quizbuzzer/db.py`.

## Persisted entities (this feature)

### Activity → table `activities`

| Field (diagram) | Column | Type | Rules |
|---|---|---|---|
| id | id | INTEGER PK | autoincrement |
| title | title | TEXT NOT NULL | `"<spreadsheet title> – <tab title>"` |
| phase | phase | TEXT NOT NULL | CHECK in (`DRAFT`,`OPEN`,`CLOSED`); this feature writes `DRAFT` only |
| groupCount | group_count | INTEGER NOT NULL | CHECK 2–12 (FR-019); unchanged by re-import (FR-025) |
| sourceSpreadsheetId | source_spreadsheet_id | TEXT NOT NULL | from URL |
| sourceSheetId | source_sheet_id | INTEGER NOT NULL | tab's `sheetId` (gid) |
| sourceTabTitle | source_tab_title | TEXT NOT NULL | tab title at import time (needed by 003 export ranges) |
| createdAt | created_at | TEXT NOT NULL | ISO-8601 UTC, server clock |
| importedAt | imported_at | TEXT NOT NULL | updated on re-import |

Index `one_current_activity`: partial unique index allowing at most one row with phase in
(`DRAFT`,`OPEN`) (FR-020a; see research R7).

### QuestionUnit → table `question_units`

| Field | Column | Type | Rules |
|---|---|---|---|
| id | id | INTEGER PK | autoincrement: never reused after re-import deletes units |
| activity_id *(FK; not drawn in diagram)* | activity_id | INTEGER NOT NULL | FK → activities.id ON DELETE CASCADE |
| number | number | INTEGER NOT NULL | > 0; UNIQUE(activity_id, number) (duplicates are an import error) |
| kind | kind | TEXT NOT NULL | CHECK in (`SINGLE`,`GROUP_SET`) |
| sourceRow | source_row | INTEGER NOT NULL | 1-based row of the numbered row |
| position | position | INTEGER NOT NULL | 0-based order in sheet; UNIQUE(activity_id, position) |

### AnswerSlot → table `answer_slots`

| Field | Column | Type | Rules |
|---|---|---|---|
| id | id | INTEGER PK | autoincrement: never reused after re-import deletes slots |
| unit_id *(FK; not drawn in diagram)* | unit_id | INTEGER NOT NULL | FK → question_units.id ON DELETE CASCADE |
| subPart | sub_part | INTEGER NOT NULL | > 0; 1 for SINGLE; UNIQUE(unit_id, sub_part) |
| cellRow | cell_row | INTEGER NOT NULL | 1-based; top-left of merge if merged |
| cellColumn | cell_column | INTEGER NOT NULL | 1-based |
| a1Ref | a1_ref | TEXT NOT NULL | e.g. `D12`, derived from row/column (never typed in code) |

Invariants checked by tests: a unit has ≥ 1 slot; `kind = GROUP_SET` ⇔ slot count ≥ 2.

## Transient types (not stored) — `models.py`

| Type | Fields |
|---|---|
| `SpreadsheetInfo` | spreadsheet_id, title, tabs: list[`TabInfo`(sheet_id, title, index)], requested_gid: int \| None |
| `TabData` | spreadsheet_id, spreadsheet_title, sheet_id, title (tab title), grid: list[list[str]] (displayed values; ragged rows allowed), merges: list[(r0, r1, c0, c1)] (0-based, half-open; research R2) |
| `HeaderInfo` | row, number_column, answer_column (1-based) |
| `ParsedSlot` | sub_part, row, column, a1_ref, existing_text |
| `ParsedUnit` | number, kind, source_row, slots: list[ParsedSlot] |
| `Issue` | severity (`error`/`warning`), code, message, cells: list[str] (A1 refs), rows: list[int] |
| `ImportPreview` | header: HeaderInfo \| None, units, issues, total_units, total_slots, fingerprint, can_confirm (no errors) |

`parse(grid, merges)` returns an `ImportPreview` without spreadsheet/tab identity; the
`ActivityService` adds `spreadsheet_id`, `sheet_id`, `tab_title` before computing the
fingerprint and returning it to the API.

### Issue codes

| Code | Severity | Spec |
|---|---|---|
| `header_not_found` | error | Edge: no single row holds both labels; message names 題號 and 作答. If both labels exist but only in different rows, the message also names those cells (spec edge case "labels in different rows") |
| `header_ambiguous` | error | label appears twice in header row; names the cells |
| `no_questions` | error | zero numbered rows |
| `duplicate_question_number` | error | FR-008a |
| `orphan_sub_part` | error | marker above first numbered row |
| `duplicate_sub_part` | error | same （k） twice in one question |
| `question_number_gap` | warning | missing numbers in 1..max |
| `question_number_out_of_order` | warning | sheet order ≠ numeric order |
| `unrecognised_question_number` | warning | FR-008a (row + content) |
| `sub_part_gap` | warning | missing k in 1..max |
| `slot_cell_has_text` | warning | FR-011a (cell + text) |
| `stray_answer_text` | warning | FR-014a (cell + text); also FR-010 when a numbered row followed by （1） has text in its answer cell |

## State transitions

```text
(none) --create_from_import--> DRAFT --replace_questions--> DRAFT
DRAFT --(feature: open activity)--> OPEN --(feature: close)--> CLOSED
```

- Create: refused if any DRAFT/OPEN exists (FR-020a).
- Re-import: allowed only in DRAFT, re-checked inside the write transaction (FR-026).
- CLOSED rows are never modified or deleted by this feature.

## Later-feature tables (not created by 001)

`groups`, `participants`, `submissions` per the domain diagram. Submissions will use
`UNIQUE(group_id, unit_id)` and a server `arrival_seq` assigned under `BEGIN IMMEDIATE`
(research R7).
