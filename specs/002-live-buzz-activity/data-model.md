# Data Model: Live Buzz-In Activity (002)

Source of truth: [domain-class.puml](../../diagrams/domain-class.puml). Builds on
[001 data-model](../001-sheets-import/data-model.md), whose tables `activities`,
`question_units` and `answer_slots` are **unchanged**. New tables are added to `db.SCHEMA` with
`CREATE TABLE IF NOT EXISTS`, so an existing 001 database gains them at startup (research R5).
Timestamps are ISO-8601 UTC strings, as in 001. Strings stored here are already trimmed.

## Persisted entities (new in 002)

### Participant → table `participants`

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | ids are never reused |
| `activity_id` | INTEGER NOT NULL → `activities(id)` ON DELETE CASCADE | a cancel deletes participants (FR-008a) |
| `group_number` | INTEGER NOT NULL CHECK (`group_number` BETWEEN 1 AND 12) | ≤ `activities.group_count`, checked in the join transaction (FR-009) |
| `display_name` | TEXT NOT NULL CHECK (`length(display_name)` BETWEEN 1 AND 20) | trimmed; not unique (FR-011); never logged (FR-032) |
| `token_hash` | TEXT NOT NULL UNIQUE | `sha256(token)` hex; the token itself is only in the browser's `qb_participant` cookie (research R2) |
| `joined_at` | TEXT NOT NULL | server UTC |

Index: `(activity_id, group_number)` for group lookups.

Lifecycle:
- **Created** by a join while the phase is DRAFT or OPEN (FR-010).
- **Deleted** by "Change group", only while DRAFT (FR-013), or by a cascade when its DRAFT
  activity is cancelled.
- Never deleted while OPEN or CLOSED, because submissions reference it.

### Group (value; no table, research R4)

Identified by `(activity_id, group_number)`, where `group_number ∈ 1..activities.group_count`.
Members = the participants with that pair. Groups with no members exist implicitly (FR-028).

### Submission → table `submissions`

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `unit_id` | INTEGER NOT NULL → `question_units(id)` ON DELETE CASCADE | the unit's activity = the participant's activity (checked in the transaction) |
| `group_number` | INTEGER NOT NULL CHECK (BETWEEN 1 AND 12) | copied from the participant at submit time (FR-014) |
| `participant_id` | INTEGER NOT NULL → `participants(id)` | the submitter (FR-020) |
| `rank` | INTEGER NOT NULL CHECK (`rank` >= 1) | `1 + count(earlier submissions of unit)`, assigned in the submit transaction (FR-019) |
| `received_at` | TEXT NOT NULL | server UTC with milliseconds, set inside the submit transaction; shown on the dashboard and **required by feature 003's CSV export**; never used to order or rank |

Constraints:
- `UNIQUE (unit_id, group_number)`: one submission per group per unit (FR-018).
- `UNIQUE (unit_id, rank)`: there can never be two rows with the same rank, including two
  winners (Constitution I).

Derived: `is_winner = (rank = 1)`. The ranks of a unit are always exactly 1..n.

### SubmissionAnswer → table `submission_answers`

| Column | Type | Rules |
|---|---|---|
| `submission_id` | INTEGER NOT NULL → `submissions(id)` ON DELETE CASCADE | |
| `slot_id` | INTEGER NOT NULL → `answer_slots(id)` | the slot belongs to the submission's unit |
| `text` | TEXT NOT NULL CHECK (`length(text)` BETWEEN 1 AND 200) | trimmed (FR-016); never logged |

PK `(submission_id, slot_id)`. A submission has exactly one row per slot of its unit.

## In-memory entities

### TeacherSessions (`api/auth.py`)

`tokens: set[str]`, guarded by a `threading.Lock`. It is filled by `create(passcode)` after a
`hmac.compare_digest` match and emptied on restart (FR-003). The passcode is never stored
(FR-004).

### StudentKey (`realtime/hub.py`)

`(activity_id, participant_id, group_number)`, or `None` for a socket without a valid
membership. It is resolved once when a `/ws/student` socket connects (research R6).

## Validation rules (summary)

| Input | Rule | Error |
|---|---|---|
| passcode | equals `TEACHER_PASSCODE` (constant-time) | 401 `wrong_passcode` |
| display name | `strip()` → 1–20 characters | 422 `invalid_join` (`details.field = "displayName"`) |
| group number | integer in 1..group_count | 422 `invalid_join` (`details.field = "groupNumber"`) |
| answer text | `strip()` → 1–200 characters, for every slot | 422 `invalid_answers` (`details.subParts = [k, …]`, `details.reasons`) |
| answer set | the `subPart`s are exactly the unit's slots, with no duplicates | 422 `invalid_answers` |

`strip()` is Python's `str.strip()`, which removes all Unicode whitespace, including U+3000
(full-width space) and line breaks.

## State transitions

```text
(none) --create (001)--> DRAFT --re-import (001)--> DRAFT
DRAFT --open--> OPEN --end--> CLOSED
DRAFT --cancel--> (deleted: activity, units, slots, participants)
```

| Request | DRAFT | OPEN | CLOSED | missing |
|---|---|---|---|---|
| open | → OPEN | 409 `phase_conflict` | 409 `phase_conflict` | 404 |
| end | 409 `phase_conflict` (suggests Cancel) | → CLOSED | 409 `phase_conflict` | 404 |
| cancel | delete | 409 `cancel_refused` ("can only be ended") | 409 `cancel_refused` | 404 |
| join | ✓ | ✓ | 409 `join_refused` | 409 `join_refused` (no current activity) |
| change group | ✓ | 409 `group_change_refused` | 409 `group_change_refused` | 401 `not_a_member` |
| submit | 409 `not_open` | ✓ (or 409 `already_submitted`) | 409 `activity_ended` | 401 `not_a_member` |
| re-import (001) | ✓ | 409 `reimport_refused` | 409 `reimport_refused` | 404 |

Every cell above is decided inside one `BEGIN IMMEDIATE` transaction (FR-006, FR-008b, FR-019).
CLOSED activities and their submissions are never modified or deleted.

## Queries added to `db.py`

`find_latest_activity` (R7), `get_phase_for_update` (reuses `get_activity_phase` inside the
transaction), `delete_activity`, `set_phase`, `insert_participant`, `find_participant_by_token_hash`,
`delete_participant`, `list_group_members`, `list_members_by_group`, `count_unit_submissions`,
`group_has_submitted`, `insert_submission` (+ answers), `list_group_submissions`,
`list_dashboard_submissions` (all units, rank order). Each one takes the caller's connection, so
that it runs inside the caller's transaction.
