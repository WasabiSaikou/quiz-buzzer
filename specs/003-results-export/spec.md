# Feature Specification: Results, Sheet Export and CSV Download

**Feature Branch**: `003-results-export` (spec directory; no git branch created)

**Created**: 2026-11-27

**Status**: Draft

**Input**: User description: "Feature 003: show results after the activity ends, export winning
answers back into the Google Sheet, and export a CSV. Builds on 001 (import, slots, parser) and
002 (phases, submissions with per-unit rank and server receive time, teacher passcode, student
membership cookie)."

## Design Diagrams *(Constitution Principle VIII)*

These diagrams are the blueprint for `/speckit-plan`. Sources and rendered PNGs live side by side
in `diagrams/`. Routes, message names and module names in the diagrams are a proposed design for
the plan to confirm; the requirements below do not depend on them.

| Diagram | Source | Image |
|---------|--------|-------|
| System components (whole system, updated for 003) | [system-component.puml](../../diagrams/system-component.puml) | [PNG](../../diagrams/system-component.png) |
| Domain classes (whole system, updated for 003) | [domain-class.puml](../../diagrams/domain-class.puml) | [PNG](../../diagrams/domain-class.png) |
| Sequence: view results (student and teacher) | [003-seq-view-results.puml](../../diagrams/003-seq-view-results.puml) | [PNG](../../diagrams/003-seq-view-results.png) |
| Sequence: export winning answers to the sheet | [003-seq-export-sheet.puml](../../diagrams/003-seq-export-sheet.puml) | [PNG](../../diagrams/003-seq-export-sheet.png) |
| Sequence: download CSV | [003-seq-download-csv.puml](../../diagrams/003-seq-download-csv.puml) | [PNG](../../diagrams/003-seq-download-csv.png) |
| Sequence: past CLOSED activities | [003-seq-past-activities.puml](../../diagrams/003-seq-past-activities.puml) | [PNG](../../diagrams/003-seq-past-activities.png) |

The feature 001 and 002 sequence diagrams are unchanged.

## Roles

- **Teacher**: unlocks the teacher controls with the teacher passcode (feature 002). Sees the
  results of the current CLOSED activity and of past CLOSED activities, exports winning answers
  into the activity's source sheet, and downloads the CSV of all submissions.
