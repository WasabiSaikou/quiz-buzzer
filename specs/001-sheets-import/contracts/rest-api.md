# REST Contract: Teacher Import API (001)

Router: `src/quizbuzzer/api/teacher_routes.py`, prefix `/api/teacher`. All bodies are JSON
(UTF-8), and fields are camelCase. Every endpoint here is teacher-only. Feature 002 adds its
passcode check (`TeacherGuardMiddleware`, before routing; see 002 research R1), so this feature
defines no auth of its own.

## Error envelope (all non-2xx)

```json
{
  "error": {
    "code": "not_shared",
    "message": "This spreadsheet is not shared with the app. Share it (Viewer) with the address below.",
    "details": { "serviceAccountEmail": "quiz-buzzer@example-project.iam.gserviceaccount.com" }
  }
}
```

| HTTP | code | When |
|---|---|---|
| 400 | `invalid_url` | URL is not a Google Sheets spreadsheet link (FR-002) |
| 403 | `not_shared` | sheet not shared with service account; `details.serviceAccountEmail` (FR-004) |
| 404 | `not_found` | spreadsheet or tab does not exist (`SheetNotFound`), or the activity does not exist (`ActivityNotFound`: `GET /activities/{id}`, re-import preview, `PUT …/questions`) |
| 409 | `preview_changed` | sheet structure changed since preview; `details.preview` = new preview (FR-022) |
| 409 | `current_activity_exists` | a DRAFT/OPEN activity exists; `details.activity` = {id, title, phase} (FR-020a) |
| 409 | `reimport_refused` | activity is OPEN/CLOSED; `details.phase` (FR-026) |
| 422 | `invalid_group_count` | groupCount not in 2–12 (FR-019) |
| 422 | `import_errors` | preview has errors; `details.preview` (FR-015) |
| 422 | `warnings_not_acknowledged` | preview has warnings and `acknowledgeWarnings` is false |
| 422 | `invalid_request` | body is missing fields or has the wrong types (FastAPI validation); `details.fields` |
| 500 | `server_misconfigured` | `.env` / service-account key missing or invalid; the message names the env var, never secret contents |
| 502 | `sheets_unavailable` | Google unreachable / timeout / unexpected API error, or the Google Sheets API is not enabled for the service account's project (Google HTTP 403 with reason `SERVICE_DISABLED`; reported as unavailable, not `not_shared`, because sharing would not fix it) |

---

## POST /api/teacher/import/tabs

Lists tabs and the preselected one (FR-003).

Request:
```json
{ "url": "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOp/edit#gid=918273645" }
```

Response 200:
```json
{
  "spreadsheetId": "1AbCdEfGhIjKlMnOp",
  "spreadsheetTitle": "Ch3 Guided Notes",
  "tabs": [
    { "sheetId": 0, "title": "講義", "index": 0 },
    { "sheetId": 918273645, "title": "練習", "index": 1 }
  ],
  "preselectedSheetId": 918273645
}
```

`preselectedSheetId` is the `#gid=` tab if it exists, otherwise the tab with index 0.

## POST /api/teacher/import/preview

Request:
```json
{ "url": "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOp/edit", "sheetId": 0 }
```

