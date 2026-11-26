# Feature Specification: Import Guided Notes Worksheet

**Feature Branch**: `001-sheets-import` (spec directory; no git branch created)

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "Import a Guided Notes worksheet from Google Sheets as the question set
of a new buzz-in activity. Teacher pastes a URL, picks a tab, previews detected questions (number,
type single/題組, sub-part count, answer cell per slot), confirms to create a DRAFT activity with a
group count of 2–12, and may re-import while the activity is still DRAFT."

## Design Diagrams *(Constitution Principle VIII)*

These diagrams are the blueprint for `/speckit-plan`. Sources and rendered PNGs live side by side
in `diagrams/`.

| Diagram | Source | Image |
|---------|--------|-------|
| System components (whole system) | [system-component.puml](../../diagrams/system-component.puml) | [PNG](../../diagrams/system-component.png) |
| Domain classes (whole system) | [domain-class.puml](../../diagrams/domain-class.puml) | [PNG](../../diagrams/domain-class.png) |
| Sequence: import preview | [001-seq-import-preview.puml](../../diagrams/001-seq-import-preview.puml) | [PNG](../../diagrams/001-seq-import-preview.png) |
| Sequence: confirm and create activity | [001-seq-confirm-create.puml](../../diagrams/001-seq-confirm-create.puml) | [PNG](../../diagrams/001-seq-confirm-create.png) |
| Sequence: re-import into DRAFT activity | [001-seq-reimport.puml](../../diagrams/001-seq-reimport.puml) | [PNG](../../diagrams/001-seq-reimport.png) |

The whole-system diagrams also show parts that later features will specify (Student UI,
real-time channel, groups, participants, submissions). They are included for context only;
this feature delivers only the import path.

## Clarifications

### Session 2026-11-26

- Q: How strictly should the header labels 題號 and 作答 be matched? → A: Ignore all whitespace
  inside and around the label — half-width spaces, full-width spaces and line breaks — then
  require an exact match; no prefix or synonym matching. If no header is found, the error names
  both labels searched for (題號 and 作答).
- Q: If a numbered row's answer cell already contains text that is not a sub-part marker, what
  should import do? → A: Create the slot as usual and show a preview warning naming the cell and
  its current text. At export (feature 003) the slot cell is overwritten entirely — a single
  question's cell becomes the answer, a 題組 slot becomes `（k）answer` — so this warning is the
  teacher's notice that the existing text will be replaced.
- Q: Should the same warning appear when a sub-part marker cell has extra text after the marker
  (e.g. `（2）______`)? → A: Yes. Any slot cell containing text beyond its own marker produces the
  warning (cell + text). A cell holding only its marker, or empty, produces none.
- Q: When a row has an empty 題號 cell and its answer cell holds non-marker text, what should
  import do? → A: The row does not create a slot or change structure, but the preview shows a
  warning naming the cell and its text.
- Q: Can the teacher have several activities saved at the same time? → A: Activities are kept,
  but at most one is non-CLOSED (DRAFT or OPEN): creating a new activity is refused while one
  exists. CLOSED activities are kept with their results and CSV viewable. The teacher UI shows
  only the current (non-CLOSED) activity plus a simple list of past CLOSED ones for results.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preview the questions detected in a worksheet (Priority: P1)

The teacher pastes the link to a Google Sheets Guided Notes worksheet. The app lists the
spreadsheet's tabs with the first tab selected, reads the selected tab, and shows a preview of
every detected question: its number, its type (single question or 題組), how many sub-parts it
has, and which cell each answer slot maps to. Any problems found are listed with the row they
occur on and what the teacher can do about them.

**Why this priority**: Nothing else in the app works without a question set, and the preview is
how the teacher confirms the worksheet was understood correctly before students see anything.

**Independent Test**: Paste the link to a prepared sample worksheet and compare the preview with
the known list of questions, sub-parts and answer cells. Delivers value on its own as a check
that a worksheet is compatible.

**Acceptance Scenarios**:

1. **Given** a shared worksheet whose first tab has a header row with 題號 and 作答 and five
   numbered rows, **When** the teacher pastes its link, **Then** the first tab is preselected and
   the preview lists questions 1–5, each with its type, sub-part count and answer cell.
