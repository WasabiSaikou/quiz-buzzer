# Implementation Plan: Import Guided Notes Worksheet

**Branch**: `001-sheets-import` (spec directory; work on `master`) | **Date**: 2026-11-26 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-sheets-import/spec.md`

## Summary

The teacher pastes a Google Sheets link, picks a tab (the `#gid=` tab, or the first tab), and
sees a preview of every detected question. The preview shows each question's number, its type
(SINGLE or 題組 / `GROUP_SET`), its sub-parts, and the answer cell for each slot, along with
errors and warnings. Confirming creates the single current activity in DRAFT. While the activity
is DRAFT, the teacher can re-import to replace its questions.

Technically:
- A pure `guided_notes_parser.parse(grid, merges)` locates everything from sheet content alone
  (Principle II).
- A `SheetsAdapter` interface is implemented by `GoogleSheetsAdapter` (read-only scope) and by
  `FakeSheetsAdapter` in tests.
- `ActivityService` orchestrates and writes to SQLite under `BEGIN IMMEDIATE`, with a partial
  unique index that allows only one current activity.
- `RealtimeHub` pushes `activity.state` to teacher sockets.
- All of it is served by one FastAPI process with a static `/teacher` page.

## Diagram Blueprint (Principle VIII)

The diagrams are the primary blueprint. The plan's module and class names match them exactly.

| Diagram element | Code |
|---|---|
| Teacher UI | `src/quizbuzzer/static/teacher.html`, `teacher.js` |
| Student UI | `static/student.html`, `student.js`: **later feature** (not built in 001) |
| API server | `main.py` (`create_app`, `app`), `api/teacher_routes.py`, `api/ws_routes.py`, `api/schemas.py` |
| Real-time channel | `realtime/hub.py`: `RealtimeHub` |
| Activity service | `services/activity_service.py`: `ActivityService` (`list_tabs`, `preview_import`, `create_from_import`, `check_reimport_allowed`, `preview_reimport`, `replace_questions`, `get_current_activity`, `get_activity`) |
| Guided Notes parser | `services/guided_notes_parser.py`: `parse(grid, merges) -> ImportPreview`; pure helper `compute_fingerprint(...)`, called by `ActivityService` |
| Sheets adapter | `services/sheets_adapter.py`: `SheetsAdapter` (Protocol: `list_tabs(spreadsheet_id)`, `read_tab(spreadsheet_id, sheet_id)`), errors `InvalidSheetUrl`, `SheetNotShared`, `SheetNotFound`, `SheetsUnavailable`; `services/google_sheets_adapter.py`: `GoogleSheetsAdapter`; tests: `tests/fakes/fake_sheets_adapter.py`: `FakeSheetsAdapter` |
| URL parsing | `services/sheets_url.py`: `parse_spreadsheet_url`, called by `ActivityService` before any adapter call |
| SQLite store | `db.py` (connection, schema, queries) and the DB file at `QUIZBUZZER_DB_PATH` |
| Domain classes | `models.py`: `Phase`, `UnitKind`, `Activity`, `QuestionUnit`, `AnswerSlot` (+ transient `SpreadsheetInfo`, `TabData`, `ImportPreview`, `Issue`, …) |
| Service exceptions (sequence diagrams) | `services/activity_service.py`: `InvalidGroupCount`, `ImportHasErrors`, `PreviewChanged`, `WarningsNotAcknowledged`, `CurrentActivityExists`, `ReimportRefused` |

**Diagram changes made during planning** (re-rendered 2026-11-26):
- The parser moved out of the Sheets adapter and is now called by `ActivityService`. This keeps
  the parser pure and lets the fake adapter supply grids.
- URL parsing moved out of the Sheets adapter too: `ActivityService` calls
  `parse_spreadsheet_url`, and the adapter takes a `spreadsheet_id`. The fingerprint is computed
  by `ActivityService` after `parse()` (re-rendered 2026-11-26, during `/speckit-analyze`).
- The API now calls `ActivityService` for everything.
- Participants are named after their classes and modules, and HTTP routes and status codes were
  added.
