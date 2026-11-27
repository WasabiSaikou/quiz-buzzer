# Quiz Buzzer — Behaviour Summary (features 001–003)

Every user-visible behaviour and rule, one per line, for comparison with another implementation.
Citations: `001` = [sheets-import](../specs/001-sheets-import/spec.md), `002` =
[live-buzz-activity](../specs/002-live-buzz-activity/spec.md), `003` =
[results-export](../specs/003-results-export/spec.md). The edge-case lists in each spec give
the full error/warning classification.

## Teacher

**Access**
- The teacher unlocks every teacher control with a passcode from `.env`; a wrong passcode shows nothing. (002 FR-001)
- Every teacher action and view, including import, export, CSV and past results, refuses requests without the passcode ("teacher passcode required"). (002 FR-002, 003 FR-020)
- Once unlocked, a browser stays unlocked until the server restarts; several teacher tabs may be open. (002 FR-003)
- The passcode is never displayed or logged; without one configured, the app refuses to start. (002 FR-004)

**Import a worksheet**
- Paste a Google Sheets link; a link that is not a Sheets spreadsheet is rejected without contacting Google. (001 FR-001, FR-002)
- All tabs are listed; the `#gid=` tab is preselected if it exists, otherwise the first tab. (001 FR-003)
- A sheet not shared with the app shows the service-account email to share with. (001 FR-004)
- Import, preview and re-import never change the sheet. (001 FR-005, 003 FR-014)
- Header row = the topmost row with one cell exactly `題號` and one exactly `作答`, after removing all spaces, full-width spaces and line breaks (`作答區` does not match). (001 FR-006)
- No fixed row, column or cell address is assumed; everything is found from the content. (001 FR-007)
- A question starts at a number cell reading `n`, `n.`, `n、`, `Qn` or `qn` (half- or full-width digits). (001 FR-008)
- Any other non-empty number cell (`備註`, `0`, `1.5`, `一`) gives a warning and starts no question. (001 FR-008a)
- An answer cell starting with `（k）` or `(k)` (any half/full-width mix) is sub-part k of the current question. (001 FR-009)
- The numbered row is sub-part 1 if it holds `（1）`, or holds no marker and the next marker is `（2）`; if the next marker is `（1）`, the numbered row is not a slot. (001 FR-010)
- 2+ sub-parts = 題組 (one slot per sub-part); otherwise a single question with one slot. (001 FR-011)
- A slot cell already holding text beyond its marker is still a slot, with a warning that export will overwrite it. (001 FR-011a)
- Question text is never imported; questions are shown by number only. (001 FR-013)
- Blank rows are skipped and do not end a question; an unnumbered row with non-marker text gives a warning. (001 FR-014, FR-014a)
- Errors block confirmation; warnings allow it after acknowledgement. Errors: no header, header labels in different rows or repeated, duplicate question numbers, duplicate marker in one question, marker before the first question, zero questions. Warnings: number gaps or wrong order, sub-part marker gaps, unrecognised number cells, existing text in slot cells. (001 FR-015)
- Every error and warning names the rows or cells involved and what to change. (001 FR-016)
- The preview lists each question in sheet order with type, sub-part count and answer cell (tab + A1), plus totals. (001 FR-017, FR-018)
- The group count must be 2–12. (001 FR-019)
- Confirming creates a DRAFT activity from the confirmed detection; if the sheet changed since the preview, nothing is created and the new preview is shown. (001 FR-020, FR-022, FR-023)
- Re-import replaces a DRAFT activity's whole question set and keeps its phase and group count; it is refused for OPEN or CLOSED activities. (001 FR-024 – FR-026)

**Activity lifecycle**
- At most one activity is DRAFT or OPEN at a time; creating another is refused, naming the current one. CLOSED activities are kept. (001 FR-020a)
- Phases move forward one step only: DRAFT → OPEN → CLOSED; any other request is refused with the current phase. (002 FR-005, FR-006)
- Open, End and Cancel ask for confirmation stating they cannot be undone. (002 FR-007)
- Every phase change, and every creation or cancellation of the current activity, reaches every screen at once. (002 FR-008)
- A DRAFT activity can be cancelled: it is deleted with its questions, groups and memberships. OPEN can only be ended; CLOSED is never deleted. (002 FR-008a, FR-008b)

**Live dashboard**
- Lists every question in sheet order with its submissions in rank order: rank, group, submitter name, answers (（k） for 題組), receive time; rank 1 is marked winner; "No submissions yet" when empty. (002 FR-026)
- New submissions appear on every teacher tab within 1 s. (002 FR-027)
- Shows every group 1..N with its members and member count, updating as students join, leave or change group. (002 FR-028)
- After End, the final dashboard stays visible, including after a refresh. (002 FR-029)

