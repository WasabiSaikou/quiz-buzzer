# Quiz Buzzer (課堂搶答系統)

A classroom buzz-in system that runs on the teacher's laptop over the classroom LAN.

- **Import (feature 001)**: the teacher pastes a link to a Google Sheets Guided Notes worksheet.
  The app reads its questions and answer cells, shows a preview, and creates a DRAFT activity with
  a chosen number of groups. Import only ever reads the sheet.
- **Live activity (feature 002)**: students join a group from their own devices. The teacher
  opens the activity, and every screen switches to answering at the same moment. The first group
  to submit a question wins it: the server ranks submissions by arrival order. The teacher
  watches a live dashboard, then ends the activity. Students never see other groups' answers or
  ranks while the activity is open.
- **Results and export (feature 003)**: once the activity is CLOSED, every student sees each
  question's winning group and answer and the full rank order (無人作答 for questions nobody
  answered). The teacher can write the winning answers back into the worksheet, download a CSV of
  all submissions, and reopen the results of past activities.

There are no user accounts. The teacher unlocks the controls with a passcode, and students only
enter a display name.

## Project documents

- Constitution (project principles and governance): [`.specify/memory/constitution.md`](.specify/memory/constitution.md)
- Feature specs, plans, research, data models, contracts, quickstarts and tasks:
  - [`specs/001-sheets-import/`](specs/001-sheets-import/)
  - [`specs/002-live-buzz-activity/`](specs/002-live-buzz-activity/)
  - [`specs/003-results-export/`](specs/003-results-export/)
- Design diagrams (PlantUML sources and rendered PNGs): [`diagrams/`](diagrams/)
- Code-vs-diagram verification: [`diagrams/VERIFICATION.md`](diagrams/VERIFICATION.md)
- Test-first records, manual checks and test runs: [`docs/verification.md`](docs/verification.md)

## Requirements

