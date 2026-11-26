# WebSocket Contract: Teacher Channel (001)

Endpoint: `GET /ws/teacher` (WebSocket upgrade), served by `src/quizbuzzer/api/ws_routes.py`;
connections are managed by `realtime/hub.py: RealtimeHub`. Teacher-only (feature 002's passcode
check applies to the upgrade). Messages are JSON text frames with a `type` field.

Student sockets (`/ws/student`) and their visibility-filtered messages (Principle III) are
defined by the student-facing features, not here.

## Server → client

### `activity.state`

Sent (a) immediately after connect — so a reconnecting client recovers state (Principle IV) —
and (b) to every teacher socket after an activity is created or its questions are replaced.

```json
{
  "type": "activity.state",
  "activity": {
    "id": 7,
    "title": "Ch3 Guided Notes – 講義",
    "phase": "DRAFT",
    "groupCount": 6,
    "totals": { "units": 12, "slots": 19 },
    "importedAt": "2026-11-26T08:15:02Z"
  }
}
```

When there is no current (DRAFT/OPEN) activity:

```json
{ "type": "activity.state", "activity": null }
```

The message carries a summary only; clients fetch full detail with
`GET /api/teacher/activities/{id}`.

**Changed by feature 002** ([002 websocket contract](../../002-live-buzz-activity/contracts/websocket.md)):
`activity` is the teacher's *displayed* activity. That is the DRAFT/OPEN one, otherwise the most
recently CLOSED one, otherwise `null`, as for `GET /api/teacher/activities/current`. A CLOSED
activity shown here never blocks a new import. 002 also adds `dashboard.state` and requires the
teacher cookie on connect.

## Client → server

None in this feature. Any frame received is ignored. Unknown `type` values are reserved for
later features.

## Connection rules

- The server never trusts client-sent state. Phase always comes from the database at send time.
- On disconnect the socket is removed from the hub; no state is lost because the database is the
  source of truth.