- **Student**: a member of a group of the activity (feature 002 membership, kept by the
  student's browser). Once the activity is CLOSED, sees its results. Cannot export or download.
- **Google service account** (system actor): the app's identity for Google Sheets. Import still
  only reads (001 FR-005). For export the teacher must give it Editor access to the sheet.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Students see the results once the activity ends (Priority: P1)

When the teacher ends the activity, every student screen switches from answering to the results
screen without a reload. For every question unit, in sheet order, the student sees the winning
group and its answer (each sub-part labelled （k） for a 題組), followed by the full submission
order: every group that answered, its answer and its rank. A unit nobody answered shows 無人作答.
This is the first time students see other groups' answers or any rank, including their own.

**Why this priority**: The race only means something once everyone can see who won. Students
have been waiting for exactly this screen since 002.

**Independent Test**: Run an activity in which groups 2 and 5 answer unit 1 (in that order) and
nobody answers unit 2, then end it. A student of group 1 who never submitted must see unit 1 won
by group 2 with its answer, the order group 2 (rank 1), group 5 (rank 2), and unit 2 as 無人作答.

**Acceptance Scenarios**:

1. **Given** an OPEN activity with students on the answering screen, **When** the teacher ends
   it, **Then** every student screen shows the results within a second, without a reload.
2. **Given** a CLOSED activity in which groups 4, 1 and 6 answered unit 2 in that order, **When**
   any member views the results, **Then** unit 2 shows group 4 as the winner with its answer,
   then the order rank 1 group 4, rank 2 group 1, rank 3 group 6, each with its answer.
3. **Given** a CLOSED activity and a 題組 unit with 3 sub-parts, **When** a student views its
   results, **Then** each listed answer shows all 3 sub-parts, labelled （1）, （2）, （3）.
4. **Given** a unit with no submissions, **When** a student views the results, **Then** the unit
   shows 無人作答 and no winner.
5. **Given** a student who joined but whose group never submitted anything, **When** they view
   the results, **Then** they see the full results like every other member.
6. **Given** an OPEN or DRAFT activity, **When** a student asks for results by any means
   (including a crafted request), **Then** nothing about other groups' submissions or any rank is
   returned (002 FR-023 still applies).
7. **Given** a CLOSED activity, **When** a student refreshes or reconnects, **Then** they are
   back on the results screen.

---

### User Story 2 - Teacher sees the results and exports winning answers into the sheet (Priority: P1)

After ending the activity, the teacher sees the same results as the students, plus the submitter
name and receive time of each submission. The teacher chooses "Export to sheet" and confirms. The
app re-reads the source tab, finds each winning answer slot again by its question number and
sub-part number, and writes all winning answers into their answer cells in one go. A single
question's cell becomes the answer. Every 題組 slot's cell becomes `（k）answer`. Cells of units
nobody answered are left as they are. The teacher is told how many cells were written.

**Why this priority**: Writing the winning answers back into the worksheet is how the class's
Guided Notes get filled in. It is the teacher's main reason to run the activity.

**Independent Test**: Run an activity on a sample sheet (one single question, one 題組 with 2
sub-parts, one unanswered question), end it, insert two rows above the questions in the sheet,
then export. The single question's cell must hold the answer, the 題組 cells must hold
`（1）answer` and `（2）answer` at their new rows, the unanswered question's cell must be
unchanged, and the app must report 3 cells written.

**Acceptance Scenarios**:

1. **Given** a CLOSED activity, **When** the teacher opens it, **Then** the results show every
   unit in sheet order with the winner, the full submission order, each submitter's display name
   and receive time, and 無人作答 for units with no submissions.
2. **Given** a CLOSED activity where single question 1 was won with answer `光合作用`, **When**
   the teacher exports, **Then** question 1's answer cell contains exactly `光合作用`, whatever
   it held before.
3. **Given** 題組 question 3 with 2 sub-parts won with answers `A` and `B`, **When** the teacher
   exports, **Then** sub-part 1's cell contains exactly `（1）A` and sub-part 2's cell contains
   exactly `（2）B`. This also holds when sub-part 1 is the numbered row that had no marker.
4. **Given** a unit with no submissions, **When** the teacher exports, **Then** its cells are not
   changed.
5. **Given** the teacher inserted rows above the questions after import, **When** the teacher
   exports, **Then** every answer is written into the cell where its question and sub-part now
   are, not where they were at import.
6. **Given** the source tab was renamed after import, **When** the teacher exports, **Then** the
   export still finds the tab and succeeds.
7. **Given** a question or sub-part of a winning unit has been deleted from the sheet, **When**
   the teacher exports, **Then** nothing is written and the message lists every missing question
   and sub-part.
8. **Given** the source tab now has detection errors (001 classification), **When** the teacher
   exports, **Then** nothing is written and the message lists the errors.
9. **Given** a winning answer that starts with `=` (e.g. `=1+1`), **When** the teacher exports,
   **Then** the cell shows the text `=1+1`, not a formula result.
10. **Given** a successful export, **When** the teacher exports again, **Then** the same cells
    receive the same values and the same count is reported.
11. **Given** a CLOSED activity with zero submissions, **When** the teacher exports, **Then**
    nothing is written and the app says 0 cells were written.
12. **Given** the service account has only view access to the sheet, **When** the teacher
    exports, **Then** nothing is written and the message names the service account email and asks
    the teacher to give it Editor access.
13. **Given** the teacher clicks "Export to sheet", **When** the confirmation appears, **Then**
    it states that the answer cells of answered units will be overwritten, and backing out
    changes nothing.

---

### User Story 3 - Teacher downloads a CSV of all submissions (Priority: P2)

The teacher downloads a CSV file of every submission of a CLOSED activity, one row per answer
slot, with the question number, sub-part, group, answer, rank, whether it was the winner, and the
server's receive time. It opens correctly in Excel and Google Sheets, including Chinese text and
answers containing commas, quotes or line breaks, and answers can never run as formulas.

**Why this priority**: Useful for records and for grading later, but the class can run and the
worksheet can be filled without it.

**Independent Test**: Run an activity in which answers include `a,b`, `say "hi"`, a two-line
answer, `=SUM(A1)` and `中文`, end it, download the CSV and open it in Excel. Every answer must
appear in one cell, as typed (formula-like ones with a leading `'`), with Chinese shown correctly.

**Acceptance Scenarios**:

1. **Given** a CLOSED activity, **When** the teacher downloads the CSV, **Then** the first row is
   `question_no,sub_part,group,answer,rank,is_winner,submitted_at` and there is one row per
   answer slot of every submission.
2. **Given** a 題組 submission with 3 sub-parts, **When** the CSV is produced, **Then** it has 3
   rows for that submission with sub_part 1, 2, 3 and the same group, rank, is_winner and
   submitted_at.
3. **Given** answers containing a comma, a double quote or a line break, **When** the CSV is
   opened in a spreadsheet program, **Then** each answer appears whole in one cell.
4. **Given** answers starting with `=`, `+`, `-` or `@`, **When** the CSV is produced, **Then**
   each is written with a leading `'`, so it is shown as text and never executed.
5. **Given** Chinese answers, **When** the CSV is opened in Excel by double-clicking, **Then**
   the Chinese text is shown correctly.
6. **Given** a CLOSED activity with zero submissions, **When** the teacher downloads the CSV,
   **Then** it contains only the header row.

---

### User Story 4 - Teacher opens results of past CLOSED activities (Priority: P3)

The teacher sees a simple list of past CLOSED activities, newest first. Opening one shows its
results, from which the teacher can also download its CSV or export it to its sheet.

**Why this priority**: Recorded decision from 001: CLOSED activities are kept so their results
stay viewable. It matters only once a new activity has replaced the last one on the teacher's
screen.

**Independent Test**: Close activity A, create and close activity B, then open the past list. It
must list B then A. Opening A must show A's results, not B's.

**Acceptance Scenarios**:

1. **Given** two CLOSED activities and one DRAFT activity, **When** the teacher opens the past
   activities list, **Then** only the two CLOSED activities are listed, newest first, each with
   its title, creation date, group count, unit count and submission count.
2. **Given** the list, **When** the teacher opens an activity, **Then** its results are shown
   (as in User Story 2), with its CSV download and sheet export.
3. **Given** no CLOSED activities, **When** the teacher opens the list, **Then** it says there
   are no past activities.

---

### Edge Cases

- **Export or CSV before CLOSED** (DRAFT or OPEN, including from a stale tab or crafted request):
  refused with a message stating the activity's current phase; nothing is written or downloaded.
- **Results requested before CLOSED**: the teacher keeps the 002 live dashboard; students get
  nothing about other groups or ranks (002 FR-023).
- **Rows inserted or deleted above or between questions after import**: export follows the
  questions to their new cells (found by question number and sub-part number), never the cell
  addresses stored at import.
- **A question, or a sub-part of a 題組, deleted from the sheet after import**: if that unit has
  a winner, the export is aborted, nothing is written, and the message lists every missing
  question number and sub-part. Missing questions whose units nobody answered do not block the
  export, because nothing would be written to them.
- **Sub-parts added to a 題組 after import, or new questions added**: ignored. Only slots that
  existed at import and have a winning answer are written.
- **A question changed from single to 題組 (or back) in the sheet after import**: the export uses
  the unit's kind from import time to format the text, and looks for its stored sub-part numbers
  in the sheet as it is now. A single question is located by its question number (sub-part 1).
- **Duplicate question numbers or other 001 errors in the sheet now**: export aborted, errors
  listed, nothing written. 001 warnings (such as existing text in an answer cell) do not block
  export.
- **Tab renamed**: export finds the tab by its fixed ID and succeeds.
- **Tab deleted, or the spreadsheet deleted**: export aborted with "the source tab (or
  spreadsheet) could not be found".
