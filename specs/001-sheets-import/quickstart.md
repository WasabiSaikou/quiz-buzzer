# Quickstart: Import Guided Notes Worksheet (001) — Windows

Run and validation guide. Endpoint and payload details live in [contracts/](contracts/), and
tables in [data-model.md](data-model.md).

## Prerequisites

- Windows 10/11, PowerShell.
- `uv` (0.13 or later) on PATH.
- Java 21 or later, used only for diagrams (`tools/plantuml.jar`).
- A Google Cloud service account with the Sheets API enabled, and its JSON key saved under
  `quiz-buzzer\secrets\` (gitignored). The key is never committed or pasted anywhere
  (Principle VI).

## 1. Environment (project-local `.venv`, uv-managed)

The venv is `quiz-buzzer\.venv`, which `uv sync` creates. **Do not touch** the outer
`SWE-Voting-System\.venv`. It is an MSYS2 Python that uv cannot use; see
[research.md R1](research.md#r1-python-environment-and-uv).

```powershell
cd C:\path\to\SWE-Voting-System\quiz-buzzer
deactivate 2>$null                 # if the outer .venv is active in this shell
uv python find 3.11                # which 3.11 would uv use?
# Only if it finds nothing, or only MSYS2/mingw interpreters (C:\msys64\..., ..\.venv\bin\...):
uv python install 3.11             # uv-managed official CPython
uv python pin 3.11                 # writes .python-version (committed)
uv sync                            # creates .\.venv; installs runtime + dev deps from uv.lock
```

`.python-version` is committed, so on a fresh clone `uv sync` alone picks the pinned 3.11. It
still needs `uv python install 3.11` once on a machine that only has MSYS2 Python.

## 2. Configuration

```powershell
Copy-Item .env.example .env
```

Edit `.env`. The variable names are in `.env.example`, and real values go only in `.env`:

| Variable | Meaning |
|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | path to the service-account JSON key, e.g. `secrets/<key-file>.json` |
| `QUIZBUZZER_DB_PATH` | SQLite file, default `data/quizbuzzer.db` |
| `QUIZBUZZER_HOST` / `QUIZBUZZER_PORT` | bind address (LAN IP or `0.0.0.0` for the classroom; default `127.0.0.1`) / port (default `8000`) |

## 3. Run

```powershell
uv run uvicorn quizbuzzer.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/teacher`.

## 4. Automated tests (no Google access needed)

```powershell
uv run pytest                          # everything
uv run pytest tests/unit -q            # parser, URL parsing, fingerprint, service rules
uv run pytest tests/integration -q     # REST + WebSocket through TestClient with FakeSheetsAdapter
```

Expected: all pass. The parser suite runs against at least three fixture sheets in
`tests/fixtures/sheets/` (Principle II).

## 5. Diagrams (Principle VIII)

```powershell
java -jar tools/plantuml.jar "./diagrams/*.puml"
```

Expected: exit code 0, with a fresh `.png` next to every `.puml`.

## 6. Manual validation scenarios

Record each run in `docs/verification.md` with the date, tester, steps and
observed result (Principle V).

| # | Steps | Expected |
|---|---|---|
| M1 | Paste a link to a sheet **not** shared with the service account | Error shows the service account email and says to share as Viewer |
| M2 | Paste `https://example.com/x` | "Not a Google Sheets link"; no Google request in server log |
| M3 | Share a course template, paste its link | First tab preselected; preview lists every question with type, sub-part count, answer cell |
| M4 | Paste the same link with `#gid=` of the second tab | Second tab preselected |
| M5 | Add `備註` in the 題號 column, re-preview | Warning naming the row and `備註` |
| M6 | Confirm with 6 groups (acknowledging warnings) | DRAFT activity shown with 6 groups and the same slots; a second open `/teacher` tab updates without reload |
| M7 | Try to create another activity | Refused: names the current DRAFT activity, suggests re-import |
| M8 | Edit the sheet (add a question), re-import, confirm | Activity now has the new question set; phase and group count unchanged |
| M9 | Preview, then edit the sheet structure, then confirm | Refused with updated preview |
| M10 | Open the sheet's version history after M3–M9 | No edits by the service account (FR-005, SC-005) |