2. **Given** a question numbered 3 followed by rows whose answer cells read （1）, （2）, （3）,
   **When** the preview is shown, **Then** question 3 is a 題組 with 3 sub-parts, and each
   sub-part maps to the answer cell on its own row.
3. **Given** a numbered row whose answer cell is empty and no sub-part rows follow it, **When**
   the preview is shown, **Then** that question is a single question with one slot mapped to its
   empty answer cell.
4. **Given** a spreadsheet with several tabs, **When** the teacher selects a different tab,
   **Then** the preview is rebuilt from that tab only.
5. **Given** a pasted link ending in `#gid=` followed by the ID of the spreadsheet's third tab,
   **When** the tab list is shown, **Then** the third tab is preselected and previewed.
6. **Given** question-number cells reading `1`, `2.`, `3、`, `Q4`, `q5` and `６`, **When** the
   preview is shown, **Then** questions 1–6 are detected.
7. **Given** a question-number cell reading `備註` below the header, **When** the preview is
   shown, **Then** a warning names that row and its content, and the row does not start a
   question.
8. **Given** any worksheet, **When** a preview is produced, **Then** the worksheet's contents are
   unchanged (import never writes to the sheet).

---

### User Story 2 - Confirm the preview to create a DRAFT activity (Priority: P1)

After reviewing a preview with no errors, the teacher chooses how many student groups will take
part (2–12) and confirms. The app creates a new activity in the DRAFT phase holding the detected
questions, their slots, and the answer cell each slot maps to.

**Why this priority**: Creating the activity is the outcome the teacher wants; the preview alone
does not let a class start.

**Independent Test**: Confirm a clean preview with a chosen group count, then reopen the activity
and verify its phase is DRAFT, its group count is as chosen, and its questions, slots and answer
cells match the preview exactly.

**Acceptance Scenarios**:

1. **Given** a preview with no errors, **When** the teacher picks 6 groups and confirms, **Then**
   an activity is created in DRAFT with 6 groups and exactly the questions, slots and answer
   cells shown in the preview.
2. **Given** a preview with one or more errors, **When** the teacher tries to confirm, **Then**
   confirmation is blocked until the errors are fixed in the sheet and the preview is rebuilt.
3. **Given** a preview with only warnings, **When** the teacher confirms, **Then** the activity
   is created after the teacher acknowledges the warnings.
4. **Given** a group count outside 2–12, **When** the teacher confirms, **Then** the activity is
   not created and the teacher is told the allowed range.
5. **Given** the sheet's structure changed after the preview was shown, **When** the teacher
   confirms, **Then** no activity is created and the teacher is shown the updated preview.
6. **Given** an activity already exists in DRAFT or OPEN, **When** the teacher tries to create a
   new activity, **Then** it is refused with a message naming the current activity and its
   phase, and suggesting re-import (if DRAFT) or closing it first (if OPEN).
7. **Given** only CLOSED activities exist, **When** the teacher confirms a clean preview,
   **Then** the new activity is created and the CLOSED activities are kept unchanged.

---

### User Story 3 - Re-import into a DRAFT activity (Priority: P2)

The teacher fixes the worksheet (or picks another tab or sheet) and re-imports into an existing
activity that is still in DRAFT. After a new preview and confirmation, the activity's question
set is replaced entirely. Once the activity has been opened or closed, re-import is refused.

**Why this priority**: Teachers often spot a mistake after creating the activity; re-importing
saves recreating it. It is not required for a first class session.

**Independent Test**: Create a DRAFT activity, change the sheet, re-import, and verify the
activity now holds only the new questions; then open the activity (via a later feature or test
setup) and verify re-import is refused.

**Acceptance Scenarios**:

1. **Given** a DRAFT activity with 5 questions, **When** the teacher re-imports a sheet that now
   has 7 questions and confirms, **Then** the activity holds exactly those 7 questions and none of
   the old ones.
2. **Given** a DRAFT activity, **When** the teacher re-imports, **Then** the activity's phase and
   group count are unchanged.
3. **Given** an activity in OPEN or CLOSED, **When** the teacher attempts to re-import, **Then**
   the request is refused with a message stating the activity's phase, and its questions are
   unchanged.
4. **Given** a DRAFT activity that is opened after the re-import preview was shown, **When** the
   teacher confirms the re-import, **Then** it is refused and the questions are unchanged.