- **Sheet no longer shared with the app**: export aborted; the message names the service account
  email and asks the teacher to share the sheet with it as an Editor.
- **Sheet shared view-only**: the re-read succeeds but the write is refused; the message names
  the service account email and asks for Editor access. Nothing is written.
- **Google Sheets unavailable** (network, timeout, unexpected Google error): export reports that
  Google Sheets is unavailable. The app never reports cells as written unless Google accepted the
  write.
- **The sheet changes between the re-read and the write** (the teacher edits it at that moment):
  not guarded against; the write goes to the cells found by the re-read a moment earlier.
- **Zero submissions**: export writes nothing and says "0 cells written"; the CSV has only the
  header row; results show 無人作答 for every unit.
- **Answers with commas, quotes, line breaks, leading `=`, `+`, `-` or `@`**: written to the
  sheet exactly as stored, as text (never as formulas). In the CSV they are quoted as needed,
  and those starting with `=`, `+`, `-` or `@` get a leading `'`.
- **Repeated export**: allowed any number of times. Each export overwrites the same cells with
  the same values and reports the count. If the teacher edited an exported cell in between, it
  is overwritten again.
- **Two export requests at the same time** (two teacher tabs): both may run. They write the same
  values to the same cells, so the result is the same as one export.
- **Export of a past activity whose sheet has since been used by a newer activity**: allowed;
  the teacher confirms the overwrite as usual.
