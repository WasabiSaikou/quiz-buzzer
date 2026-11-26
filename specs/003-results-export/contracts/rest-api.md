# REST Contract: Results, Export and CSV (003)

Conventions as in [002](../../002-live-buzz-activity/contracts/rest-api.md): JSON (UTF-8),
camelCase, the 001 error envelope `{error: {code, message, details?}}`. Every route below is
under `/api/teacher/` and therefore behind `TeacherGuardMiddleware` (401 `teacher_required`, no
data, FR-020).

Common refusals for `{id}` routes:

| Situation | Status | Code | Details |
|---|---|---|---|
| no such activity | 404 | `not_found` | — |
| activity is DRAFT or OPEN | 409 | `phase_conflict` | `{phase}`; message "Results are available once the activity is CLOSED; it is <phase>." (export: "…cannot be exported until…"; CSV: "…cannot be downloaded until…") |

---

## GET /api/teacher/activities/closed (FR-023)

Declared before `/activities/{activity_id}`.

**200**

```json
{
  "activities": [
    { "id": 9, "title": "學習單 – 練習", "createdAt": "2026-11-27T02:00:00Z",
      "groupCount": 6, "unitCount": 5, "submissionCount": 14 }
  ]
}
```

Newest first. DRAFT and OPEN activities never appear. Empty list when none.

## GET /api/teacher/activities/{id}/results (FR-001, FR-005)

**200** `TeacherResults`:

```json
{
  "activityId": 9, "title": "學習單 – 練習", "phase": "CLOSED", "groupCount": 6,
  "units": [
    {
      "unitId": 31, "number": 3, "kind": "GROUP_SET", "subParts": [1, 2],
      "submissions": [
        { "rank": 1, "isWinner": true, "groupNumber": 4,
          "submittedBy": "小華", "receivedAt": "2026-11-27T02:14:09.512Z",
          "answers": [ {"subPart": 1, "text": "…"}, {"subPart": 2, "text": "…"} ] }
      ]
    },
    { "unitId": 32, "number": 4, "kind": "SINGLE", "subParts": [1], "submissions": [] }
  ]
}
```

Units in sheet order, submissions in rank order. The winner is `submissions[0]` when present;
an empty list means 無人作答.

## POST /api/teacher/activities/{id}/export (FR-006 – FR-013)

No body.

**200** `ExportReport`:

```json
{ "cellsWritten": 3, "unitsWritten": 2, "unitsSkipped": 1 }
```

With zero winners: `{"cellsWritten": 0, "unitsWritten": 0, "unitsSkipped": <all units>}` and no
Google call.

| Failure | Status | Code | Details |
|---|---|---|---|
| sheet now has detection errors, or a winning question / sub-part is missing | 409 | `export_blocked` | `{problems: [{kind, questionNumber, subPart, code, message}]}` — every problem listed; **nothing written** |
| sheet cannot be read (not shared) | 403 | `export_not_shared` | `{serviceAccountEmail}`; message asks to share the sheet with that address as an **Editor** |
| write refused (view-only) | 403 | `sheet_read_only` | `{serviceAccountEmail}`; message asks to give that address **Editor** access |
| spreadsheet or tab (by sheetId) gone | 404 | `not_found` | — |
| Google unreachable / unexpected error / API not enabled | 502 | `sheets_unavailable` | — |
| credentials not configured | 500 | `server_misconfigured` | — |

`kind` values: `parse_error` (with the 001 `code`), `missing_question` (`questionNumber`),
`missing_sub_part` (`questionNumber`, `subPart`).

## GET /api/teacher/activities/{id}/results.csv (FR-015 – FR-019)

**200** `text/csv; charset=utf-8`,
`Content-Disposition: attachment; filename="activity-<id>.csv"; filename*=UTF-8''<encoded
activity-<id>-<safe title>.csv>`.

Body: UTF-8 with BOM, CRLF line endings, header
`question_no,sub_part,group,answer,rank,is_winner,submitted_at`, one row per answer slot of every
submission (unit sheet order → rank → sub-part). `sub_part` empty for single questions;
`is_winner` `true`/`false`; `submitted_at` like `2026-11-27T02:14:09.512+00:00`. Fields with
`,` `"` CR or LF are quoted (inner `"` doubled). Answers starting with `=` `+` `-` `@` are
prefixed with `'`.

---

## Change to 002: StudentState gains `results` (FR-002 – FR-004)

`GET /api/student/state` and the `/ws/student` `student.state` push are unchanged except for one
row of 002's rules table:

| Situation | `activity` | `membership` | `group` | `results` |
|---|---|---|---|---|
| member of the latest CLOSED activity, no current activity | `{id, phase: "CLOSED", groupCount}` | set | `members` + own `submissions` | **present** |
| every other situation (incl. a browser with no membership of the CLOSED activity) | as in 002 | as in 002 | as in 002 | **absent** |

```json
"results": {
  "units": [
    { "unitId": 31, "number": 3, "kind": "GROUP_SET", "subParts": [1, 2],
      "submissions": [
        { "rank": 1, "isWinner": true, "groupNumber": 4,
          "answers": [ {"subPart": 1, "text": "…"}, {"subPart": 2, "text": "…"} ] }
      ] },
    { "unitId": 32, "number": 4, "kind": "SINGLE", "subParts": [1], "submissions": [] }
  ]
}
```

Student entries never carry `submittedBy` or `receivedAt` (FR-003). Before CLOSED, 002's rule
still holds: no key carries `rank`, `isWinner`, another group's number or data.
