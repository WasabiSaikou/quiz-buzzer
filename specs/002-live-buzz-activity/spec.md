# Feature Specification: Live Buzz-In Activity with Real-Time Phase Sync

**Feature Branch**: `002-live-buzz-activity` (spec directory; no git branch created)

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "Feature 002: run the live buzz-in activity with real-time phase sync.
Builds on feature 001 (specs/001-sheets-import): the activity, its question units and answer slots,
and its group count already exist in DRAFT; at most one activity is non-CLOSED. Teacher opens the
DRAFT activity, students join groups and submit answers per question unit, the server ranks
submissions by arrival, the teacher watches a live dashboard and ends the activity; every phase
change reaches every client instantly."

## Design Diagrams *(Constitution Principle VIII)*

These diagrams are the blueprint for `/speckit-plan`. Sources and rendered PNGs live side by side
in `diagrams/`. Routes, message names and module names in the diagrams are a proposed design for
the plan to confirm; the requirements below do not depend on them.

| Diagram | Source | Image |
|---------|--------|-------|
| System components (whole system, updated for 002) | [system-component.puml](../../diagrams/system-component.puml) | [PNG](../../diagrams/system-component.png) |
| Domain classes (whole system, updated for 002) | [domain-class.puml](../../diagrams/domain-class.puml) | [PNG](../../diagrams/domain-class.png) |
| Sequence: teacher unlock and access check | [002-seq-teacher-unlock.puml](../../diagrams/002-seq-teacher-unlock.puml) | [PNG](../../diagrams/002-seq-teacher-unlock.png) |
| Sequence: open activity | [002-seq-open-activity.puml](../../diagrams/002-seq-open-activity.puml) | [PNG](../../diagrams/002-seq-open-activity.png) |
| Sequence: student join (and change group in DRAFT) | [002-seq-join.puml](../../diagrams/002-seq-join.puml) | [PNG](../../diagrams/002-seq-join.png) |
| Sequence: submit with ranking | [002-seq-submit.puml](../../diagrams/002-seq-submit.puml) | [PNG](../../diagrams/002-seq-submit.png) |
| Sequence: end activity | [002-seq-end-activity.puml](../../diagrams/002-seq-end-activity.puml) | [PNG](../../diagrams/002-seq-end-activity.png) |
| Sequence: cancel DRAFT activity | [002-seq-cancel-activity.puml](../../diagrams/002-seq-cancel-activity.puml) | [PNG](../../diagrams/002-seq-cancel-activity.png) |
| Sequence: refresh / reconnect | [002-seq-reconnect.puml](../../diagrams/002-seq-reconnect.puml) | [PNG](../../diagrams/002-seq-reconnect.png) |

The feature 001 sequence diagrams (`001-seq-*.puml`) are unchanged. Their "teacher passcode check
applies" notes are put into effect by FR-002 below.

## Clarifications

### Session 2026-11-26

- Q: After joining, a refresh returns a student to the same group. How does a student who picked
  the wrong group fix it? → A: The student can leave and choose another group only while the
  activity is DRAFT. Once the activity is OPEN, their group is fixed for the rest of the activity.
  This handles the usual mistake made at the start and stops anyone switching groups during the
  race to submit for a second group.

### Session 2026-11-27

- Q: Can the teacher get rid of the current DRAFT activity, for example to import a different
  worksheet? → A: Yes. The teacher can cancel the current DRAFT activity. It is deleted along
  with its questions, groups and student memberships. Nothing of value is lost, because a DRAFT
  activity never has submissions. Cancelling frees the "one non-CLOSED activity" slot for a new
  import. An OPEN activity cannot be cancelled, only ended, and a CLOSED activity is never
  deleted. This replaces the earlier default that a DRAFT activity could not be discarded.

## Roles

- **Teacher**: runs the activity. Unlocks the teacher controls with the teacher passcode, which is
  set in the app's local configuration (`TEACHER_PASSCODE` in `.env`). Opens the activity, watches
  the live dashboard, and ends the activity. Can cancel the activity while it is still DRAFT.
  The same passcode also unlocks feature 001's import and re-import actions.
