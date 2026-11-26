# Quickstart: Results, Sheet Export and CSV (003) — Windows

Prerequisites, configuration and running are as in
[002 quickstart](../002-live-buzz-activity/quickstart.md) §1–§2.

## 1. Configuration (new in 003)

- No new `.env` keys. The same service-account key is used, but export asks Google for the
  **write** scope with its own client (research R1).
- Share the worksheet with the service account's email as **Editor** before exporting.
  Import still works with Viewer access.

## 2. Automated tests (no Google access needed)

```powershell
uv run pytest -q                                  # whole suite
uv run pytest -q tests/unit/test_sheet_exporter.py tests/unit/test_csv_export.py
uv run pytest -q tests/integration/test_export_api.py tests/integration/test_results_api.py
```

Expected: all green. The exporter tests cover ≥ 3 sheet shapes with inserted rows (Principle II).

## 3. Diagrams (Principle VIII)

```powershell
java -jar tools/plantuml.jar "./diagrams/*.puml"
```

Every `.puml` in `diagrams/` must have a fresh `.png`.

## 4. Manual validation scenarios

Use one teacher laptop and at least two student browsers, and a copy of a worksheet with one
single question, one 題組 with 2 sub-parts and one question nobody will answer. Record each run
in `docs/verification.md` under a 003 section (date, tester, commit, steps, observed result; no
secrets or student data).

| # | Steps | Expected |
|---|---|---|
| M31 | Run an activity: groups 2 then 1 answer the single question, group 2 answers the 題組, nobody answers the third. A student of group 3 who never submitted stays connected. Teacher clicks End | Within 1 s every student screen shows results: winners, rank order, 無人作答 for the third. Group 3's student sees them too. No names or times on student screens (US1, SC-001) |
| M32 | Refresh a student page | Results again (FR-004) |
| M33 | Teacher results view | Same results plus submitter names and times; Export and Download CSV buttons (US2 AS1) |
| M34 | Sheet shared as Viewer only → Export | Error names the service account email and asks for Editor access; sheet unchanged (US2 AS12) |
| M35 | Share as Editor; insert two rows above the questions; rename the tab; Export | "3 cells written, 1 unit had no answer". Single cell = answer; 題組 cells = `（1）…`, `（2）…` at their new rows; third question's cell untouched; formatting unchanged (US2 AS2–6) |
| M36 | Export again | Same values, same count (US2 AS10) |
| M37 | Delete the 題組's sub-part 2 row; Export | Refused, listing question 2 sub-part 2; sheet unchanged (US2 AS7) |
| M38 | Run an activity where an answer is `=1+1`; export | The cell shows `=1+1` as text (US2 AS9) |
| M39 | Download CSV; open by double-click in Excel, and import into Google Sheets | Chinese correct, commas/quotes/line breaks in one cell, `=1+1` shown as `'=1+1` text, header row as specified (US3, SC-006) |
| M40 | Create and close a second activity; open Past activities | Both listed newest first; opening the older one shows its results (US4) |
| M41 | From a student browser, request `/api/teacher/activities/<id>/results.csv` and `…/export` | 401 `teacher_required` (FR-020) |
| M42 | Server log after M31–M41 | No answer text or display names (FR-024) |