- **A student who joined but never submitted**: sees the full results.
- **A browser with no membership of the CLOSED activity** (never joined): sees that the activity
  has ended, without results (joining a CLOSED activity is refused by 002 FR-010).
- **A student's membership belongs to an older CLOSED activity after the teacher created a new
  one**: the student sees the join form for the new activity (002); the old results are no
  longer shown to them.
- **A student calls an export, CSV or past-activity action directly**: refused with "teacher
  passcode required" and no data (002 FR-002).
- **Activity does not exist** (stale page or wrong ID): "activity could not be found".

## Requirements *(mandatory)*

### Functional Requirements

**Results** (Constitution Principle III)

- **FR-001**: The results of an activity MUST be available only while it is CLOSED. For each
  question unit, in sheet order, they MUST show the winning group and its answer, and every
  submission in rank order with its group, its answer (each slot labelled （k） for a 題組) and
  its rank. A unit with no submissions MUST show 無人作答.
- **FR-002**: Students MUST receive results only through the existing server-side visibility
  filter (002 FR-024). The filter MUST include other groups' submissions and any rank only when
  the activity is CLOSED. In every other phase it MUST behave exactly as in 002.
- **FR-003**: A student MUST see the results of the activity they are a member of, whether or
  not their group submitted anything. The student results MUST NOT include submitters' display
  names or receive times. A browser with no membership of that activity MUST NOT receive results.
- **FR-004**: When the activity becomes CLOSED, every connected student client MUST switch to
  the results within one second, without a reload. A student who refreshes or reconnects while
  the activity is CLOSED MUST return to the results (002 FR-030).
- **FR-005**: The teacher's results view MUST show the same results plus, for each submission,
  the submitter's display name and the server's receive time. It is available for any CLOSED
  activity.

**Export to the sheet** (Constitution Principle II)

- **FR-006**: The teacher MUST be able to export the winning answers of a CLOSED activity into
  the activity's source spreadsheet and tab, after a confirmation that states the answer cells of
  answered units will be overwritten.
- **FR-007**: For every unit with a winner, export MUST overwrite each of the unit's slot cells
  entirely. A single question's cell MUST become the winning answer text. Each slot of a 題組
  MUST become `（k）` followed by that slot's winning answer, where k is the slot's sub-part
  number and the parentheses are full-width. This includes a numbered row that became sub-part 1
  without its own marker. Units without a winner MUST NOT be written to.
- **FR-008**: Before writing, the export MUST re-read the source tab, identifying it by its fixed
  tab ID (never by its title), and run the same detection as import (001) on it. Each slot to
  write MUST be located by its question number and sub-part number in that new detection result.
  Cell addresses stored at import MUST NOT be used as write targets.
- **FR-009**: The export MUST write nothing if the re-read finds any detection error, or if any
  question number or sub-part of a unit with a winner cannot be found. The message MUST list every
  detection error, or every missing question number and sub-part. Detection warnings MUST NOT
  block the export.
