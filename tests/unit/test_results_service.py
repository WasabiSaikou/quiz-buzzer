"""Results model and read side, tests first (003 T005; data-model.md › ResultEntry, UnitResult,
ActivityResults; contracts/rest-api.md › TeacherResults)."""

from __future__ import annotations

import pytest

from quizbuzzer.models import Phase, UnitKind
from quizbuzzer.services.activity_service import ActivityNotFound, PhaseConflict
from quizbuzzer.services.results_service import ResultsService, build_results, results_out
from tests.live_helpers import init_schema, make_activity, run_activity

# live sheet: unit 1 is a 題組 (1)(2); units 2..n are single questions.
PLAYS = [
    (2, 4, ["四"]),
    (1, 3),
    (2, 1, ["一"]),
    (2, 6, ["六"]),
]


@pytest.fixture
def closed(fake_adapter, db_path):
    activity, _part, _tokens = run_activity(fake_adapter, db_path, PLAYS, n_units=4)
    return activity


def test_teacher_results_units_in_sheet_order_entries_in_rank_order(db_path, closed):
    results = ResultsService(db_path).teacher_results(closed.id)
    assert results.activity_id == closed.id
    assert results.phase is Phase.CLOSED
    assert [u.number for u in results.units] == [1, 2, 3, 4]
    unit2 = results.units[1]
    assert [(e.rank, e.group_number) for e in unit2.entries] == [(1, 4), (2, 1), (3, 6)]
    assert [e.answers for e in unit2.entries] == [((1, "四"),), ((1, "一"),), ((1, "六"),)]
    assert unit2.winner.group_number == 4
    assert [e.is_winner for e in unit2.entries] == [True, False, False]


def test_unit_without_submission_has_no_answer(db_path, closed):
    results = ResultsService(db_path).teacher_results(closed.id)
    unit3 = results.units[2]
    assert unit3.entries == ()
    assert unit3.no_answer is True
    assert unit3.winner is None


def test_group_set_answers_in_sub_part_order_with_teacher_fields(db_path, closed):
    results = ResultsService(db_path).teacher_results(closed.id)
    unit1 = results.units[0]
    assert unit1.kind is UnitKind.GROUP_SET
    assert unit1.sub_parts == (1, 2)
    (entry,) = unit1.entries
    assert entry.answers == ((1, "ans-1-1"), (2, "ans-1-2"))
    assert entry.submitted_by == "名3"
    assert entry.received_at.endswith("Z")


def test_unknown_activity_raises_not_found(db_path, closed):
    with pytest.raises(ActivityNotFound):
        ResultsService(db_path).teacher_results(closed.id + 100)


@pytest.mark.parametrize("phase", ["DRAFT", "OPEN"])
def test_results_refused_before_closed(fake_adapter, db_path, phase):
    init_schema(db_path)
    activity = make_activity(fake_adapter, db_path, phase=phase)
    with pytest.raises(PhaseConflict) as info:
        ResultsService(db_path).teacher_results(activity.id)
    assert info.value.action == "results"
    assert info.value.phase is Phase(phase)
    assert str(info.value) == (
        f"Results are available once the activity is CLOSED; it is {phase}."
    )


@pytest.mark.parametrize(
    "action, verb",
    [("export", "cannot be exported"), ("csv", "cannot be downloaded")],
)
def test_phase_conflict_messages_for_export_and_csv(action, verb):
    exc = PhaseConflict(1, Phase.OPEN, action)
    assert str(exc) == f"The results {verb} until the activity is CLOSED; it is OPEN."


def test_results_for_skips_the_phase_check(db_path, closed):
    svc = ResultsService(db_path)
    assert svc.results_for(closed) == svc.teacher_results(closed.id)


def test_build_results_is_pure_and_handles_no_submissions(fake_adapter, db_path):
    init_schema(db_path)
    activity = make_activity(fake_adapter, db_path, phase="CLOSED")
    results = build_results(activity, [])
    assert [u.no_answer for u in results.units] == [True] * len(activity.units)
    assert results.title == activity.title


def test_results_out_matches_contract_shape(db_path, closed):
    out = results_out(ResultsService(db_path).teacher_results(closed.id))
    assert set(out) == {"activityId", "title", "phase", "groupCount", "units"}
    assert out["phase"] == "CLOSED"
    unit1, unit2, unit3, _ = out["units"]
    assert unit1["kind"] == "GROUP_SET" and unit1["subParts"] == [1, 2]
    assert set(unit2) == {"unitId", "number", "kind", "subParts", "submissions"}
    first = unit2["submissions"][0]
    assert set(first) == {"rank", "isWinner", "groupNumber", "submittedBy", "receivedAt", "answers"}
    assert first["rank"] == 1 and first["isWinner"] is True and first["groupNumber"] == 4
    assert first["answers"] == [{"subPart": 1, "text": "四"}]
    assert unit3["submissions"] == []