- **Student**: a member of one group in the current activity. Has no account. Joins by choosing a
  group number (1 to the activity's group count) and typing a display name. Any member can submit
  an answer for their group.
- **Group**: a team of zero or more students, numbered 1 to the activity's group count. Each group
  gets one submission per question unit, and the group (not the individual) is what gets ranked.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Teacher opens the activity and every screen switches to answering (Priority: P1)

The teacher unlocks the teacher controls with the passcode and sees the current DRAFT activity.
After the teacher confirms "Open", the activity becomes OPEN. Every connected screen changes at
once: student screens move from the waiting screen to the answering screen, and every teacher tab
shows the activity as OPEN.

**Why this priority**: Opening is what starts the race. Students cannot answer anything until it
happens, and all groups must start at the same moment for the race to be fair.

**Independent Test**: Create a DRAFT activity (feature 001), connect two student screens and two
teacher tabs, and open the activity from one tab. All four screens must show OPEN within a second,
with no reload.

**Acceptance Scenarios**:

1. **Given** a DRAFT activity and a locked teacher page, **When** the teacher enters the correct
   passcode, **Then** the teacher controls unlock and show the current activity, its phase, and
   its groups.
2. **Given** a locked teacher page, **When** the teacher enters a wrong passcode, **Then** the
   controls stay locked, a "wrong passcode" message is shown, and no activity data is shown.
3. **Given** a DRAFT activity with students waiting, **When** the teacher confirms "Open",
   **Then** the phase becomes OPEN and every connected student screen switches to the answering
   screen without a reload.
4. **Given** an OPEN activity, **When** a second teacher tab (or a stale tab) asks to open it
   again, **Then** the request is refused with a message that the activity is already OPEN, and
   nothing changes.
5. **Given** an OPEN activity, **When** the teacher tries to re-import questions (feature 001),
   **Then** the re-import is refused.

---

### User Story 2 - Student joins a group, waits, then answers for the group (Priority: P1)

A student opens the student page, chooses a group number and types a display name. While the
activity is DRAFT the student sees a waiting screen with their group number. When the activity
opens, the student sees every question unit by number. A single question has one answer field. A
題組 has one field per sub-part, labelled （1）, （2）, and so on. The student fills in a unit and
submits it on behalf of their group.

**Why this priority**: Submitting answers is the core of the activity. Without it there is no
race.

**Independent Test**: With an OPEN activity of 3 units (one a 題組 with 2 sub-parts), join group
2 from a student screen, submit each unit, and check that each submission is accepted and that a
second submission of the same unit is refused.

**Acceptance Scenarios**:

1. **Given** a DRAFT activity with 6 groups, **When** a student chooses group 3 and enters the
   name "小明", **Then** the student joins group 3 and sees a waiting screen naming group 3.
2. **Given** a student waiting in DRAFT, **When** the teacher opens the activity, **Then** the
   student sees the question units listed by number in sheet order, with one field per slot.
3. **Given** an OPEN activity and a 題組 unit with 3 sub-parts, **When** the student fills all 3
   fields and submits, **Then** the submission is accepted as a whole and the unit shows as
   submitted by the group.
4. **Given** a 題組 unit with one field left empty or containing only spaces, **When** the student
   submits, **Then** it is refused with a message naming the empty sub-part, and nothing is
   saved.
5. **Given** a field longer than 200 characters, **When** the student submits, **Then** it is
   refused with a message naming that sub-part and the limit, and nothing is saved.
6. **Given** group 2 has already submitted unit 4, **When** any member of group 2 submits unit 4
   again, **Then** it is refused with "Your group has already submitted question 4", and the
   group's existing answer is shown.
7. **Given** an OPEN activity, **When** a student joins a group for the first time, **Then** the
   student goes straight to the answering screen.
8. **Given** a student in group 3 while the activity is DRAFT, **When** the student chooses
   "Change group" and picks group 5, **Then** they are now a member of group 5 only.
9. **Given** an OPEN activity, **When** a student tries to change group, **Then** it is refused
   and they stay in their group.
10. **Given** a student accepted into a group, **When** they submit, **Then** they see only that
    their group's answer was submitted. They do not see its rank or whether any other group
    answered first.

---

### User Story 3 - Teacher watches the live dashboard and ends the activity (Priority: P1)

While the activity is OPEN, the teacher sees a dashboard listing every question unit in sheet
order. Under each unit are its submissions in arrival order, each with its rank, group number,
the display name of the student who submitted it, and the answer for each slot. Rank 1 is marked
as the winner. The dashboard updates as each submission arrives. The dashboard also shows each
group's members. When the teacher confirms "End", the activity becomes CLOSED and every connected
screen moves to the closed state at once.

**Why this priority**: The teacher needs to see who answered first in order to run the class and
reward the winners. Ending is the only way to stop submissions and close the race.

**Independent Test**: With an OPEN activity, submit from three groups to the same unit, check that
the dashboard shows them with ranks 1, 2 and 3 in arrival order, then end the activity and check
that every screen shows CLOSED and further submissions are refused.

**Acceptance Scenarios**:

1. **Given** an OPEN activity, **When** groups 4, 1 and 6 submit unit 2 in that order, **Then**
   the dashboard lists them under unit 2 as rank 1 (group 4, winner), rank 2 (group 1) and rank 3
   (group 6), each with its answers and submitter.
2. **Given** the dashboard is open in two teacher tabs, **When** a submission is accepted, **Then**
   both tabs show it within a second without a reload.
3. **Given** a unit with no submissions, **When** the teacher views the dashboard, **Then** the
   unit is listed with "No submissions yet".
4. **Given** an OPEN activity, **When** the teacher confirms "End", **Then** the phase becomes
   CLOSED and every connected student and teacher screen shows the closed state without a reload.
5. **Given** a CLOSED activity, **When** any student submits, **Then** it is refused with
   "The activity has ended" and nothing is saved.
6. **Given** an OPEN activity with zero submissions, **When** the teacher ends it, **Then** it
   closes normally and the dashboard shows every unit with no submissions.
7. **Given** the activity has just been ended, **When** the teacher looks at the dashboard,
   **Then** it shows the final submissions and ranks of the closed activity.

---

### User Story 4 - Teammates see their group's submissions live (Priority: P2)

When any member of a group submits a unit, every other member of that group sees the unit change
to "submitted" at once, showing the submitted answers and who submitted them. They do not need to
reload, and they cannot submit that unit again by mistake.

**Why this priority**: It prevents duplicate work and confusion inside a group. The core race
works without it, because duplicate submissions are refused anyway (FR-018).

**Independent Test**: Join group 3 from two student screens. Submit unit 1 from the first screen
and check that the second screen shows unit 1 as submitted, with the answer and submitter, within
a second.

**Acceptance Scenarios**:

1. **Given** two members of group 3 on the answering screen, **When** one submits unit 1, **Then**
   the other sees unit 1 as submitted, with the answers and the submitter's display name, without
   a reload.
2. **Given** a member who has typed an answer for unit 1 but not submitted it, **When** a teammate
   submits unit 1 first, **Then** that member's unit 1 becomes read-only and shows the teammate's
   submitted answer.
3. **Given** a submission by group 5, **When** it is accepted, **Then** members of every other
   group see no change of any kind.

---

### User Story 5 - Teacher cancels a DRAFT activity (Priority: P2)

The teacher created a DRAFT activity but no longer wants it, for example because they picked the
wrong worksheet. After the teacher confirms "Cancel activity", it is deleted along with its
questions, groups and student memberships. There is then no current activity, so the teacher can
import a new worksheet straight away. Students who had joined see "No activity available yet".

**Why this priority**: Without it, a mistaken DRAFT activity can only be fixed by re-importing
into it, which also keeps its group count. Classes can still run without cancelling, so it is
not P1.

**Independent Test**: Create a DRAFT activity and join it from a student screen. Cancel it, then
check that the student screen shows "No activity available yet", that the activity is gone, and
that a new import creates a new DRAFT activity.

**Acceptance Scenarios**:

1. **Given** a DRAFT activity, **When** the teacher confirms "Cancel activity", **Then** the
   activity, its questions, groups and memberships are deleted, and every teacher tab shows no
   current activity.
2. **Given** students waiting in a DRAFT activity, **When** the teacher cancels it, **Then** every
   connected student screen shows "No activity available yet" without a reload, and the students'
   memberships are no longer valid.
3. **Given** a DRAFT activity has just been cancelled, **When** the teacher imports and confirms a
   worksheet (feature 001), **Then** a new DRAFT activity is created.
4. **Given** an OPEN activity, **When** the teacher (or a stale tab) asks to cancel it, **Then**
   it is refused with a message that an OPEN activity can only be ended, and nothing changes.
5. **Given** a CLOSED activity, **When** a request to cancel it arrives, **Then** it is refused
   and the activity and its submissions are kept.
6. **Given** a DRAFT activity, **When** the teacher clicks "Cancel activity" and then backs out of
   the confirmation, **Then** nothing changes.

---

### Edge Cases

- **Two groups submit the same unit in the same millisecond**: both are accepted. The server
  decides which arrived first, and they get ranks 1 and 2. There are never two rank-1 submissions,
  and client clocks are never used to decide.
- **Two members of the same group submit the same unit at the same time**: exactly one is
  accepted. The other is refused as "already submitted by your group" and is shown the accepted
  answer.
- **A submission arrives at the instant the teacher ends the activity**: it is either accepted
  in full before the close, so it appears on the dashboard and keeps its rank, or refused with
  "The activity has ended". It is never partly saved or saved after the close.
- **Student refreshes the page mid-activity**: they return to the same group and screen with
  their group's submitted units, without typing their name again. Text they typed but did not
  submit may be lost.
- **Network drop, or the server restarts while the activity is OPEN**: the client shows that it is
  reconnecting and tries again automatically. Once connected it shows the current phase and state.
  Accepted submissions are never lost. Teachers must enter the passcode again after a server
  restart.
- **Phase changes while a client is disconnected**: on reconnect the client shows the current
  phase (for example, it goes straight to the closed screen).
- **Duplicate display names in one group**: allowed. Both students are separate members. The
  dashboard and teammates may see the same name twice.
- **A group with no members**: allowed. The dashboard shows it with 0 members. It simply has no
  submissions.
- **Closing with zero submissions**: allowed. The activity closes normally.
- **Whitespace-only answer** (spaces, full-width spaces, line breaks): treated as empty and
  refused, naming the sub-part.
- **Display name empty, whitespace-only, or longer than 20 characters**: refused, with the rule
  stated.
- **Group number outside 1 to the group count** (for example, from a crafted request): refused.
- **A student calls a teacher action directly** (open, end, dashboard, the teacher live channel,
  or any feature 001 import or re-import action): refused with "teacher passcode required", and no
  activity, submission or roster data is returned.
- **A student sends a request claiming another group's number**: ignored. The server knows each
  student's group only from that student's own membership.
- **Teacher open in two tabs or two browsers**: both stay in sync. Of two simultaneous "Open"
  (or "End") requests, exactly one takes effect. The other is refused with the current phase, and
  both tabs end up showing the same phase.
- **Teacher tries to end a DRAFT activity, or open a CLOSED one**: refused with the current phase.
  Phases only move forward, one step at a time. The refusal to end a DRAFT activity points the
  teacher to "Cancel activity" instead.
- **Cancel and Open requested at the same time** (two tabs): exactly one takes effect. If Open
  wins, the cancel is refused because the activity is OPEN. If Cancel wins, the open is refused
  because the activity no longer exists.
- **A student joins, or changes group, at the instant the teacher cancels**: either the join
  completes first and is then deleted with the activity, or it is refused because there is no
  current activity. In both cases the student ends up on "No activity available yet".
- **Re-import confirmed at the instant the teacher cancels** (feature 001): if the cancel wins,
  the re-import is refused because the activity no longer exists, and nothing is created.
- **A student with a membership of a cancelled activity refreshes**: the membership is no longer
  valid. The student sees "No activity available yet", or the join form if a new activity
  exists.
- **No current activity when a student opens the page**: the page says no activity is available
  yet. It switches to the join form by itself when the teacher creates one.
- **A student is a member of a CLOSED activity and the teacher then creates a new one**: the old
  membership does not carry over. The student sees the join form for the new activity.
- **Submitting while DRAFT** (for example, from a crafted request): refused with "The activity has
  not opened yet".
- **Re-import while students are waiting in DRAFT** (feature 001): memberships are kept, and the
  new question set is what students see when the activity opens.
- **Teacher passcode not set in the configuration**: the app does not start, and the startup
  message names the missing setting (never a value).

## Requirements *(mandatory)*

### Functional Requirements

**Teacher access**

- **FR-001**: The teacher MUST unlock the teacher controls by entering the passcode set in the
  app's local configuration. A wrong passcode MUST be refused, and no teacher data may be
  returned.
- **FR-002**: Every teacher action and teacher view MUST require an unlocked teacher. This covers
  opening, ending and cancelling the activity, the dashboard, the teacher live channel, and every feature 001
  teacher action: listing tabs, preview, confirm (create activity), viewing the current or a
  specific activity, re-import preview, and re-import confirm. A request without an unlocked
  teacher MUST be refused with the same "teacher passcode required" response and no data. A
  student page MUST NOT be able to perform any of these actions.
- **FR-003**: Once unlocked, a browser MUST stay unlocked until the server restarts. Several
  teacher tabs or browsers MAY be unlocked at the same time.
- **FR-004**: The passcode MUST NOT appear in any response, page, log, or the browser's stored
  data. If the passcode is not configured, the app MUST refuse to start, with a message naming the
  missing setting.

**Phases** (Constitution Principle IV)

- **FR-005**: The activity phase MUST be held by the server and MUST move only forward, one step
  at a time: DRAFT → OPEN → CLOSED. Open MUST be allowed only from DRAFT, and End only from OPEN.
  Any other request MUST be refused with a message stating the current phase, and nothing may
  change.
- **FR-006**: Changing the phase and checking that the change is allowed MUST happen in one
  all-or-nothing step, so that of two simultaneous requests for the same change, exactly one
  succeeds.
- **FR-007**: The teacher UI MUST ask for confirmation before Open, End and Cancel, stating that
  the action cannot be undone.
- **FR-008**: Every phase change MUST be pushed at once to every connected teacher and student
  client. So must the creation of a current activity (feature 001), so that students on the "no
  activity yet" page move to the join form, and the cancellation of one (FR-008a), so that every
  client shows that there is no current activity.

**Cancelling a DRAFT activity**

- **FR-008a**: The teacher MUST be able to cancel the current activity while it is DRAFT.
  Cancelling MUST delete the activity together with its questions, slots, groups and student
  memberships, so that there is no current activity and a new import can be confirmed (feature
  001, FR-020a). Cancelling is not a phase: no CANCELLED activity is kept.
- **FR-008b**: Checking that the activity is still DRAFT and deleting it MUST happen in one
  all-or-nothing step. A cancel request for an OPEN activity MUST be refused with a message that
  an OPEN activity can only be ended. A cancel request for a CLOSED activity MUST be refused, and
  CLOSED activities MUST never be deleted. Of a simultaneous Cancel and Open, exactly one takes
  effect (FR-006).
- **FR-008c**: After a cancel, every connected student MUST see "No activity available yet"
  (FR-031). Their memberships MUST no longer be valid for any activity (FR-014).

**Joining**

- **FR-009**: A student MUST be able to join the current activity by choosing a group number from
  1 to the activity's group count and entering a display name of 1–20 characters after trimming
  leading and trailing whitespace. Other group numbers and display names MUST be refused.
- **FR-010**: Joining MUST be allowed while the activity is DRAFT or OPEN. It MUST be refused when
  the activity is CLOSED or when there is no current activity.
- **FR-011**: Display names MUST NOT need to be unique, within a group or across groups.
- **FR-012**: The student's browser MUST remember the membership. Refreshing or reopening the
  student page MUST return the student to the same group of the same activity without asking for
  their details again.
- **FR-013**: While the activity is DRAFT, a student MUST be able to leave their group and join
  another one. While the activity is OPEN or CLOSED, changing group MUST be refused.
- **FR-014**: The server MUST work out a student's group only from that student's membership,
  never from a group number sent with a request. A membership in one activity MUST NOT be valid
  for any other activity.

**Answering and ranking** (Constitution Principle I)

- **FR-015**: While the activity is OPEN, a student MUST see every question unit of the activity,
  by number only and in sheet order. A single question shows one answer field. A 題組 shows one
  answer field per sub-part, labelled （k）. Question text is not shown, because it is not
  imported (feature 001, FR-013).
- **FR-016**: A unit MUST be submitted as a whole. Every slot MUST be non-empty after trimming
  leading and trailing whitespace (including full-width spaces and line breaks) and MUST be at
  most 200 characters after trimming. A submission that breaks either rule MUST be refused with a
  message naming each failing sub-part, and nothing may be saved. Answers MUST be stored trimmed.
- **FR-017**: Submitting MUST be allowed only while the activity is OPEN. A submission that
  reaches the server while the activity is DRAFT MUST be refused with "The activity has not opened
  yet". One that reaches it after the activity is CLOSED MUST be refused with "The activity has
  ended".
- **FR-018**: Each group MUST have at most one submission per unit. A later attempt by any member
  of that group MUST be refused with a message saying their group has already submitted that
  question, and nothing may be saved.
- **FR-019**: The server MUST give each accepted submission a rank within its unit, in the order
  submissions reach the server: rank = 1 + the number of submissions already accepted for that
  unit. Rank 1 is the winner. Checking the phase, checking for a duplicate, assigning the rank and
  saving the submission MUST all happen in one all-or-nothing step. Each unit MUST therefore have
  ranks 1, 2, 3, … with no gaps or repeats, and exactly one winner once it has any submission,
  even when submissions arrive at the same time. Client-side times MUST NOT influence the rank.
- **FR-020**: Each accepted submission MUST record its unit, group, the participant who submitted
  it, the answer for every slot, the time the server received it, and its rank.

**Own-group view** (User Story 4)

- **FR-021**: When a submission is accepted, every connected member of that group MUST see at once
  that the unit is submitted, along with the submitted answers and the submitter's display name.
  That unit MUST become read-only for them.
- **FR-022**: A student MUST see their own group number and the display names of their own group's
  members, and nothing about the members of other groups.

**Information hiding** (Constitution Principle III)

- **FR-023**: Until the activity is CLOSED, nothing the server sends to a student client — page
  data, responses, live updates or error messages — may reveal anything about other groups'
  submissions. This includes their content, count, timing, order, rank, winner, and whether a
  unit has been submitted by anyone. It therefore also covers the student's own group's rank.
- **FR-024**: This MUST be enforced by the server. All data sent to student clients MUST pass
  through one server-side filter that decides what to send based on the activity phase and the
  receiving student's group.
- **FR-025**: After the activity is CLOSED, a student MUST see the closed state with their own
  group's submissions. Showing other groups' results and ranks to students is feature 003.

**Teacher dashboard**

- **FR-026**: The dashboard MUST list every unit in sheet order. Under each unit it MUST show the
  unit's submissions in rank order, each with its rank, group number, the submitter's display
  name, the answer for each slot (labelled （k） for a 題組), and the time the server received it.
  Rank 1 MUST be marked as the winner. A unit with no submissions MUST say so.
- **FR-027**: The dashboard MUST show each accepted submission within one second, in every
  unlocked teacher tab, without a reload.
- **FR-028**: The dashboard MUST show every group from 1 to the group count, with its members'
  display names and member count, including groups with no members. It MUST update as students
  join, leave, or change group.
- **FR-029**: After the teacher ends the activity, the dashboard MUST keep showing the final
  submissions and ranks of that activity. Returning to past activities later is part of the
  results feature (003).

**Refresh and reconnect** (Constitution Principle IV)

- **FR-030**: A client that refreshes or reconnects MUST get its current state from the server
  without any action by the user. That state is the current phase plus, for a student, their
  membership and their own group's submissions, and for the teacher, the full dashboard. While
  disconnected, the client MUST show that it is reconnecting and MUST try to reconnect
  automatically.
- **FR-031**: When there is no current activity, the student page MUST say that no activity is
  available yet, and it MUST move to the join form by itself when an activity is created
  (FR-008).

**Privacy** (Constitution Principle VI)

- **FR-032**: Display names and answer text are student data and MUST NOT be written to logs.

### Key Entities *(see [domain-class.puml](../../diagrams/domain-class.puml))*

- **Activity** (from 001): now also moves through OPEN and CLOSED. Its phase is the single source
  of truth for what every client shows and for what the server accepts. While DRAFT it can be
  cancelled, which deletes it with its questions, groups and memberships. OPEN and CLOSED
  activities are never deleted.
- **QuestionUnit / AnswerSlot** (from 001): the units students answer and the slots inside each
  unit. Unchanged by this feature.
- **Group**: one of the activity's groups, numbered 1 to the group count. Has zero or more members
  and at most one submission per unit.
- **Participant**: one student's membership in one group of one activity. Has a display name, the
  time they joined, and the private membership the student's browser keeps so that it can return
  to the group. Does not identify the student outside the activity.
- **Submission**: one group's answer to one unit. Has its rank within the unit (1 = winner), the
  time the server received it, the participant who submitted it, and one answer per slot.
- **Submission answer**: the trimmed text a submission gives for one answer slot (at most 200
  characters).
- **Teacher session** (not stored; lost on server restart): marks a browser as unlocked with the
  teacher passcode.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With 12 groups and up to 60 student screens connected, every screen shows a phase
  change, or the cancellation of a DRAFT activity, within 1 second of the teacher confirming it.
- **SC-002**: An accepted submission appears on every teacher dashboard tab, and on the screens of
  all members of the submitting group, within 1 second.
- **SC-003**: In 100 rounds where all 12 groups submit the same unit at the same moment, every
  round gives exactly one rank-1 submission and ranks 1 to 12 with no gaps or repeats.
- **SC-004**: In repeated trials of submissions sent around the moment the teacher ends the
  activity, 100% of submissions are either refused or appear in the final dashboard with a rank,
  and none is accepted after the close.
- **SC-005**: Over a full OPEN activity in which every other group submits, a recording of
  everything the server sends to one student's screen contains nothing about another group's
  submissions.
- **SC-006**: 100% of teacher actions and views requested without the passcode, including every
  feature 001 import action, are refused and return no activity or submission data.
- **SC-007**: After a refresh or a dropped connection, a student is back on the correct screen,
  with their group and their group's submitted units, within 3 seconds of the connection
  returning, without retyping anything.
- **SC-008**: A student who has never used the app can go from opening the student page to having
  joined a group in under 30 seconds, and can submit a 題組 answer without help.
- **SC-009**: Cancel requests for OPEN or CLOSED activities are refused 100% of the time, and
  after a DRAFT activity is cancelled a new import can be confirmed straight away.

## Assumptions

- The app runs on the classroom's local network only. The server must be reachable from student
  devices, but deploying it beyond that is out of scope (see Non-Goals).
- Expected scale for one class: 1 teacher (possibly several tabs), up to 12 groups, about 60
  student screens.
- Group membership is based on trust: anyone with the student page can join any group. The only
  rule enforced is that a student cannot change group after the activity opens (FR-013).
- A browser holds one student membership at a time. Several tabs of the same browser share it.
- Text a student has typed but not submitted stays on that device only. It is not shared with
  teammates and is not guaranteed to survive a refresh.
- The teacher session lasts until the server restarts. There is no "lock again" button and no
  lockout after wrong attempts, because the app runs on the local network only. Passcode checks
  never reveal how close a guess was.
- A DRAFT activity cannot be ended (DRAFT → CLOSED is not a transition). The teacher either
  re-imports into it (feature 001) or cancels it (FR-008a), which deletes it. Nothing of value
  is lost, because a DRAFT activity never has submissions.
- Times shown on the dashboard are the server's receive times, in the server's local time zone.
- Display names are limited to 20 characters, which is enough for a name or nickname.

## Non-Goals

- User accounts, logins, or student identities that last beyond one activity.
- Deployment beyond the classroom local network (hosting, internet access, HTTPS setup).
- Per-question or per-activity timers, countdowns or automatic closing.
- Grading answers for correctness, or scoring beyond rank order.
- Showing results to students, and exporting results to the sheet or to CSV (feature 003).
- Reopening a CLOSED activity, or editing or deleting submissions.
- Cancelling or deleting an OPEN or CLOSED activity. Only a DRAFT activity can be cancelled.
- Question text on student screens (it is not imported).

## Dependencies

- **Feature 001 (sheets import)**: provides the DRAFT activity, its units, slots and group count,
  the "at most one non-CLOSED activity" rule, and the teacher live channel. This feature puts
  001's recorded dependency into effect: the passcode check of FR-002 MUST cover 001's tabs,
  preview, confirm, activity view, re-import preview and re-import confirm actions. 001's refusal
  to re-import an OPEN or CLOSED activity (001 FR-026) is what makes opening final. Cancelling a
  DRAFT activity (FR-008a) frees 001's single non-CLOSED slot. 001's re-import confirm already
  refuses a missing activity, which covers a cancel that wins a race.
- **Feature 003 (results and export)**: will read this feature's submissions, ranks and answers,
  show results to students after CLOSED, and write answers to the sheet. This feature stores
  every submission's answer per slot, its rank and the server's receive time (FR-020), so that
  003 can do so. The receive time is needed for 003's CSV export.