- **FR-010**: All cells of one export MUST be sent to Google in a single write request, written
  as plain text exactly as stored, so that text starting with `=`, `+`, `-` or `@` is never
  interpreted as a formula. Formatting of the cells MUST NOT be changed.
- **FR-011**: After a successful export, the teacher MUST be told how many cells were written and
  how many units were skipped because nobody answered. With zero winning units, the export MUST
  send no write and report 0 cells written.
- **FR-012**: Export MUST be repeatable any number of times. Each export MUST locate the cells
  afresh (FR-008) and report its own count.
- **FR-013**: If the sheet cannot be read because it is not shared with the app, the message MUST
  name the service account email and ask the teacher to share the sheet with it as an Editor. If
  the write is refused because the service account has only view access, the message MUST name
  the service account email and ask for Editor access. If the spreadsheet or tab no longer
  exists, or Google Sheets is unavailable, the export MUST say so. In every failure case the
  teacher MUST NOT be told that any cell was written.
- **FR-014**: Import, preview and re-import MUST remain read-only (001 FR-005). Only the export
  action may write to a spreadsheet.

**CSV download**

- **FR-015**: The teacher MUST be able to download a CSV of all submissions of a CLOSED activity.
  It MUST have the header row `question_no,sub_part,group,answer,rank,is_winner,submitted_at` and
  one row per answer slot of every submission, ordered by unit in sheet order, then rank, then
  sub-part.
- **FR-016**: Column contents: `question_no` is the unit's question number; `sub_part` is the
  slot's sub-part number for a 題組 and empty for a single question; `group` is the group number;
  `answer` is the stored answer text; `rank` is the submission's rank in its unit; `is_winner` is
  `true` for rank 1 and `false` otherwise; `submitted_at` is the server's receive time in ISO 8601
  with its UTC offset.
- **FR-017**: The file MUST be UTF-8 with a byte-order mark. Any field containing a comma, a
  double quote, a carriage return or a line feed MUST be enclosed in double quotes, with inner
  double quotes doubled.
- **FR-018**: An answer starting with `=`, `+`, `-` or `@` MUST be written to the CSV with a
  leading `'`, so spreadsheet programs show it as text and never execute it.
- **FR-019**: The CSV file name MUST identify the activity (for example its ID and title) and be
  safe to save on Windows and macOS.

**Access and phase rules**

- **FR-020**: Export, CSV download, the teacher results view and the past activities list MUST
  be teacher-only and covered by the 002 passcode check (002 FR-002), with the same "teacher
  passcode required" refusal and no data.
- **FR-021**: Export and CSV download MUST be refused for an activity that is DRAFT or OPEN,
  with a message stating its current phase. The phase MUST be checked by the server at the time
  of the request.
- **FR-022**: Nothing in this feature may change an activity, its phase or its submissions.
  Results are read-only.

**Past activities**

- **FR-023**: The teacher MUST be able to see a list of all CLOSED activities, newest first, each
  with its title, creation date, group count, unit count and submission count, and open the
  results of any of them. DRAFT and OPEN activities MUST NOT appear in the list.

**Privacy** (Constitution Principle VI)

- **FR-024**: Answer text and display names MUST NOT be written to logs, including during
  export and CSV generation. The service account email MAY be shown to the teacher, because it is
  not secret (001 Assumptions).

### Key Entities *(see [domain-class.puml](../../diagrams/domain-class.puml))*

- **Activity, QuestionUnit, AnswerSlot** (from 001): source spreadsheet, tab ID, question
  numbers, kinds and sub-part numbers are what export uses to find cells again. Unchanged.
- **Submission, SubmissionAnswer** (from 002): the data shown in results, exported and written to
  the CSV. Unchanged; read only.
- **Activity results** (derived, not stored): for one CLOSED activity, per unit in sheet order,
  the winner (or none) and the ordered submissions. The student version leaves out submitter
  names and times.
- **Export report** (derived, not stored): the outcome of one export — cells written and units
  skipped, or the list of problems that stopped it.