**Results, export, CSV, past activities**
- Results exist only for CLOSED activities: per question the winner and full rank order, 無人作答 when nobody answered; the teacher also sees submitter names and times. (003 FR-001, FR-005)
- Export and CSV are refused for DRAFT or OPEN activities, stating the current phase. (003 FR-021)
- Export asks for confirmation that the answer cells of answered questions will be overwritten. (003 FR-006)
- Single question → cell = the answer; each 題組 slot → cell = `（k）answer` (full-width brackets, including an unmarked sub-part 1); unanswered questions' cells are untouched. (003 FR-007)
- Before writing, the tab is re-read by its fixed tab ID (a renamed tab still works), re-parsed, and each slot is found again by question number and sub-part; stored cell addresses are never written to. (003 FR-008)
- If the sheet now has errors, or a winning question or sub-part is missing, nothing is written and every problem is listed. Missing unanswered questions and warnings do not block. (003 FR-009)
- All cells go in one request as plain text, so `=1+1` stays text; formatting is never changed. (003 FR-010)
- The result reports cells written and questions skipped; no answers at all → "0 cells written". (003 FR-011)
- Export can be repeated any number of times, re-locating cells each time. (003 FR-012)
- Not shared → asks to share with the service-account email as Editor; view-only → asks for Editor access for that email; tab or sheet gone, or Google down → says so; never reports cells written on failure. (003 FR-013)
- CSV columns: `question_no, sub_part, group, answer, rank, is_winner, submitted_at`; one row per answer slot; sheet order → rank → sub-part. (003 FR-015)
- CSV values: `sub_part` empty for single questions; `is_winner` `true`/`false`; `submitted_at` = server receive time in ISO 8601 with offset. (003 FR-016)
- CSV is UTF-8 with BOM; fields with commas, quotes or line breaks are quoted (inner quotes doubled). (003 FR-017)
- CSV answers starting with `=`, `+`, `-` or `@` get a leading `'`. (003 FR-018)
- The CSV file name identifies the activity and is safe on Windows and macOS. (003 FR-019)
- A list of past CLOSED activities, newest first (title, created date, groups, questions, submissions); opening one shows its results, export and CSV. (003 FR-023)
- Nothing in results, export or CSV changes an activity or its submissions. (003 FR-022)

## Student

**Joining**
- Join by choosing a group 1..N and a display name of 1–20 characters after trimming; names need not be unique. (002 FR-009, FR-011)
- Joining is allowed while DRAFT or OPEN; refused when CLOSED or when there is no activity. (002 FR-010)
- The browser remembers the membership; a refresh returns to the same group without retyping. (002 FR-012)
- Changing group is allowed only while DRAFT. (002 FR-013)
- The group always comes from the student's own membership, never from the request; a membership never carries over to another activity. (002 FR-014)
- With no activity, the page says "No activity available yet" and switches to the join form by itself when one is created. (002 FR-031)

**Buzzing in**
- While OPEN, the student sees every question by number in sheet order: one field for a single question, one field per （k） for a 題組. (002 FR-015)
- A question is submitted whole: every field non-empty after trimming (incl. full-width spaces and line breaks) and at most 200 characters; failures name each sub-part and save nothing. (002 FR-016)
- Submitting is allowed only while OPEN ("has not opened yet" / "has ended" otherwise). (002 FR-017)
- One submission per group per question; a second attempt by any member is refused. (002 FR-018)
- Rank = arrival order at the server (1 = winner), assigned atomically: ranks 1, 2, 3… with no gaps or ties, never from client time. (002 FR-019, FR-020)
- Teammates see a submission at once (answers + submitter name) and that question becomes read-only. (002 FR-021)
- A student sees their own group number and members only. (002 FR-022)
- A refresh or reconnect restores the current phase and the group's state automatically; "reconnecting" is shown while offline. (002 FR-030)

**Visibility before and after close**
- Before CLOSED, nothing about other groups' submissions reaches a student: no content, count, timing, order, rank or winner, not even their own rank. (002 FR-023)
- Enforced by one server-side filter on every response and push. (002 FR-024, 003 FR-002)
- After CLOSED, every member sees the results: per question the winning group and answer, and every group's answer and rank; 無人作答 for unanswered questions; no names or times. (003 FR-001, FR-003)
- The closed screen also keeps showing the student's own group's submissions. (002 FR-025)
- A member whose group never submitted sees the same results; a browser that never joined sees none. (003 FR-003)
- Results appear on every student screen within 1 s of End and again after a refresh. (003 FR-004)

## System-wide

- Display names and answer text are never written to logs. (002 FR-032, 003 FR-024)