---

### Edge Cases

- **Sheet not shared with the app**: the teacher sees a message containing the app's service
  account email address and instructions to share the sheet with it as a viewer.
- **Invalid URL** (not a Google Sheets spreadsheet link, or malformed): the teacher is told the
  link is not a Google Sheets spreadsheet link; no request to the sheet is attempted.
- **Spreadsheet or tab does not exist** (deleted, wrong ID): the teacher is told it could not be
  found.
- **Tab with no header row** (no single row contains both 題號 and 作答): error stating the
  header could not be found and naming both labels searched for, 題號 and 作答.
- **Header labels with spaces or line breaks inside** (`題 號`, `作　答`, a line break between
  the characters): recognised as the labels. Labels with extra characters (`作答區`, `題號欄`)
  are not recognised.
- **Header labels in different rows, or a label appearing more than once in the header row**:
  treated as no usable header; error names the conflicting cells.
- **Duplicate question numbers**: error listing each duplicated number and the rows it appears on.
- **Non-sequential question numbers** (gaps such as 1, 2, 4, or not starting at 1): warning
  listing the missing numbers; confirmation is still allowed.
- **Numbers out of order** (e.g., 1, 3, 2): warning; questions keep sheet row order.
- **Unnumbered row with non-marker text in the answer column** (e.g., `提示：看課本p.12`): no
  slot is created and the current question continues; a warning names the cell and its text so
  the teacher can add a marker if it was meant to be a sub-part.
- **Blank spacer rows**: ignored; they do not end the current question, so sub-part rows after a
  spacer still belong to it.
- **Merged question-text cells**: do not affect detection; only the question-number and answer
  columns are read. If an answer cell is part of a merged range, its location is the top-left
  cell of that range.
- **Half-width vs full-width markers and digits**: （1）, (1), （１）, and mixed forms like （1)
  are all recognised as sub-part 1.
- **Trailing or leading spaces** in numbers or markers: ignored. (Header labels ignore all
  whitespace; see above.)
- **Numbered row with an empty answer cell** and no following sub-part rows: single question,
  one slot at that empty cell.
- **Slot cell that already holds text beyond its marker** (a numbered row with `答：`,
  `______` or an old answer; a sub-part row with `（2）______`): the slot is created at that cell,
  with a warning naming the cell and its text, because export will overwrite the whole cell. A
  cell holding only `（2）` gives no warning.
- **Duplicate sub-part marker within one question** (two （2） rows): error naming the question
  and rows.
- **Gap in sub-part markers** (（1）, （3）): warning; slots keep the markers' numbers.
- **Sub-part marker before the first numbered row**: error naming the row (the marker belongs to
  no question).
- **Zero questions found** (header present but no numbered rows below it): error; confirmation is
  blocked.
- **Question-number formats**: `1`, `1.`, `1、`, `Q1`, `q1`, and the same forms with full-width
  digits (e.g., `１`, `１.`, `Q１`) are all question 1.
- **Unrecognised question-number cell** (any other non-empty content, e.g. `備註`, `0`, `-1`,
  `1.5`, `一`): warning naming the row and the cell's content; the row does not start a question.
  Such cells are never silently ignored.
- **`#gid=` in the URL that matches no tab**: the first tab is preselected.

## Requirements *(mandatory)*

### Functional Requirements

**Locating the sheet**

- **FR-001**: The teacher MUST be able to start an import by pasting a Google Sheets spreadsheet
  URL.
- **FR-002**: The system MUST reject a URL that does not identify a Google Sheets spreadsheet,
  without contacting Google.
- **FR-003**: The system MUST list every tab of the spreadsheet. If the pasted URL contains
  `#gid=<id>` and a tab with that ID exists, that tab MUST be preselected; otherwise the first tab
  MUST be preselected. The teacher MUST be able to select any other tab.
- **FR-004**: When the spreadsheet cannot be read because it is not shared with the app, the
  system MUST show the app's service account email address and tell the teacher to share the
  sheet with it.
- **FR-005**: Import MUST be read-only: no import, preview, or re-import action may modify the
  spreadsheet in any way.

**Detecting structure** (Constitution Principle II)