- **Cell write** (derived, not stored): one target cell found by the re-read and the text to put
  in it.
- **Past activity summary** (derived, not stored): one CLOSED activity's title, creation date,
  group count, unit count and submission count.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With 12 groups and up to 60 student screens connected, every student screen shows
  the results within 1 second of the teacher ending the activity.
- **SC-002**: Over a full activity, a recording of everything the server sends to one student
  before CLOSED contains nothing about other groups' submissions or any rank; after CLOSED it
  contains the complete results.
- **SC-003**: On at least three differently shaped sample sheets, each also tested after rows are
  inserted above and between the questions, 100% of winning answers land in the correct cell with
  the correct text, and 0 other cells change.
- **SC-004**: In 100% of exports where a winning question or sub-part is missing or the sheet has
  detection errors, zero cells are changed and every missing item or error is named.
- **SC-005**: For an activity of up to 50 units, export completes, or reports its error, within
  10 seconds.
- **SC-006**: A CSV containing commas, quotes, line breaks, Chinese text and formula-like answers
  opens in Excel and Google Sheets with every answer whole in its own cell, Chinese shown
  correctly, and no formula executed.
- **SC-007**: 100% of export and CSV requests for DRAFT or OPEN activities, and 100% of teacher
  results, export, CSV and past-list requests without the passcode, are refused and change or
  return nothing.
- **SC-008**: A teacher can go from ending the activity to having the winning answers in the
  worksheet in under 1 minute, with no help.

## Assumptions

- Export always writes to the activity's source spreadsheet and the tab identified by its stored
  tab ID. Choosing another target is out of scope.
- The teacher gives the service account Editor access before exporting. Import keeps working
  with view access. The app uses read-only Google access for import and write access only for
  export, so import cannot write even by mistake (001 FR-005).
- Only units with a winner are written. Their winning answer has text for every slot (002
  FR-016), so every slot of a winning unit is written.
- A unit's kind (single or 題組) at import time decides the export format, even if the sheet has
  changed since.
- Export does not try to detect other edits by the teacher (for example text typed into an
  answer cell after import). Overwriting the whole cell is the recorded decision from 001, and the
  confirmation warns about it.
- Export history is not recorded. Every export reports its own result.
- Receive times are shown to the teacher in the server's local time zone (as in 002). The CSV
  uses ISO 8601 with the UTC offset so it is unambiguous.
- Students can see results only while they hold a membership of that CLOSED activity and it is
  still the activity shown to students. Once the teacher creates a new activity, students move
  to the new join form (002); past results are teacher-only.
- The `'` prefix rule covers exactly `=`, `+`, `-` and `@` as the first character, as requested.
- Expected scale: up to 50 units, 12 groups, so at most a few thousand CSV rows and a few hundred
  cells per export.

## Non-Goals

- Editing, deleting or re-ranking results or submissions.
- Grading answers for correctness, or scoring beyond rank order.
- Changing sheet formatting (fonts, colours, borders, merges) or anything other than the winning
  slots' cell values.
- Exporting to other spreadsheets, other tabs, files other than the CSV, or other services.
- A fair-ordering mode (for example compensating for network delay); rank stays arrival order
  at the server (Constitution Principle I).
- Showing past activities' results to students.
- Exporting losing answers into the sheet.
- Reopening a CLOSED activity.

## Dependencies

- **Feature 001 (sheets import)**: provides the parser used for the re-read (001 FR-006 to
  FR-016, including its error/warning classification), each slot's question number, sub-part
  number and unit kind, the source spreadsheet and tab ID, the service-account error messages,
  and the recorded export format decision (001 Dependencies). The stored cell addresses (001
  FR-021) are kept for display only; export re-locates cells instead.
- **Feature 002 (live activity)**: provides the CLOSED phase, submissions with rank, per-slot
  answers and server receive time (002 FR-019, FR-020), the visibility filter that this feature
  extends for CLOSED (002 FR-024), the teacher passcode check (002 FR-002), the student
  membership (002 FR-012), and the push of every phase change (002 FR-008). 002 FR-025 and
  FR-029 are completed by this feature.