- A `SheetsUnavailable` (502) branch was added.
- The confirm and re-import flows now publish through `RealtimeHub` and use `BEGIN IMMEDIATE`.
- `domain-class`: added `Activity.sourceSheetId`; removed `AnswerSlot.tabTitle`, because the tab
  belongs to the activity (one source of truth); Python types.

## Technical Context

**Language/Version**: Python 3.11 (`requires-python = ">=3.11"`), managed with uv. The venv is
the project-local `quiz-buzzer\.venv` created by `uv sync`. Python is pinned with `uv python pin
3.11` (`.python-version`) and installed with `uv python install 3.11` when only MSYS2 Pythons
exist. The outer `..\.venv` is not touched (research R1).

**Primary Dependencies**: FastAPI, uvicorn + websockets, python-dotenv,
google-api-python-client, google-auth. Dev: pytest, httpx.

**Storage**: SQLite through the stdlib `sqlite3` module (WAL, foreign keys, `BEGIN IMMEDIATE`).

**Testing**: pytest + FastAPI `TestClient`. `FakeSheetsAdapter` is fed from
`tests/fixtures/sheets/*.json` and `*.csv` (research R9).

**Target Platform**: Windows 10/11 teacher laptop; students' browsers on the classroom LAN.

**Project Type**: Local web application (single process: API, WebSocket and static pages).

**Performance Goals**: Preview in under 5 s for a 200-row tab (SC-001). That's two Google
calls plus an O(rows) parse.

**Constraints**:
- Import is read-only (FR-005), enforced by the read-only OAuth scope.
- No hardcoded cell addresses (Principle II).
- No secrets in the repo (Principle VI).
- No build step for the frontend.

**Scale/Scope**: One teacher, one current activity, at most 12 groups. Sheets of up to about
500 rows / 200 questions.

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1 design.*

| Principle | How this plan complies | Pre | Post |
|---|---|---|---|
| I. Server-authoritative fairness | No ranking in 001. Create and re-import use `BEGIN IMMEDIATE` with a partial unique index, so two current activities are impossible, not just unlikely. The ranking design (`BEGIN IMMEDIATE` + `UNIQUE(group_id, unit_id)`, server `arrival_seq`) is recorded for the submissions feature. | ✅ | ✅ |
| II. Dynamic Guided Notes handling | `parse(grid, merges)` derives the header, columns, rows and slots from content only. The A1 reference is computed from row/column indices. The parser suite runs against at least 3 differently shaped fixtures (`template_single`, `template_group` + `shifted_layout`). | ✅ | ✅ |
| III. Information hiding until close | 001 only has teacher endpoints and sockets; no group data exists yet. The student channel is deferred, and the visibility filter is required there. | ✅ (N/A) | ✅ (N/A) |
| IV. Single source of truth for phase | Phase lives only in SQLite. `activity.state` is pushed after every change and sent on connect, so reconnecting clients recover. | ✅ | ✅ |
| V. Test-first for core rules | Parser, phase rules (create/re-import refusal, one current activity) and fingerprint/confirm tests are written and seen failing before the code. `verification.md` holds the manual records M1–M10 (quickstart). Export tests belong to 003. | ✅ | ✅ |
| VI. Secrets hygiene | The key path comes from `.env` (`GOOGLE_APPLICATION_CREDENTIALS`). `.env.example` has placeholders only. `secrets/`, `.env` and `*.db` are gitignored. Logs record issue codes and IDs, never cell text or credentials. | ✅ | ✅ |
| VII. Consistency and simplicity | The diagrams were updated in this plan. No ORM, no frontend build, no `uvicorn[standard]`. Only tables for 001 are created. The README dependency/licence table comes from research R10. | ✅ | ✅ |
| VIII. PlantUML design-first | The diagrams drive the module names (table above). They were re-rendered with `java -jar tools/plantuml.jar "./diagrams/*.puml"` (exit 0). `/speckit-implement` must end with a code-vs-diagram check. | ✅ | ✅ |

**Environment note** (research R1, no open item): the outer `.venv` is an MSYS2/mingw Python that
uv cannot use. It is left untouched, and the project uses its own uv-managed `.venv`.

## Project Structure

### Documentation (this feature)

