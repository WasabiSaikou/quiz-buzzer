"""The visibility filter: the only function that shapes data sent to students (Constitution III).

`student_view` is pure: no DB, no I/O. It is handed only the activity, the recipient's own
participant, its own group's members and its own group's submissions, and it emits exactly
contracts/rest-api.md › StudentState. It never emits rank, winner flags, counts, or another
group's number, members or submissions, in any phase (FR-015, FR-022 – FR-025). As a second
line of defence it drops any submission that is not the recipient's own group's.

Feature 003 (FR-002, FR-003): the one exception is `results`, added only for a member of a
CLOSED activity. The filter re-checks the phase, the membership and the results' activity
itself, so results passed in by mistake before CLOSED are dropped, and it strips submitter
names and receive times from every entry.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from quizbuzzer.models import Activity, ActivityResults, Participant, Phase, Submission


def _activity_summary(activity: Activity, *, with_units: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": activity.id,
        "phase": activity.phase.value,
        "groupCount": activity.group_count,
    }
    if with_units and activity.phase is Phase.OPEN:  # members only, while answering (FR-015)
        out["units"] = [
            {
                "unitId": u.id,
                "number": u.number,
                "kind": u.kind.value,
                "subParts": [s.sub_part for s in sorted(u.slots, key=lambda s: s.sub_part)],
            }
            for u in sorted(activity.units, key=lambda u: u.position)
        ]
    return out


def _submission_out(s: Submission) -> dict[str, Any]:
    # Deliberately no rank / is_winner / group_number (FR-023).
    return {
        "unitId": s.unit_id,
        "unitNumber": s.unit_number,
        "submittedBy": s.submitted_by,
        "receivedAt": s.received_at,
        "answers": [
            {"subPart": a.sub_part, "text": a.text}
            for a in sorted(s.answers, key=lambda a: a.sub_part)
        ],
    }


def student_view(
    activity: Activity | None,
    participant: Participant | None,
    members: Sequence[str],
    own_submissions: Sequence[Submission],
    *,
    results: ActivityResults | None = None,
) -> dict[str, Any]:
    """StudentState for one recipient (contracts/rest-api.md › StudentState › Rules)."""
    if activity is None:
        return {"activity": None, "membership": None, "group": None}
    if participant is None or participant.activity_id != activity.id:
        return {
            "activity": _activity_summary(activity, with_units=False),
            "membership": None,
            "group": None,
        }
    own = [s for s in own_submissions if s.group_number == participant.group_number]
    if activity.phase is Phase.DRAFT:
        own = []
    view = {
        "activity": _activity_summary(activity, with_units=True),
        "membership": {
            "groupNumber": participant.group_number,
            "displayName": participant.display_name,
        },
        "group": {
            "members": list(members),
            "submissions": [_submission_out(s) for s in sorted(own, key=_unit_order(activity))],
        },
    }
    if (
        results is not None
        and activity.phase is Phase.CLOSED
        and results.activity_id == activity.id
    ):
        view["results"] = _student_results(results)
    return view


def _student_results(results: ActivityResults) -> dict[str, Any]:
    """003 contracts › StudentState `results`: entries without submittedBy / receivedAt."""
    return {
        "units": [
            {
                "unitId": u.unit_id,
                "number": u.number,
                "kind": u.kind.value,
                "subParts": list(u.sub_parts),
                "submissions": [
                    {
                        "rank": e.rank,
                        "isWinner": e.is_winner,
                        "groupNumber": e.group_number,
                        "answers": [{"subPart": k, "text": t} for k, t in e.answers],
                    }
                    for e in u.entries
                ],
            }
            for u in results.units
        ]
    }


def _unit_order(activity: Activity):
    positions = {u.id: u.position for u in activity.units}
    return lambda s: (positions.get(s.unit_id, 1 << 30), s.unit_number)