- **FR-006**: The system MUST find the header row as the topmost row containing one cell whose
  text is exactly 題號 and one cell whose text is exactly 作答, after removing all whitespace
  from the cell — half-width spaces, full-width spaces (`　`) and line breaks, wherever they
  occur (so `題 號`, `作　答`, and 題 and 號 split by a line break all match; `作答區` does
  not). The 題號 cell's column is
  the question-number column; the 作答 cell's column is the answer column.
- **FR-007**: The system MUST NOT assume any fixed row, column, or cell address for the header,
  questions, or answers; every location MUST be derived from the sheet's content.
- **FR-008**: Every row below the header whose question-number cell holds a positive integer MUST
  start a new question with that number. Accepted forms, with surrounding spaces ignored, are
  `n`, `n.`, `n、`, `Qn` and `qn`, where n is written in half-width or full-width digits.
- **FR-008a**: A non-empty question-number cell below the header that does not match an accepted
  form MUST produce a preview warning stating the row number and the cell's content; it MUST NOT
  start a question and MUST NOT be silently ignored. Duplicate question numbers remain an error.
- **FR-009**: A row whose answer cell begins with a sub-part marker （k） or (k) — k a positive
  integer, with any mix of half-width and full-width parentheses and digits, surrounding spaces
  ignored — MUST belong to the current question as sub-part k.
- **FR-010**: The numbered row MUST itself be sub-part 1 when its own answer cell holds the （1）
  marker, or when it holds no marker and the first sub-part row after it is marked （2）. When
  the first sub-part row after it is marked （1）, the numbered row is not a slot.
- **FR-011**: A question with 2 or more sub-parts MUST be classified as a 題組 (one answer unit
  with one slot per sub-part); any other question MUST be a single question with exactly one slot
  at the numbered row's answer cell.
- **FR-011a**: When any slot's answer cell contains text beyond its own sub-part marker — on a
  numbered row or a sub-part row, with or without a marker — the system MUST still create the slot
  there and MUST show a preview warning naming the cell and its current text, stating that export
  will replace it. An empty cell, or one holding only its marker, MUST NOT produce this warning.
- **FR-012**: The number of detected questions MUST equal the number of numbered rows below the
  header.
- **FR-013**: Question text MUST NOT be required or imported; questions are identified and shown
  by number only.
- **FR-014**: Blank rows MUST be skipped without ending the current question.
- **FR-014a**: A row below the header whose question-number cell is empty and whose answer cell
  holds text that does not begin with a sub-part marker MUST NOT create a slot or end the current
  question, and MUST produce a preview warning naming the cell and its text.

**Problems found**

- **FR-015**: The system MUST classify each problem as an error (blocks confirmation) or a
  warning (allows confirmation after acknowledgement), using the classification in Edge Cases.
- **FR-016**: Every error and warning MUST name the row(s) or cell(s) involved and state what the
  teacher can change to resolve it.

**Preview**

- **FR-017**: The preview MUST list every detected question in sheet row order with its number,
  type (single or 題組), sub-part count, and the answer cell of each slot (tab name plus cell
  reference such as `B7`).
- **FR-018**: The preview MUST show the total number of questions and total number of slots.

**Creating the activity**

- **FR-019**: The teacher MUST choose a group count between 2 and 12 inclusive before confirming;
  values outside that range MUST be rejected.
- **FR-020**: On confirmation of a preview without errors, the system MUST create a new activity
  in the DRAFT phase with the chosen group count, the detected questions and slots, and the source
  spreadsheet and tab.
- **FR-020a**: At most one activity MAY be non-CLOSED (DRAFT or OPEN) at any time. The system
  MUST refuse to create a new activity while one exists, naming that activity and its phase. The
  check MUST be made inside the same all-or-nothing step that creates the activity, so two
  simultaneous confirmations cannot both succeed. Creating an activity MUST NOT modify or delete
  any CLOSED activity.
- **FR-021**: Each slot's answer cell location MUST be computed at import time and stored with the
  activity for use by a later export feature.
- **FR-022**: The activity MUST be created from the same detection result the teacher confirmed.
  If the sheet's detected structure differs at confirmation time, the system MUST create nothing
  and show the updated preview.
- **FR-023**: Creating the activity MUST be all-or-nothing: either the activity with all its
  questions and slots is saved, or nothing is saved.