```text
specs/001-sheets-import/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── rest-api.md      # Phase 1: REST endpoints + JSON examples
│   └── websocket.md     # Phase 1: WebSocket message types
├── checklists/requirements.md
├── verification.md      # manual verification records (created during implement)
└── tasks.md             # /speckit-tasks (not created here)
```

### Source Code (quiz-buzzer/)

```text
pyproject.toml                 # uv project; requires-python >=3.11
uv.lock
.python-version                # uv python pin 3.11 (committed); .venv/ is gitignored
.env.example                   # placeholders only
README.md                      # run instructions + dependency/licence table
diagrams/                      # *.puml + rendered *.png
src/quizbuzzer/
├── __init__.py
├── main.py                    # create_app(adapter, db_path); app; static mount; /teacher
├── config.py                  # loads .env (python-dotenv) → Settings
├── db.py                      # connect(), init_schema(), activity/unit/slot queries
├── models.py                  # Phase, UnitKind, Activity, QuestionUnit, AnswerSlot, transient types
├── services/
│   ├── __init__.py
│   ├── activity_service.py    # ActivityService + service exceptions
│   ├── guided_notes_parser.py # parse(grid, merges) — pure
│   ├── sheets_adapter.py      # SheetsAdapter Protocol + adapter errors
│   ├── google_sheets_adapter.py
│   └── sheets_url.py          # parse_spreadsheet_url
├── realtime/
│   ├── __init__.py
│   └── hub.py                 # RealtimeHub
├── api/
│   ├── __init__.py
│   ├── schemas.py             # pydantic request/response models (camelCase)
│   ├── teacher_routes.py      # /api/teacher/*
│   └── ws_routes.py           # /ws/teacher
└── static/
    ├── teacher.html
    └── teacher.js
tests/
├── conftest.py                # app + temp DB + FakeSheetsAdapter fixtures
├── fakes/
│   └── fake_sheets_adapter.py # FakeSheetsAdapter
├── fixtures/sheets/
│   ├── template_single.csv    # course template, 6 single questions (team-supplied)
│   ├── template_single.expected.json
│   ├── template_group.csv     # course template, 題組 + single questions (team-supplied)
│   ├── template_group.expected.json
│   ├── shifted_layout.json    # synthetic, differently shaped
│   ├── shifted_layout.expected.json
│   └── edge_cases/*.json      # small grids, one per edge case
├── unit/
│   ├── test_guided_notes_parser.py
│   ├── test_sheets_url.py
│   ├── test_fingerprint.py
│   └── test_activity_service.py
└── integration/
    ├── test_import_api.py
    ├── test_reimport_api.py
    ├── test_one_current_activity_concurrency.py
    └── test_ws_teacher.py
```

**Structure Decision**: This is a single project using the src layout the team specified. The
frontend is static files inside the package, so there are no separate frontend/backend
projects. `student.html`/`student.js` and the student socket are added by the student features.

## Implementation Notes for Tasks

- Order: write tests first for the parser, URL parsing, fingerprint and service rules (red), then
  implement. API and WebSocket integration tests come next, then the teacher page, then the
  manual verification records, then the diagram consistency check (Principle VIII).
- `create_app(adapter=None, db_path=None)` builds a `GoogleSheetsAdapter` from config unless one
  is injected. Tests always inject `FakeSheetsAdapter`.
- Schema creation runs at startup (`init_schema`, idempotent `CREATE … IF NOT EXISTS`). No
  migration tool is needed at this size.
- `.env.example` keys: `GOOGLE_APPLICATION_CREDENTIALS`, `QUIZBUZZER_DB_PATH`,
  `QUIZBUZZER_HOST`, `QUIZBUZZER_PORT`. Feature 002 adds its passcode key.

## Complexity Tracking

No constitution violations. Two choices beyond the bare stack, each justified:

| Choice | Why needed | Simpler alternative rejected because |
|---|---|---|
| Parser takes `merges` as well as `grid` | Merged-cell edge cases (spec) cannot be resolved from values alone | Copying values into merged cells creates false duplicate question numbers |
| Partial unique index in addition to the in-transaction check | Makes a second current activity impossible even if a code path forgets the check | Check-only relies on every future write path remembering it |