Response 200 (a preview is returned even when it contains errors):
```json
{
  "spreadsheetId": "1AbCdEfGhIjKlMnOp",
  "spreadsheetTitle": "Ch3 Guided Notes",
  "sheetId": 0,
  "tabTitle": "講義",
  "header": { "row": 3, "numberColumn": 1, "answerColumn": 4 },
  "units": [
    {
      "number": 1, "kind": "SINGLE", "sourceRow": 4,
      "slots": [ { "subPart": 1, "a1Ref": "D4", "row": 4, "column": 4 } ]
    },
    {
      "number": 2, "kind": "GROUP_SET", "sourceRow": 6,
      "slots": [
        { "subPart": 1, "a1Ref": "D6", "row": 6, "column": 4 },
        { "subPart": 2, "a1Ref": "D7", "row": 7, "column": 4 },
        { "subPart": 3, "a1Ref": "D8", "row": 8, "column": 4 }
      ]
    }
  ],
  "issues": [
    {
      "severity": "warning",
      "code": "slot_cell_has_text",
      "message": "D7 already contains \"（2）______\". Export will replace the whole cell.",
      "cells": ["D7"],
      "rows": [7]
    },
    {
      "severity": "warning",
      "code": "unrecognised_question_number",
      "message": "Row 10: 題號 cell \"備註\" is not a question number and was skipped.",
      "cells": ["A10"],
      "rows": [10]
    }
  ],
  "totals": { "units": 2, "slots": 4, "errors": 0, "warnings": 2 },
  "fingerprint": "9f2c…e41a",
  "canConfirm": true
}
```

## POST /api/teacher/activities

Creates the DRAFT activity (FR-019 – FR-023, FR-020a).

Request:
```json
{
  "url": "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOp/edit",
  "sheetId": 0,
  "groupCount": 6,
  "fingerprint": "9f2c…e41a",
  "acknowledgeWarnings": true
}
```

Response 201: an `Activity` (see below).

## GET /api/teacher/activities/current

Response 200: `{ "activity": Activity }`, or `{ "activity": null }` when there is no DRAFT or
OPEN activity.

**Changed by feature 002** ([002 research R7](../../002-live-buzz-activity/research.md#r7-teacher-view-after-end-fr-029),
[002 contract](../../002-live-buzz-activity/contracts/rest-api.md#change-to-001-get-apiteacheractivitiescurrent-research-r7)):
this endpoint returns the teacher's *displayed* activity:
1. the DRAFT/OPEN activity, if one exists;
2. otherwise the most recently CLOSED activity (`"phase": "CLOSED"`), so that the final dashboard
   survives a refresh after End;
3. otherwise `{ "activity": null }`.

A CLOSED activity returned here **does not block** creating a new one. `POST /activities` is
refused (409 `current_activity_exists`) only while a DRAFT or OPEN activity exists (FR-020a).
Until 002 is implemented, case 2 returns `null`.

## GET /api/teacher/activities/{id}

Response 200: `Activity`. Returns 404 `not_found` if the activity does not exist (service
exception `ActivityNotFound`).

## POST /api/teacher/activities/{id}/reimport/preview

Request is the same as `/import/preview`. Response 200 is the same preview shape. Returns 409
`reimport_refused` if the activity is not DRAFT, and 404 `not_found` (`ActivityNotFound`) if it
does not exist.

## PUT /api/teacher/activities/{id}/questions

Replaces the question set (FR-024 – FR-026).

Request:
```json
{
  "url": "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOp/edit",
  "sheetId": 918273645,
  "fingerprint": "77b0…0c3d",
  "acknowledgeWarnings": false
}
```

Response 200: the updated `Activity` (phase and groupCount unchanged). Errors: 409 `reimport_refused` (phase re-checked at confirm time), 409 `preview_changed`, 422 `import_errors`, 422 `warnings_not_acknowledged`, 404 `not_found`.

---

## Activity (response shape)

```json
{
  "id": 7,
  "title": "Ch3 Guided Notes – 講義",
  "phase": "DRAFT",
  "groupCount": 6,
  "source": { "spreadsheetId": "1AbCdEfGhIjKlMnOp", "sheetId": 0, "tabTitle": "講義" },
  "createdAt": "2026-11-26T08:15:02Z",
  "importedAt": "2026-11-26T08:15:02Z",
  "units": [
    {
      "id": 31, "number": 1, "kind": "SINGLE", "sourceRow": 4, "position": 0,
      "slots": [ { "id": 88, "subPart": 1, "a1Ref": "D4", "row": 4, "column": 4 } ]
    }
  ],
  "totals": { "units": 1, "slots": 1 }
}
```