**Re-import**

- **FR-024**: While an activity is in DRAFT, the teacher MUST be able to re-import (same or
  different spreadsheet or tab), preview, and confirm to replace the activity's entire question
  set in a single all-or-nothing step.
- **FR-025**: Re-import MUST leave the activity's phase and group count unchanged.
- **FR-026**: The server MUST refuse re-import when the activity is OPEN or CLOSED, checking the
  phase at the moment of confirmation, not only when the re-import began.

### Key Entities *(see [domain-class.puml](../../diagrams/domain-class.puml))*

- **Activity**: one buzz-in session built from one worksheet tab. Has a phase (DRAFT, OPEN,
  CLOSED — this feature creates DRAFT only), a group count (2–12), the source spreadsheet and
  tab, and an ordered set of question units. At most one activity is non-CLOSED at a time (the
  "current activity"); CLOSED activities are kept.
- **QuestionUnit**: one detected question. Has its question number, its type (single or 題組),
  the sheet row it was found on, and one or more answer slots. Later features award exactly one
  winner per question unit.
- **AnswerSlot**: one place an answer goes. Has its sub-part number (1 for a single question) and
  the answer cell location (tab and cell) computed at import.
- **Import preview** (transient, not stored): the detection result for one tab — questions,
  slots, errors and warnings — shown to the teacher before confirmation.
- **Group, Participant, Submission**: part of the overall model, defined by later features; not
  created or changed by this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a worksheet of up to 200 rows, the teacher sees the preview within 5 seconds of
  pasting the link or changing the tab.
- **SC-002**: On a reference set of at least three differently shaped Guided Notes worksheets
  (different header positions, answer-column positions, and sub-part layouts), 100% of questions,
  types, sub-part counts and answer cells are detected correctly.
- **SC-003**: A teacher with a correctly shared worksheet can go from pasting the link to a
  created DRAFT activity in under 2 minutes.
- **SC-004**: 100% of error and warning messages identify the row or cell involved and the
  change needed; a teacher can resolve each reference-set error without outside help.
- **SC-005**: Across all import, preview and re-import actions, the spreadsheet's contents and
  revision history show zero changes made by the app.
- **SC-006**: Re-import attempts on OPEN or CLOSED activities are refused 100% of the time and
  leave the questions unchanged.

## Assumptions

- Only the teacher uses this feature. Restricting these actions to the teacher is the job of
  feature 002 (see Dependencies); this feature assumes the requester is the teacher.
- The app reads sheets through a single Google service account whose credentials are supplied via
  configuration (Constitution Principle VI); the teacher shares each sheet with that account. The
  service account email is not secret and may be displayed.
- Cell values are read as displayed in the sheet, so a number shown as `1` is read as 1.
- Answer cells are located by position at import time; if the teacher later inserts or deletes
  rows in the sheet, stored locations may become stale. Detecting that is a concern of the export
  feature.
- One question table per tab: each tab has one header row and the numbered rows below it until
  the end of the tab's data. Side-by-side or stacked tables in one tab are not supported.
- The activity is named from the spreadsheet title and tab name; renaming is out of scope.
- The group count field is prefilled with 4.
- Non-goals: importing question text or correct answers; Excel/CSV upload; automatic grading;
  editing questions in the app.

## Dependencies

- **Feature 002 (teacher passcode)**: import, preview, confirm and re-import are teacher-only
  actions. Feature 002's teacher passcode check MUST cover every one of them; this feature does
  not implement its own access control.
- **Feature 003 (export) — recorded decisions**: export overwrites each slot's cell entirely.
  A single question's cell becomes the answer text. Every slot of a 題組 becomes `（k）answer`,
  where k is the slot's sub-part number; this includes a numbered row that became sub-part 1
  without its own marker (FR-010), which is exported as `（1）answer`. This feature stores each
  slot's sub-part number and answer cell, and warns about existing text (FR-011a), so that 003
  can do this.
- **Later features — activity history (recorded decision)**: CLOSED activities are kept and
  their results and CSV stay viewable. The teacher UI shows only the current (non-CLOSED)
  activity, plus a simple list of past CLOSED activities for viewing results. Building that list
  and the results/CSV view is outside this feature; this feature only guarantees it never deletes
  or alters CLOSED activities (FR-020a).
