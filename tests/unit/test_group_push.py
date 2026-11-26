"""Group-only pushes (002 US4; FR-021 – FR-023; contracts/websocket.md › /ws/student).

A real RealtimeHub with student sockets keyed directly (no event loop needed) and delivery
recorded instead of sent.
"""

from __future__ import annotations

import pytest

from quizbuzzer.models import StudentKey
from quizbuzzer.realtime.hub import RealtimeHub
from quizbuzzer.services.participation_service import AlreadySubmitted, ParticipationService
from tests.live_helpers import answers_for, init_schema, make_activity, set_db_phase


class RecordingHub(RealtimeHub):
    def __init__(self):
        super().__init__()
        self.student_sends = []  # list of [(ws, message)] per delivery
        self.teacher_messages = []

    def send_from_thread(self, pairs):
        self.student_sends.append(list(pairs))

    def publish_from_thread(self, message):
        self.teacher_messages.append(message)


class Sock:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


@pytest.fixture
def setup(fake_adapter, db_path):
    init_schema(db_path)
    hub = RecordingHub()
    part = ParticipationService(db_path, hub)
    activity = make_activity(fake_adapter, db_path, n_units=4, group_count=6, phase="DRAFT")
    t3a, _ = part.join(None, activity.id, 3, "阿美")
    t3b, _ = part.join(None, activity.id, 3, "小明")
    t5, _ = part.join(None, activity.id, 5, "LEAK-g5")
    socks = {name: Sock(name) for name in ("g3a", "g3b", "g5", "anon")}
    for name, token in (("g3a", t3a), ("g3b", t3b), ("g5", t5)):
        hub.students[socks[name]] = part.resolve_key(token)
    hub.students[socks["anon"]] = None
    hub.student_sends.clear()
    return hub, part, activity, socks, {"g3a": t3a, "g3b": t3b, "g5": t5}


def only_delivery(hub):
    assert len(hub.student_sends) == 1, hub.student_sends
    return hub.student_sends[0]


def test_join_pushes_only_to_the_same_groups_sockets(setup):
    hub, part, activity, socks, _ = setup
    part.join(None, activity.id, 3, "新同學")
    delivery = only_delivery(hub)
    assert {ws.name for ws, _ in delivery} == {"g3a", "g3b"}
    for _, message in delivery:
        assert message["type"] == "student.state"
        assert message["state"]["group"]["members"] == ["阿美", "小明", "新同學"]
        assert "LEAK-g5" not in repr(message)


def test_submit_pushes_only_to_the_same_groups_sockets(setup, db_path):
    hub, part, activity, socks, tokens = setup
    set_db_phase(db_path, activity.id, "OPEN")
    unit = activity.units[1]
    part.submit(tokens["g3a"], unit.id, answers_for(unit, ["光合作用"]))
    delivery = only_delivery(hub)
    assert {ws.name for ws, _ in delivery} == {"g3a", "g3b"}
    for _, message in delivery:
        subs = message["state"]["group"]["submissions"]
        assert [(s["unitId"], s["submittedBy"]) for s in subs] == [(unit.id, "阿美")]
        assert subs[0]["answers"] == [{"subPart": 1, "text": "光合作用"}]
        assert "rank" not in repr(message)


def test_submission_by_another_group_sends_nothing_to_group_3(setup, db_path):
    hub, part, activity, socks, tokens = setup
    set_db_phase(db_path, activity.id, "OPEN")
    unit = activity.units[1]
    part.submit(tokens["g5"], unit.id, answers_for(unit, ["LEAK-answer"]))
    delivery = only_delivery(hub)
    assert {ws.name for ws, _ in delivery} == {"g5"}  # g3a, g3b and anon get nothing at all


def test_leave_in_draft_updates_the_old_group(setup):
    hub, part, activity, socks, tokens = setup
    part.leave(tokens["g3b"])
    delivery = only_delivery(hub)
    assert {ws.name for ws, _ in delivery} == {"g3a", "g3b"}
    by_name = {ws.name: m for ws, m in delivery}
    assert by_name["g3a"]["state"]["group"]["members"] == ["阿美"]
    # The leaver's own (stale-keyed) socket gets the no-membership view.
    assert by_name["g3b"]["state"]["membership"] is None


def test_refused_submit_sends_nothing_to_students(setup, db_path):
    hub, part, activity, socks, tokens = setup
    set_db_phase(db_path, activity.id, "OPEN")
    unit = activity.units[1]
    part.submit(tokens["g3a"], unit.id, answers_for(unit))
    hub.student_sends.clear()
    with pytest.raises(AlreadySubmitted):
        part.submit(tokens["g3b"], unit.id, answers_for(unit))
    assert hub.student_sends == []


def test_keys_are_resolved_from_the_cookie(setup):
    hub, part, activity, socks, tokens = setup
    key = part.resolve_key(tokens["g5"])
    assert isinstance(key, StudentKey)
    assert (key.activity_id, key.group_number) == (activity.id, 5)
