# REST Contract: Live Activity API (002)

All bodies are JSON (UTF-8), and fields are camelCase. Every non-2xx response uses
[001's error envelope](../../001-sheets-import/contracts/rest-api.md#error-envelope-all-non-2xx)
`{error: {code, message, details?}}`. Student-facing messages never contain other groups' data
(FR-023).

Routers:
- `api/auth_routes.py`: `/api/teacher/session`. This is the only `/api/teacher/*` route without
  the teacher guard.
- `api/teacher_routes.py`: prefix `/api/teacher`. Every request under `/api/teacher/` except
  `POST /api/teacher/session` first passes `TeacherGuardMiddleware` (`api/auth.py`), before
  routing and body parsing.
- `api/student_routes.py`: prefix `/api/student`.

Cookies (research R1, R2):

| Cookie | Set by | Attributes |
|---|---|---|
| `qb_teacher` | `POST /api/teacher/session` | HttpOnly; SameSite=Strict; Path=/; session cookie (no Max-Age) |
| `qb_participant` | `POST /api/student/join` | HttpOnly; SameSite=Strict; Path=/; Max-Age=43200 |

---

## Teacher access (FR-001 – FR-004)

### POST /api/teacher/session

Request: `{ "passcode": "…" }`

- **204**: unlocked. `Set-Cookie: qb_teacher=…`.
- **401** `wrong_passcode`: "Wrong passcode." There are no `details`, and the message is the
  same however close the guess was.
- **422** `invalid_request`: the body is missing or not a string.

The passcode is never echoed, logged or stored (FR-004).

### Guard on every other `/api/teacher/*` route (FR-002)

Without a valid `qb_teacher` cookie, **every** route below **and every 001 route**
(`/import/tabs`, `/import/preview`, `POST /activities`, `GET /activities/current`,
`GET /activities/{id}`, `/activities/{id}/reimport/preview`, `PUT /activities/{id}/questions`)
returns:

```json
{ "error": { "code": "teacher_required", "message": "Teacher passcode required." } }
```

with status **401** and no `details`. The guard runs before body validation, so a request with a
bad body and no cookie also gets 401, never a 422 that echoes field names.

---

## Teacher activity control

### POST /api/teacher/activities/{id}/open (FR-005 – FR-007)

No body. **200**: `Activity` (001 shape) with `"phase": "OPEN"`.

| Status | code | When |
|---|---|---|
| 404 | `not_found` | no such activity (e.g. cancelled in another tab) |
| 409 | `phase_conflict` | phase is OPEN or CLOSED; `details.phase`; message "The activity is already OPEN." / "… is CLOSED." |

### POST /api/teacher/activities/{id}/end

No body. **200**: `Activity` with `"phase": "CLOSED"`.

| Status | code | When |
|---|---|---|
| 404 | `not_found` | no such activity |
| 409 | `phase_conflict` | phase is DRAFT, with the message "A DRAFT activity cannot be ended. Use Cancel activity instead.", or phase is CLOSED; `details.phase` |

### DELETE /api/teacher/activities/{id} (FR-008a – FR-008c)

Cancels a DRAFT activity. No body. **204**: deleted (units, slots and participants cascade).

| Status | code | When |
|---|---|---|
| 404 | `not_found` | no such activity |
| 409 | `cancel_refused` | phase is OPEN, with the message "An OPEN activity can only be ended.", or phase is CLOSED, with the message "A CLOSED activity is kept and cannot be cancelled."; `details.phase` |

### GET /api/teacher/activities/{id}/dashboard (FR-026 – FR-029)

**200**: a `Dashboard` (shape below), also pushed as `dashboard.state`. Available in every
phase, including CLOSED. Returns 404 `not_found` if there is no such activity.

### Change to 001: GET /api/teacher/activities/current (research R7)

Returns the current (DRAFT/OPEN) activity. If there is none, it returns the **most recently
CLOSED** activity, so that the final dashboard survives a refresh (FR-029). If no activity has
ever existed, it returns `{"activity": null}` as before.

This is for display only. `POST /api/teacher/activities` (001) is still refused only while a
DRAFT or OPEN activity exists. A CLOSED activity returned here never causes
`current_activity_exists`.

---

## Student API

The student is identified only by the `qb_participant` cookie (FR-014). No student request
accepts an activity's group number except `join`.

### GET /api/student/state (FR-012, FR-030, FR-031)

**200**: a `StudentState` (shape below). This is the same object `/ws/student` pushes as
`student.state`, and it is built by `visibility.student_view`.

### POST /api/student/join (FR-009 – FR-011)

Request:
```json
{ "activityId": 7, "groupNumber": 3, "displayName": "小明" }
```

`activityId` guards against joining a different activity than the one on screen (for example,
after a cancel and a new import).

- **201**: `StudentState` (with `membership`). `Set-Cookie: qb_participant=…`.

| Status | code | When |
|---|---|---|
| 422 | `invalid_join` | the name is empty or more than 20 characters after trimming, or the group is not in 1..groupCount; `details.field` = `displayName` / `groupNumber`, plus `details.max` |
| 409 | `join_refused` | there is no current activity, `activityId` is not the current activity, or the phase is CLOSED; `details.phase` (null if none) |
| 409 | `already_joined` | the cookie already holds a membership of this activity. The UI offers "Change group" (DRAFT) instead |

### DELETE /api/student/membership (FR-013)

No body. **204**: the participant is deleted and the cookie is cleared.

| Status | code | When |
|---|---|---|
| 401 | `not_a_member` | the cookie is missing, unknown, or belongs to a different activity |
| 409 | `group_change_refused` | phase is OPEN or CLOSED. The message is "Groups are fixed once the activity has opened."; `details.phase` |

### POST /api/student/submissions (FR-015 – FR-020)

Request:
```json
{ "unitId": 31, "answers": [ { "subPart": 1, "text": "光合作用" }, { "subPart": 2, "text": "葉綠體" } ] }
```

**201**:
```json
{
  "unitId": 31,
  "unitNumber": 3,
  "answers": [ { "subPart": 1, "text": "光合作用" }, { "subPart": 2, "text": "葉綠體" } ],
  "submittedBy": "小明",
  "receivedAt": "2026-11-27T02:14:09.512Z"
}
```

The response has **no `rank` field and no `isWinner` field**, and none appears anywhere in
student responses (FR-023).

Errors, in this check order (research R3):

| Status | code | When |
|---|---|---|
| 422 | `invalid_answers` | an answer is empty or whitespace-only, or longer than 200 characters after trimming; or the `subPart` set is not exactly the unit's slots. `details.subParts` = the failing k's, and `details.reasons` = `{k: "empty" \| "too_long" \| "unknown" \| "missing" \| "duplicate"}`. Message example: "Answer （2） is empty." |
| 401 | `not_a_member` | the cookie is missing, unknown, or of another activity. The UI returns to the join form |
| 409 | `not_open` | phase is DRAFT: "The activity has not opened yet." |
| 409 | `activity_ended` | phase is CLOSED: "The activity has ended." |
| 404 | `unit_not_found` | the unit is not in the student's activity |
| 409 | `already_submitted` | the group already has a submission for this unit: "Your group has already submitted question 3." `details.submission` = **the group's own** submission, in the 201 shape above |

Empty-text and length checks run before the transaction. The `subPart`-set check runs inside it,
after the phase check, because it needs the unit's slots.

---

## Shapes

### Dashboard (teacher only)

```json
{
  "activityId": 7,
  "phase": "OPEN",
  "groupCount": 6,
  "units": [
    {
      "unitId": 31, "number": 3, "kind": "GROUP_SET", "subParts": [1, 2],
      "submissions": [
        {
          "rank": 1, "isWinner": true, "groupNumber": 4, "submittedBy": "小華",
          "receivedAt": "2026-11-27T02:14:09.512Z",
          "answers": [ { "subPart": 1, "text": "…" }, { "subPart": 2, "text": "…" } ]
        }
      ]
    },
    { "unitId": 32, "number": 4, "kind": "SINGLE", "subParts": [1], "submissions": [] }
  ],
  "groups": [
    { "number": 1, "members": ["小明", "小明"], "memberCount": 2 },
    { "number": 2, "members": [], "memberCount": 0 }
  ]
}
```

- Units are listed in sheet order (`position`), and submissions in rank order.
- `groups` always lists 1..groupCount (FR-028).
- Members are listed in join order. Display names may repeat.

### StudentState (built only by `visibility.student_view`)

```json
{
  "activity": {
    "id": 7,
    "phase": "OPEN",
    "groupCount": 6,
    "units": [
      { "unitId": 31, "number": 3, "kind": "GROUP_SET", "subParts": [1, 2] },
      { "unitId": 32, "number": 4, "kind": "SINGLE", "subParts": [1] }
    ]
  },
  "membership": { "groupNumber": 3, "displayName": "小明" },
  "group": {
    "members": ["小明", "阿美"],
    "submissions": [
      {
        "unitId": 31, "unitNumber": 3, "submittedBy": "阿美",
        "receivedAt": "2026-11-27T02:14:09.512Z",
        "answers": [ { "subPart": 1, "text": "…" }, { "subPart": 2, "text": "…" } ]
      }
    ]
  }
}
```

Rules (FR-015, FR-022 – FR-025):

| Situation | `activity` | `activity.units` | `membership` | `group` |
|---|---|---|---|---|
| no current activity and no membership of a CLOSED one | `null` | — | `null` | `null` |
| current activity, no valid membership | `{id, phase, groupCount}` | omitted | `null` | `null` |
| member, DRAFT | `{id, phase: "DRAFT", groupCount}` | omitted | set | `members`, `submissions: []` |
| member, OPEN | full | present | set | `members` + own `submissions` |
| member of the latest CLOSED activity, no current activity | `{id, phase: "CLOSED", groupCount}` | omitted | set | `members` + own `submissions` |

The object never has a key carrying `rank`, `isWinner`, another group's number, other groups'
members, or any count of submissions beyond the student's own group's list.

### Activity

As in 001, unchanged. `phase` can now be `OPEN` or `CLOSED`.