- Windows 10/11 (the commands below are PowerShell; the app itself is plain Python).
- [`uv`](https://docs.astral.sh/uv/) 0.13 or later on PATH. It installs Python 3.11 and every
  dependency from `uv.lock`.
- A Google Cloud service account with the Google Sheets API enabled (see Setup).
- For rendering diagrams only: Java 21 or later and `tools/plantuml.jar` (see [Diagrams](#diagrams)).
- Student devices (phones or laptops) on the same LAN as the teacher's laptop, with a modern
  browser.

## Setup (Windows, PowerShell)

### 1. Python environment

The app uses a project-local `quiz-buzzer\.venv`, which `uv sync` creates. **Do not use or
change the outer `SWE-Voting-System\.venv`**: it is an MSYS2 Python that uv cannot use
([001 research R1](specs/001-sheets-import/research.md#r1-python-environment-and-uv)).

```powershell
cd C:\path\to\SWE-Voting-System\quiz-buzzer
deactivate 2>$null          # only if the outer .venv is active in this shell
uv python find 3.11         # if this finds nothing, or only MSYS2/mingw Pythons:
uv python install 3.11      #   install a uv-managed CPython (once per machine)
uv sync                     # creates .\.venv with runtime and dev dependencies from uv.lock
```

`.python-version` (3.11) is committed, so `uv sync` picks the right Python on a fresh clone.

### 2. Google service account

1. In Google Cloud, create a service account, enable the **Google Sheets API** for its project,
   and download its JSON key.
2. Save the key under `quiz-buzzer\secrets\`. That folder is gitignored. Never commit the key or
   paste it anywhere.
3. Share each worksheet with the service account's email address (the key's `client_email`) as
   **Editor**. Editor access is needed to export the winning answers back into the sheet.
   Import alone works with Viewer access, and the app uses a read-only client for it. If the
   sheet is not shared, or is shared as Viewer when you export, the error message shows the
   address to share with.

### 3. Configuration

```powershell
Copy-Item .env.example .env
```

Then fill in `.env`. Real values go only in `.env`, which is never committed.

| Variable | Meaning |
|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | path to the service-account key, e.g. `secrets/<key-file>.json` |
| `TEACHER_PASSCODE` | **required**: the passcode that unlocks `/teacher`. The app refuses to start without it |
| `QUIZBUZZER_DB_PATH` | SQLite file (default `data/quizbuzzer.db`) |
| `QUIZBUZZER_HOST` / `QUIZBUZZER_PORT` | bind address and port (defaults `127.0.0.1` / `8000`). Use `0.0.0.0` in the classroom |

## Run

For the classroom, so that student devices can connect:

```powershell
uv run uvicorn quizbuzzer.main:app --host 0.0.0.0 --port 8000
```

- **Teacher**: open `http://127.0.0.1:8000/teacher` on the laptop and enter the passcode.
- **Students**: open `http://<laptop-LAN-IP>:8000/`, which redirects to `/student`.

If student devices cannot connect, allow Python through the Windows firewall on the **private**
network. To try it alone on the laptop, use `--host 127.0.0.1` instead.

### A lesson, step by step

1. **Import**: on `/teacher`, paste the worksheet link, pick the tab, check the preview and
   warnings, choose the number of groups (2–12) and confirm. This creates a DRAFT activity.
   While it is DRAFT you can re-import it to pick up sheet edits, or cancel it.
2. **Join**: students pick a group and type a display name. They can change group only while the
   activity is DRAFT.
3. **Open**: the teacher clicks Open. Every student screen switches to the questions (shown by
   number), and any member can submit a question for their group, once per group.
4. **End**: the teacher clicks End. Every student screen switches to the results: for each
   question, the winning group and its answer, then the full rank order. Student screens show no
   names or times.
5. **Export and CSV**: under the results, the teacher clicks **Export to sheet** (after a
   confirmation) to write the winning answers into the worksheet, and **Download CSV** for all
   submissions. Both can be repeated, and both also work for past activities (**Past
   activities** panel). A closed activity never blocks a new import.

## How the Guided Notes parser finds the questions

The parser (`src/quizbuzzer/services/guided_notes_parser.py`) works out every location from the
sheet's content. It has no fixed rows, columns or cell addresses (Constitution Principle II).

1. **Header row**: the topmost row that has one cell reading exactly `題號` and one reading exactly
   `作答`, after all whitespace is removed (half-width spaces, full-width spaces and line breaks).
   So `題 號` matches but `作答區` does not. The `題號` column is the question-number column, and
   the `作答` column is the answer column.
2. **Questions**: every row below the header whose number cell holds a positive integer starts a
   question: `1`, `1.`, `1、`, `Q1`, `q1`, with half- or full-width digits. Any other non-empty
   number cell (e.g. `備註`) produces a warning and does not start a question.
3. **Sub-parts**: a row whose answer cell starts with `（k）` or `(k)` (any mix of half- and
   full-width brackets and digits) is sub-part k of the current question. The numbered row is
   itself sub-part 1 if its answer cell holds `（1）`, or if it holds no marker and the next marker
   is `（2）`. A question with 2 or more sub-parts is a **題組**, with one answer slot per
   sub-part. Any other question is a single question, with one slot in the numbered row's answer
   cell.
4. **Details**: blank rows are skipped and do not end a question. Only the number and answer
   columns are read, so question text is never imported. If an answer cell is part of a merged
   range, its location is the range's top-left cell.
5. **Errors and warnings**: these name the rows or cells involved. Errors block confirmation:
   no header, duplicate question numbers, duplicate markers, a marker before the first question,
   or no questions at all. Warnings allow confirmation once acknowledged: gaps or out-of-order
   numbers, unrecognised number cells, or text already in an answer cell that export will
   overwrite.

## How export writes the answers back

Export (`src/quizbuzzer/services/sheet_exporter.py`) never trusts the cell addresses stored at
import, because the teacher may have inserted or deleted rows since then.

1. It is allowed only for a CLOSED activity. If nobody answered anything, nothing is sent to
   Google and the report says 0 cells.
2. It re-reads the source tab using its fixed **sheetId**, not its title, so a renamed tab still
   works. It then runs the same parser on it.
3. It finds each winning answer's slot again by **question number and sub-part number**. If the
   sheet now has parser errors, or a winning question or sub-part can no longer be found, it
   **writes nothing** and lists every problem. Questions nobody answered are never looked up, so
   deleting one of them does not block the export.
4. It overwrites each winning slot's whole cell. A single question's cell becomes the answer, and
   each 題組 slot becomes `（k）answer`.
5. It sends all cells in **one** `spreadsheets.values.batchUpdate` request with
   `valueInputOption: RAW`, so an answer such as `=1+1` is stored as text and never runs as a
   formula. Only cell values change, never formatting.
6. Writing goes through a separate client (`google_sheets_writer.py`) that has the write scope.
   The import client keeps the `spreadsheets.readonly` scope.

The CSV (`question_no, sub_part, group, answer, rank, is_winner, submitted_at`) is UTF-8 with a
BOM so that Excel shows Chinese correctly. Fields with commas, quotes or line breaks are quoted.
Answers starting with `=`, `+`, `-` or `@` get a leading `'`, so a spreadsheet program never runs
them as formulas.

## Tests

No Google access is needed: the tests use a fake Sheets adapter that also acts as the writer.

```powershell
uv run pytest                        # everything (001 + 002 + 003)
uv run pytest tests/unit -q          # parser, exporter re-location, CSV, visibility filter, service rules
uv run pytest tests/integration -q   # REST + WebSocket, teacher guard, export, leak and concurrency tests
```

Test-first records, manual checks and test-run results are in
[`docs/verification.md`](docs/verification.md). The manual scenarios are in each feature's
`quickstart.md`.

## Diagrams

`tools/plantuml.jar` is not committed (it is gitignored). Download the PlantUML jar from
<https://plantuml.com/download> and save it as `tools/plantuml.jar`. Then run:

```powershell
java -jar tools/plantuml.jar "./diagrams/*.puml"
```

This must exit with code 0 and leave a fresh `.png` next to every `.puml`. The code-vs-diagram
check is in [`diagrams/VERIFICATION.md`](diagrams/VERIFICATION.md).

## Third-party dependencies and licences

Licences were read from the installed packages' metadata (`importlib.metadata`: the
`License-Expression` field, or else `License`) on 2026-11-27. Exact versions of every package,
including transitive ones, are pinned in [`uv.lock`](uv.lock).

**Direct dependencies** (`pyproject.toml`):

| Package | Version | Use | Licence |
|---|---|---|---|
| fastapi | 0.165.0 | HTTP + WebSocket server | MIT |
| uvicorn | 0.54.0 | ASGI server | BSD-3-Clause |
| websockets | 17.4 | WebSocket protocol for uvicorn | BSD-3-Clause |
| python-dotenv | 1.2.4 | load `.env` | BSD-3-Clause |
| google-api-python-client | 2.202.0 | Google Sheets API | Apache-2.0 |
| google-auth | 2.63.1 | service-account credentials | Apache-2.0 |
| pytest (dev) | 9.2.0 | tests | MIT |
| httpx (dev) | 0.28.1 | TestClient transport | BSD-3-Clause |

**Imported directly by the code, but installed as dependencies of the packages above:**

| Package | Version | Pulled in by | Use | Licence |
|---|---|---|---|---|
| starlette | 1.10.0 | fastapi | middleware, WebSocket types | BSD-3-Clause |
| pydantic | 2.14.4 | fastapi | request/response models | MIT |
| anyio | 4.16.0 | starlette | thread → event-loop bridge for pushes | MIT |
| httplib2 | 0.32.1 | google-api-python-client | HTTP transport with timeout | MIT |
| google-auth-httplib2 | 0.4.4 | google-api-python-client | authorised HTTP transport | Apache-2.0 |

**Development tool** (not a Python package and not distributed with the app):

| Tool | Version | Use | Licence |
|---|---|---|---|
| PlantUML (`tools/plantuml.jar`) | 1.2026.10 | render `diagrams/*.puml` to PNG | GPL-3.0-or-later (from `java -jar tools/plantuml.jar -license`) |
