# Research: Import Guided Notes Worksheet (001)

**Date**: 2026-11-26 | **Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)

The stack was fixed by the team (see plan input). This document records the decisions needed to
apply it to this feature, and the one environment conflict found while checking the machine.

## R1. Python environment and uv (⚠ needs team action)

- **Finding**: The agreed environment is the outer folder's `.venv`
  (`SWE-Voting-System/.venv`). On inspection (2026-11-26) it is an **MSYS2/mingw** CPython
  3.11.7 venv created `--without-pip` (platform `mingw_x86_64`, `bin/` layout). `uv 0.13.10`
  refuses it: "Unknown operating system: `mingw_x86_64`". Mingw Python also lacks prebuilt
  wheels for `pydantic-core` (required by FastAPI), so installs would try to compile Rust.
- **Decision**: Keep the venv in the outer folder, but recreate it as a uv-managed official
  CPython 3.11 venv: `uv venv ..\.venv --python 3.11`, and point uv at it with
  `UV_PROJECT_ENVIRONMENT=..\.venv` (set in the shell or user environment, not in `.env`).
  No venv is created inside `quiz-buzzer/`.
- **Rationale**: Satisfies both team decisions (outer venv; uv-managed project) with a Python uv
  and all wheels support.
- **Alternatives considered**: keep mingw venv and use pip (breaks the uv decision; pydantic-core
  build risk); default uv `.venv` inside `quiz-buzzer/` (team declined).
- **Action**: Deleting/recreating `..\.venv` is a team decision; not done by this plan.

## R2. Parser input: grid plus merges

- **Decision**: `guided_notes_parser.parse(grid, merges)` — `grid` is `list[list[str]]` of
  displayed values (ragged rows allowed), `merges` is a list of 0-based half-open ranges
  `(start_row, end_row, start_col, end_col)` as returned by the Sheets API. Still a pure function.
- **Rationale**: The Sheets API returns a merged range's value only in its top-left cell. To meet
  the merged-cell edge cases the parser must know merges: an answer cell inside a merge resolves
  to the merge's top-left (its stored location), a vertically merged 題號 cell counts once (only
  its top-left row starts a question, so it is not reported as a duplicate), and rows covered by
  a vertical answer merge below its top-left are skipped.
- **Alternatives considered**: grid only, by copying the top-left value into every merged cell
  (would create false duplicate question numbers); resolving merges in the adapter (puts
  structural logic outside the parser and outside its tests).

## R3. Text normalisation rules

- **Decision**: Every cell is normalised with Unicode NFKC before matching. NFKC maps full-width
  digits, letters, parentheses and the ideographic space to their half-width forms.
  - Header: remove all whitespace (`\s`, which covers U+3000 and line breaks), then compare
    exactly with `題號` / `作答` (FR-006).
  - Question number: strip, then match `^[Qq]?([0-9]+)[.、]?$` with value > 0 (FR-008). Any other
    non-empty cell gives an `unrecognised_question_number` warning (FR-008a).
  - Sub-part marker: strip, then match `^\(\s*([0-9]+)\s*\)` at the start of the cell (FR-009).
    The remaining text after the marker, if non-empty after stripping, triggers
    `slot_cell_has_text` (FR-011a).
- **Side effect, accepted**: NFKC also accepts a full-width `Ｑ` and full-width `．`, which
  the spec does not list. They are unambiguous and harmless. This is recorded here so tests
  cover it.
- **Alternatives considered**: hand-written translation tables (more code, same result).

## R4. Sub-part assignment (FR-009 – FR-011)

For each numbered row N, collect marker rows after it until the next numbered row (blank rows
skipped; unnumbered non-marker text → `stray_answer_text` warning, FR-014a):

1. N's own answer cell starts with marker k → N is slot k.
2. Otherwise, if the first following marker is （1） → N is not a slot.
3. Otherwise, if the first following marker is k ≥ 2 → N is implicit slot 1.
4. Otherwise (no markers follow) → N is the single slot.

Then: 2+ slots → `GROUP_SET` (題組), else `SINGLE`. Duplicate k → `duplicate_sub_part` error;
missing k in 1..max → `sub_part_gap` warning. Marker rows above the first numbered row →
`orphan_sub_part` error.

## R5. Reading the sheet (GoogleSheetsAdapter)

- **Decision**:
  - `list_tabs`: `spreadsheets.get(fields="properties.title,sheets.properties(sheetId,title,index)")`.
  - `read_tab`: `spreadsheets.get(fields="sheets(properties.sheetId,merges)")` for merges, plus
    `values.get(range="'<title>'", valueRenderOption="FORMATTED_VALUE")`; single quotes in
    tab titles are doubled.
  - Credentials: `google.oauth2.service_account.Credentials.from_service_account_file(path,
    scopes=[spreadsheets.readonly])` for import. Export (003) will use the `spreadsheets` scope
    and `values.batchUpdate` with `valueInputOption=RAW`.
  - The service account email is read from the key file's `client_email` at startup.
  - HTTP timeout is 10 s. `HttpError` 403 maps to `SheetNotShared`, 404 to `SheetNotFound`, and
    other errors or timeouts to `SheetsUnavailable` (502).
