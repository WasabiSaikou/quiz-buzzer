# WebSocket Contract: Teacher and Student Channels (002)

Served by `api/ws_routes.py`. Connections are held by `realtime/hub.py: RealtimeHub`. Messages
are JSON text frames with a `type` field. **Every message is a complete snapshot** (research R6):
a client renders the latest one it received, and a (re)connect sends the same snapshot. No event
replay or versioning is needed (Principle IV, FR-030).

Clients send nothing. Any frame received from a client is ignored.

---

## `/ws/teacher` (extends [001's contract](../../001-sheets-import/contracts/websocket.md))

**Auth**: the `qb_teacher` cookie (research R1). If it is missing or invalid, the server accepts
and immediately closes with code **4401**, before sending any message. The client then shows the
passcode form.

### Server → client

| Message | When |
|---|---|
| `activity.state` | on connect; after create, re-import (001), open, end, cancel |
| `dashboard.state` | on connect (when a displayed activity exists); after open, end, and every join, change group and accepted submission |

`activity.state` keeps 001's summary shape. Its `activity` is now the **displayed activity**:
the current DRAFT/OPEN one, or else the most recently CLOSED one (research R7). It is `null`
after a cancel when no CLOSED activity exists, or when no activity has ever existed.

```json
{ "type": "activity.state", "activity": { "id": 7, "title": "…", "phase": "OPEN", "groupCount": 6,
  "totals": { "units": 12, "slots": 19 }, "importedAt": "2026-11-26T08:15:02Z" } }
```

```json
{ "type": "dashboard.state", "dashboard": { "...": "Dashboard shape, rest-api.md" } }
```

After a cancel the server sends `activity.state` (the displayed activity, often `null`) and no
`dashboard.state`. The client clears the dashboard whenever `activity` is `null`, or when its
`id` differs from the dashboard's `activityId`.

Several teacher tabs each get every message (FR-027).

---

## `/ws/student`

**Auth**: none required. The optional `qb_participant` cookie is resolved **once, at connect**,
to a `StudentKey (activity_id, participant_id, group_number)`, or to `None` when there is no
valid membership (research R6). After join or change group, the client closes its socket and
reconnects, so that the new cookie takes effect.

### Server → client

```json
{ "type": "student.state", "state": { "...": "StudentState shape, rest-api.md" } }
```

| Trigger | Recipients | Built by |
|---|---|---|
| connect | that socket | `ParticipationService.student_state(key)` |
| create (001), re-import (001), open, end, cancel | **every** student socket, each with its own filtered state | `publish_student_states()` |
| join, change group, accepted submission in group *g* of activity *a* | only sockets whose key has `(a, g)` | `publish_group_state(a, g)` |

Visibility guarantees (Constitution III, FR-023, FR-024):
- Each `student.state` is produced by `visibility.student_view`. That function receives only the
  activity, the recipient's own participant, and its own group's members and submissions.
- A submission by group *g* sends **nothing at all** to sockets of other groups or to sockets
  without a membership. Even the timing of a message would leak that someone submitted.
- No student message carries `rank`, `isWinner`, or any data about other groups, in any phase
  covered by 002.
- A socket whose participant no longer exists (cancelled activity, left group) receives the
  no-membership view on the next publish.

### Connection rules

- The database is the only source of truth. The server never trusts client-sent state.
- On disconnect the socket is removed from the hub. Nothing is lost.
- While disconnected, the client shows "Reconnecting…" and retries after 0.5 s, doubling each
  time up to a 5 s cap (FR-030).
