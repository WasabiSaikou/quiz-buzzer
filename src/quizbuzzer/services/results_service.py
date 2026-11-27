"""ResultsService: results of CLOSED activities (diagrams/003-seq-view-results.puml).

Read only (003 FR-022). `build_results` is pure; the service reads 001/002 rows and enforces the
CLOSED-only rule for teacher requests. Students never call it directly: ParticipationService
asks `results_for` only after checking CLOSED, and the visibility filter re-checks (research R5).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from quizbuzzer import db
from quizbuzzer.models import (
    Activity,
    ActivityResults,
    Phase,
    ResultEntry,
    Submission,
    UnitResult,
)
from quizbuzzer.services.activity_service import ActivityNotFound, PhaseConflict


def build_results(activity: Activity, submissions: Sequence[Submission]) -> ActivityResults:
    """Pure: units in sheet order (ActivityResults.units), entries in rank order (UnitResult.entries)."""
    by_unit: dict[int, list[Submission]] = {}
    for s in submissions:
        by_unit.setdefault(s.unit_id, []).append(s)
    units = tuple(
        UnitResult(
            unit_id=u.id,
            number=u.number,
            kind=u.kind,
            sub_parts=tuple(sorted(sl.sub_part for sl in u.slots)),
            entries=tuple(
                ResultEntry(
                    rank=s.rank,
                    group_number=s.group_number,
                    answers=tuple(
                        (a.sub_part, a.text) for a in sorted(s.answers, key=lambda a: a.sub_part)
                    ),
                    submitted_by=s.submitted_by,
                    received_at=s.received_at,
                )
                for s in sorted(by_unit.get(u.id, []), key=lambda s: s.rank)
            ),
        )
        for u in sorted(activity.units, key=lambda u: u.position)
    )
    return ActivityResults(
        activity_id=activity.id,
        title=activity.title,
        phase=activity.phase,
        group_count=activity.group_count,
        units=units,
    )


def entry_out(entry: ResultEntry, *, teacher: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "rank": entry.rank,
        "isWinner": entry.is_winner,
        "groupNumber": entry.group_number,
    }
    if teacher:  # data-model.md › ResultEntry.submitted_by / received_at: teacher only
        out["submittedBy"] = entry.submitted_by
        out["receivedAt"] = entry.received_at
    out["answers"] = [{"subPart": k, "text": t} for k, t in entry.answers]
    return out


def units_out(results: ActivityResults, *, teacher: bool) -> list[dict[str, Any]]:
    return [
        {
            "unitId": u.unit_id,
            "number": u.number,
            "kind": u.kind.value,
            "subParts": list(u.sub_parts),
            "submissions": [entry_out(e, teacher=teacher) for e in u.entries],
        }
        for u in results.units
    ]


def results_out(results: ActivityResults) -> dict[str, Any]:
    """contracts/rest-api.md › TeacherResults."""
    return {
        "activityId": results.activity_id,
        "title": results.title,
        "phase": results.phase.value,
        "groupCount": results.group_count,
        "units": units_out(results, teacher=True),
    }


class ResultsService:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def teacher_results(self, activity_id: int, action: str = "results") -> ActivityResults:
        """Results of a CLOSED activity; ActivityNotFound / PhaseConflict(action) otherwise."""
        return self.load(activity_id, action)[1]

    def load(self, activity_id: int, action: str = "results") -> tuple[Activity, ActivityResults]:
        """The CLOSED activity (with units and slots) and its results, read in one connection."""
        conn = db.connect(self.db_path)
        try:
            activity = db.get_activity_with_units(conn, activity_id)
            if activity is None:
                raise ActivityNotFound(activity_id)
            if activity.phase is not Phase.CLOSED:
                raise PhaseConflict(activity_id, activity.phase, action)
            return activity, build_results(activity, db.list_dashboard_submissions(conn, activity_id))
        finally:
            conn.close()

    def results_for(self, activity: Activity) -> ActivityResults:
        """No phase check: the caller (ParticipationService) has already checked CLOSED."""
        conn = db.connect(self.db_path)
        try:
            return build_results(activity, db.list_dashboard_submissions(conn, activity.id))
        finally:
            conn.close()
