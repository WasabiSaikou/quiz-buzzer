"""Join and change-group rules (002 US2; FR-009 – FR-014; data-model.md › Participant)."""

from __future__ import annotations

import pytest

from quizbuzzer import db
from quizbuzzer.services.participation_service import (
    AlreadyJoined,
    GroupChangeRefused,
    InvalidJoin,
    JoinRefused,
    NotAMember,
    ParticipationService,
    hash_token,
)
from tests.live_helpers import init_schema, make_activity, set_db_phase


@pytest.fixture
def part(db_path):
    init_schema(db_path)
    return ParticipationService(db_path)


def rows(db_path, sql, *args):
    conn = db.connect(db_path)
    try:
        return [tuple(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


@pytest.mark.parametrize("phase", ["DRAFT", "OPEN"])
def test_join_allowed_in_draft_and_open(part, fake_adapter, db_path, phase):
    a = make_activity(fake_adapter, db_path, phase=phase)
    token, state = part.join(None, a.id, 3, " 小明 ")
    assert state["membership"] == {"groupNumber": 3, "displayName": "小明"}  # stored trimmed
    assert state["activity"]["phase"] == phase
    assert rows(db_path, "SELECT group_number, display_name FROM participants") == [(3, "小明")]
    assert part.resolve_key(token).group_number == 3


@pytest.mark.parametrize("name", ["", "   ", "　", "\n", "名" * 21, None, 7])
def test_invalid_display_names_are_refused(part, fake_adapter, db_path, name):
    a = make_activity(fake_adapter, db_path)
    with pytest.raises(InvalidJoin) as info:
        part.join(None, a.id, 1, name)
    assert info.value.field == "displayName" and info.value.max == 20
    assert rows(db_path, "SELECT count(*) FROM participants") == [(0,)]


def test_twenty_character_name_is_accepted(part, fake_adapter, db_path):
    a = make_activity(fake_adapter, db_path)
    _token, state = part.join(None, a.id, 1, "名" * 20)
    assert state["membership"]["displayName"] == "名" * 20


@pytest.mark.parametrize("group, ok", [(0, False), (1, True), (6, True), (7, False), (13, False),
                                       (True, False), ("3", False), (None, False), (2.5, False)])
def test_group_number_must_be_in_range(part, fake_adapter, db_path, group, ok):
    a = make_activity(fake_adapter, db_path, group_count=6)
    if ok:
        part.join(None, a.id, group, "小明")
    else:
        with pytest.raises(InvalidJoin) as info:
            part.join(None, a.id, group, "小明")
        assert info.value.field == "groupNumber" and info.value.max == 6


def test_join_refused_without_current_activity(part):
    with pytest.raises(JoinRefused) as info:
        part.join(None, 1, 1, "小明")
    assert info.value.phase is None


def test_join_refused_for_closed_activity(part, fake_adapter, db_path):
    a = make_activity(fake_adapter, db_path, phase="CLOSED")
    with pytest.raises(JoinRefused) as info:
        part.join(None, a.id, 1, "小明")
    assert info.value.phase.value == "CLOSED"


def test_join_refused_when_activity_id_is_not_the_current_one(part, fake_adapter, db_path):
    a = make_activity(fake_adapter, db_path)
    with pytest.raises(JoinRefused):
        part.join(None, a.id + 99, 1, "小明")


def test_second_join_from_the_same_browser_is_refused(part, fake_adapter, db_path):
    a = make_activity(fake_adapter, db_path)
    token, _ = part.join(None, a.id, 1, "小明")
    with pytest.raises(AlreadyJoined):
        part.join(token, a.id, 2, "小明")
    assert rows(db_path, "SELECT count(*) FROM participants") == [(1,)]


def test_token_of_an_older_activity_may_join_the_new_one(part, fake_adapter, db_path):
    old = make_activity(fake_adapter, db_path, phase="OPEN")
    token, _ = part.join(None, old.id, 1, "小明")
    set_db_phase(db_path, old.id, "CLOSED")
    new = make_activity(fake_adapter, db_path, phase="DRAFT")
    new_token, state = part.join(token, new.id, 2, "小明")
    assert new_token != token and state["membership"]["groupNumber"] == 2


def test_only_the_token_hash_is_stored(part, fake_adapter, db_path):
    a = make_activity(fake_adapter, db_path)
    token, _ = part.join(None, a.id, 1, "小明")
    assert len(token) >= 43
    stored = rows(db_path, "SELECT token_hash FROM participants")
    assert stored == [(hash_token(token),)]
    assert token not in repr(rows(db_path, "SELECT * FROM participants"))


def test_duplicate_names_are_allowed(part, fake_adapter, db_path):
    a = make_activity(fake_adapter, db_path)
    part.join(None, a.id, 1, "小明")
    part.join(None, a.id, 1, "小明")
    part.join(None, a.id, 2, "小明")
    assert rows(db_path, "SELECT count(*) FROM participants") == [(3,)]


def test_leave_in_draft_deletes_the_participant(part, fake_adapter, db_path):
    a = make_activity(fake_adapter, db_path, phase="DRAFT")
    token, _ = part.join(None, a.id, 1, "小明")
    part.leave(token)
    assert rows(db_path, "SELECT count(*) FROM participants") == [(0,)]
    assert part.resolve_key(token) is None
    _token2, state = part.join(None, a.id, 5, "小明")  # change group = leave + join
    assert state["membership"]["groupNumber"] == 5


@pytest.mark.parametrize("phase", ["OPEN", "CLOSED"])
def test_leave_refused_once_open(part, fake_adapter, db_path, phase):
    a = make_activity(fake_adapter, db_path, phase="DRAFT")
    token, _ = part.join(None, a.id, 1, "小明")
    set_db_phase(db_path, a.id, phase)
    with pytest.raises(GroupChangeRefused) as info:
        part.leave(token)
    assert info.value.phase.value == phase
    assert rows(db_path, "SELECT count(*) FROM participants") == [(1,)]


@pytest.mark.parametrize("token", [None, "", "unknown-token"])
def test_leave_without_membership(part, fake_adapter, db_path, token):
    make_activity(fake_adapter, db_path, phase="DRAFT")
    with pytest.raises(NotAMember):
        part.leave(token)