- **Rationale**: FORMATTED_VALUE matches what the teacher sees (spec assumption). Reading by
  `sheetId` rather than title survives tab renames between preview and confirm. The read-only
  scope enforces FR-005 at the credential level.
- **URL parsing** (`sheets_url.parse_spreadsheet_url`): accept `https://docs.google.com/
  spreadsheets/d/<id>/…` with an optional `#gid=<n>` (or `?gid=` / `&gid=`). Anything else
  raises `InvalidSheetUrl` with no network call (FR-002).

## R6. Preview fingerprint (FR-022)

- **Decision**: SHA-256 of canonical JSON (sorted keys, no whitespace) of
  `{spreadsheetId, sheetId, units:[{number, kind, sourceRow, slots:[{subPart, row, column}]}]}`.
  Warnings and errors are excluded, because only the structure matters. The client sends back the
  fingerprint it was shown, and confirm re-reads and re-parses the sheet and compares.
- **Rationale**: Stateless (no server-held preview), and the client cannot inject cell locations
  because the server always uses its own re-parse.
- **Alternatives considered**: server-side preview cache with expiry (more state, same
  guarantee).

## R7. SQLite usage

- **Decision**:
  - Standard `sqlite3` module, opening one connection per request with `isolation_level=None`
    and explicit `BEGIN IMMEDIATE … COMMIT` for every write.
  - `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`.
  - DB path comes from `QUIZBUZZER_DB_PATH` (default `data/quizbuzzer.db`, covered by `*.db` in
    `.gitignore`).
  - **One current activity**: checked inside the `BEGIN IMMEDIATE` transaction and backed by a
    partial unique index,
    `CREATE UNIQUE INDEX one_current_activity ON activities((phase IN ('DRAFT','OPEN'))) WHERE
    phase IN ('DRAFT','OPEN')`. Verified on SQLite 3.44: a second DRAFT/OPEN insert is rejected.
  - **Submission ranking** (recorded for the submissions feature, not built here): `BEGIN
    IMMEDIATE`, `UNIQUE(group_id, unit_id)`, and a server-assigned `arrival_seq`.
- **Rationale**: BEGIN IMMEDIATE takes the write lock up front, so check-then-insert cannot race.
  The index is a second line of defence (Principle I style: impossible, not unlikely).
- **Alternatives considered**: application-level lock only (lost on bugs); an ORM (unneeded
  dependency, Principle VII).

## R8. Sync endpoints and WebSocket push

- **Decision**:
  - Teacher REST endpoints are plain `def`, so FastAPI runs them in a worker thread. This suits
    the synchronous Google client and `sqlite3`.
  - `RealtimeHub` keeps the set of teacher WebSockets and an `async broadcast(message)`.
  - Sync service code publishes through `anyio.from_thread.run(hub.broadcast, msg)`. That works
    because FastAPI's worker threads are anyio threads.
  - On connect, a socket receives the current `activity.state` (Principle IV: a client that
    reconnects recovers state).
- **Alternatives considered**: async Google client (none official); polling (violates Principle
  IV's push requirement).
- **Scope**: this feature adds `/ws/teacher` only. Student sockets and visibility filtering
  (Principle III) arrive with the student features.

## R9. Testing approach

- **Decision**:
  - `pytest` with FastAPI `TestClient` (needs `httpx`).
  - `FakeSheetsAdapter` (in `tests/fakes/`) loads `tests/fixtures/sheets/*.json`, one file per
    spreadsheet: `{spreadsheetId, title, tabs:[{sheetId, title, index, grid, merges}]}`. It can
    also be set to raise `SheetNotShared`, `SheetNotFound` or `SheetsUnavailable`.
  - The app is built by `create_app(adapter=..., db_path=...)` so tests inject the fake and a
    temporary database.
- **Fixtures (Principle II, at least 3 shapes)**: `course_template_a.json` and
  `course_template_b.json` are copies of the two course templates, and
  `shifted_layout.json` is synthetic, with the header lower and further right, merged
  question-text cells, full-width markers and spacer rows. Small synthetic grids cover each edge
  case.
- **⚠ Input needed**: the two course templates must be supplied by the team. Any student or
  personal data must be removed before they are committed (Principle VI).
- **Concurrency test**: two threads confirm at once against a file-based temp DB, and exactly one
  activity must be created.

## R10. Dependencies and licences (README, Principle VII)

| Package | Use | Licence |
|---------|-----|---------|
| fastapi | HTTP + WebSocket server | MIT |
| uvicorn | ASGI server | BSD-3-Clause |
| websockets | WebSocket protocol for uvicorn | BSD-3-Clause |
| python-dotenv | load `.env` | BSD-3-Clause |
| google-api-python-client | Sheets API | Apache-2.0 |
| google-auth | service-account credentials | Apache-2.0 |
| pytest (dev) | tests | MIT |
| httpx (dev) | TestClient transport | BSD-3-Clause |
| PlantUML (tool, `tools/plantuml.jar`, not distributed) | diagram rendering | GPL-3.0 (default jar) |

Transitive packages (starlette, pydantic, anyio, …) are pinned in `uv.lock`; the README lists
direct dependencies and points to `uv.lock` for the rest. `uvicorn[standard]` is avoided to keep
the list short; only `websockets` is added.
