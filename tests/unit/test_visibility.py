"""visibility.student_view: the only builder of student-bound state (Constitution III).

Pure function tests: no DB. Rules: contracts/rest-api.md › StudentState (FR-015, FR-022–FR-025).
"""

from __future__ import annotations

import pytest

from quizbuzzer.models import (
    Activity,
    AnswerSlot,
    Participant,
    Phase,
    QuestionUnit,
    Submission,
    SubmissionAnswer,
    UnitKind,
)
from quizbuzzer.services.visibility import student_view

FORBIDDEN_KEYS = {"rank", "isWinner", "is_winner", "count", "total", "totals", "title", "source"}


def slot(i, k):
    return AnswerSlot(id=i, sub_part=k, cell_row=i, cell_column=4, a1_ref=f"D{i}")


def make_activity(phase, activity_id=7):
    units = (
        # Deliberately out of position order: the view must sort by position.
        QuestionUnit(id=32, number=4, kind=UnitKind.SINGLE, source_row=9, position=1,
                     slots=(slot(90, 1),)),
        QuestionUnit(id=31, number=3, kind=UnitKind.GROUP_SET, source_row=5, position=0,
                     slots=(slot(88, 1), slot(89, 2))),
    )
    return Activity(
        id=activity_id, title="Book – Tab", phase=phase, group_count=6,
        source_spreadsheet_id="sid", source_sheet_id=0, source_tab_title="Tab",
        created_at="2026-11-27T01:00:00Z", imported_at="2026-11-27T01:00:00Z", units=units,
    )


def make_participant(group=3, activity_id=7, pid=11, name="小明"):
    return Participant(id=pid, activity_id=activity_id, group_number=group, display_name=name,
                       joined_at="2026-11-27T01:01:00Z")


def make_submission(group=3, rank=2, unit_id=31, unit_number=3, by="阿美", sid=100):
    return Submission(
        id=sid, unit_id=unit_id, unit_number=unit_number, group_number=group, participant_id=12,
        submitted_by=by, rank=rank, received_at="2026-11-27T02:14:09.512Z",
        answers=(SubmissionAnswer(slot_id=88, sub_part=1, text="光合作用"),
                 SubmissionAnswer(slot_id=89, sub_part=2, text="葉綠體")),
    )


def walk(obj, path=()):
    """Yield (path, key) for every dict key in a nested structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path, k
            yield from walk(v, path + (k,))
    elif isinstance(obj, list | tuple):
        for v in obj:
            yield from walk(v, path)


def assert_no_forbidden_keys(view):
    for path, key in walk(view):
        assert key not in FORBIDDEN_KEYS, (path, key)
        if key == "groupNumber":
            assert path == ("membership",), path


def test_no_current_activity():
    view = student_view(None, None, [], [])
    assert view == {"activity": None, "membership": None, "group": None}


@pytest.mark.parametrize("phase", [Phase.DRAFT, Phase.OPEN])
def test_current_activity_without_membership(phase):
    view = student_view(make_activity(phase), None, ["x"], [make_submission()])
    assert view == {
        "activity": {"id": 7, "phase": phase.value, "groupCount": 6},
        "membership": None,
        "group": None,
    }


def test_member_in_draft_sees_waiting_state_without_units():
    view = student_view(make_activity(Phase.DRAFT), make_participant(), ["小明", "阿美"], [])
    assert view == {
        "activity": {"id": 7, "phase": "DRAFT", "groupCount": 6},
        "membership": {"groupNumber": 3, "displayName": "小明"},
        "group": {"members": ["小明", "阿美"], "submissions": []},
    }


def test_member_in_open_sees_units_in_position_order_and_own_submissions_without_rank():
    view = student_view(
        make_activity(Phase.OPEN), make_participant(), ["小明", "阿美"], [make_submission(rank=1)]
    )
    assert view["activity"] == {
        "id": 7,
        "phase": "OPEN",
        "groupCount": 6,
        "units": [
            {"unitId": 31, "number": 3, "kind": "GROUP_SET", "subParts": [1, 2]},
            {"unitId": 32, "number": 4, "kind": "SINGLE", "subParts": [1]},
        ],
    }
    assert view["membership"] == {"groupNumber": 3, "displayName": "小明"}
    assert view["group"] == {
        "members": ["小明", "阿美"],
        "submissions": [
            {
                "unitId": 31,
                "unitNumber": 3,
                "submittedBy": "阿美",
                "receivedAt": "2026-11-27T02:14:09.512Z",
                "answers": [{"subPart": 1, "text": "光合作用"}, {"subPart": 2, "text": "葉綠體"}],
            }
        ],
    }
    assert_no_forbidden_keys(view)


def test_member_of_closed_activity_sees_own_submissions_without_units():
    view = student_view(make_activity(Phase.CLOSED), make_participant(), ["小明"], [make_submission()])
    assert view["activity"] == {"id": 7, "phase": "CLOSED", "groupCount": 6}
    assert [s["unitNumber"] for s in view["group"]["submissions"]] == [3]
    assert_no_forbidden_keys(view)


@pytest.mark.parametrize("phase", list(Phase))
def test_no_forbidden_keys_in_any_phase(phase):
    view = student_view(make_activity(phase), make_participant(), ["小明"], [make_submission()])
    assert_no_forbidden_keys(view)
    if phase is not Phase.OPEN:
        assert "units" not in view["activity"]


def test_foreign_group_submissions_are_dropped_even_if_passed_in():
    own = make_submission(group=3, sid=1, by="阿美")
    foreign = make_submission(group=5, sid=2, by="LEAK-name", unit_id=32, unit_number=4)
    view = student_view(make_activity(Phase.OPEN), make_participant(group=3), ["小明"], [own, foreign])
    assert [s["submittedBy"] for s in view["group"]["submissions"]] == ["阿美"]
    assert "LEAK-name" not in repr(view)


def test_membership_of_another_activity_is_treated_as_none():
    view = student_view(make_activity(Phase.OPEN, activity_id=8), make_participant(activity_id=7),
                        ["小明"], [make_submission()])
    assert view == {
        "activity": {"id": 8, "phase": "OPEN", "groupCount": 6},
        "membership": None,
        "group": None,
    }


def test_view_is_json_serialisable_plain_data():
    import json

    view = student_view(make_activity(Phase.OPEN), make_participant(), ["小明"], [make_submission()])
    assert json.loads(json.dumps(view, ensure_ascii=False)) == view
