"""Core ranking rules, tests first (Constitution I; 002 FR-016 – FR-020; research R3).

data-model.md › Submission.*, SubmissionAnswer.*.
"""

from __future__ import annotations

import re

import pytest

from quizbuzzer import db
from quizbuzzer.services import participation_service as ps
from quizbuzzer.services.participation_service import (
    ActivityEnded,
    AlreadySubmitted,
    InvalidAnswers,
    NotAMember,
    NotOpen,
    ParticipationService,
    UnitNotFound,
)
from tests.live_helpers import answers_for, init_schema, make_activity, set_db_phase


@pytest.fixture
def part(db_path):
    init_schema(db_path)
    return ParticipationService(db_path)


@pytest.fixture
def activity(fake_adapter, db_path, part):
    return make_activity(fake_adapter, db_path, n_units=4, group_count=6, phase="DRAFT")


def join(part, activity, group, name=None):
    token, _ = part.join(None, activity.id, group, name or f"g{group}")
    return token


def open_(db_path, activity):
    set_db_phase(db_path, activity.id, "OPEN")


def unit(activity, number):
    return next(u for u in activity.units if u.number == number)


def count(db_path, table):
    conn = db.connect(db_path)
    try:
        return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def ranks(db_path, unit_id):
    conn = db.connect(db_path)
    try:
        return [tuple(r) for r in conn.execute(
            "SELECT group_number, rank FROM submissions WHERE unit_id = ? ORDER BY rank", (unit_id,))]
    finally:
        conn.close()


def walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


# --- validation before the transaction ---------------------------------------------------


@pytest.mark.parametrize("text", ["", "  ", "　", "\n", "\t　 \n"])
def test_empty_or_whitespace_answers_are_refused(part, activity, db_path, text):
    t = join(part, activity, 1)
    open_(db_path, activity)
    u = unit(activity, 1)  # 題組 (1)(2)
    with pytest.raises(InvalidAnswers) as info:
        part.submit(t, u.id, [{"subPart": 1, "text": "ok"}, {"subPart": 2, "text": text}])
    assert info.value.sub_parts == [2]
    assert info.value.reasons == {2: "empty"}
    assert "（2）" in str(info.value)
    assert count(db_path, "submissions") == 0


def test_length_limit_is_200_characters_after_trimming(part, activity, db_path):
    t = join(part, activity, 1)
    open_(db_path, activity)
    u = unit(activity, 1)
    with pytest.raises(InvalidAnswers) as info:
        part.submit(t, u.id, [{"subPart": 1, "text": "字" * 201}, {"subPart": 2, "text": "  "}])
    assert info.value.sub_parts == [1, 2]
    assert info.value.reasons == {1: "too_long", 2: "empty"}
    out = part.submit(t, u.id, [{"subPart": 1, "text": "字" * 200}, {"subPart": 2, "text": " 答 "}])
    assert out["answers"] == [{"subPart": 1, "text": "字" * 200}, {"subPart": 2, "text": "答"}]


def test_whitespace_padding_does_not_count_toward_the_limit(part, activity, db_path):
    t = join(part, activity, 1)
    open_(db_path, activity)
    u = unit(activity, 2)
    out = part.submit(t, u.id, [{"subPart": 1, "text": "　" + "字" * 200 + "\n"}])
    assert out["answers"] == [{"subPart": 1, "text": "字" * 200}]


@pytest.mark.parametrize("answers, reasons", [
    ([{"subPart": 1, "text": "a"}], {2: "missing"}),
    ([{"subPart": 1, "text": "a"}, {"subPart": 2, "text": "b"}, {"subPart": 3, "text": "c"}], {3: "unknown"}),
    ([{"subPart": 1, "text": "a"}, {"subPart": 1, "text": "b"}, {"subPart": 2, "text": "c"}], {1: "duplicate"}),
    ([], {1: "missing", 2: "missing"}),
])
def test_answer_set_must_match_the_units_slots(part, activity, db_path, answers, reasons):
    t = join(part, activity, 1)
    open_(db_path, activity)
    with pytest.raises(InvalidAnswers) as info:
        part.submit(t, unit(activity, 1).id, answers)
    assert info.value.reasons == reasons
    assert count(db_path, "submissions") == 0


# --- check order inside the transaction (research R3) --------------------------------------


@pytest.mark.parametrize("token", [None, "", "unknown"])
def test_not_a_member(part, activity, db_path, token):
    open_(db_path, activity)
    with pytest.raises(NotAMember):
        part.submit(token, unit(activity, 2).id, [{"subPart": 1, "text": "a"}])


def test_draft_is_not_open(part, activity):
    t = join(part, activity, 1)
    with pytest.raises(NotOpen) as info:
        part.submit(t, unit(activity, 2).id, [{"subPart": 1, "text": "a"}])
    assert str(info.value) == "The activity has not opened yet."


def test_closed_has_ended(part, activity, db_path):
    t = join(part, activity, 1)
    set_db_phase(db_path, activity.id, "CLOSED")
    with pytest.raises(ActivityEnded) as info:
        part.submit(t, unit(activity, 2).id, [{"subPart": 1, "text": "a"}])
    assert str(info.value) == "The activity has ended."


def test_membership_of_an_older_activity_is_not_a_member(part, fake_adapter, db_path, activity):
    t = join(part, activity, 1)
    set_db_phase(db_path, activity.id, "CLOSED")
    newer = make_activity(fake_adapter, db_path, phase="OPEN")
    with pytest.raises(NotAMember):
        part.submit(t, unit(newer, 2).id, [{"subPart": 1, "text": "a"}])


def test_unit_of_another_activity_is_not_found(part, fake_adapter, db_path, activity):
    t = join(part, activity, 1)
    open_(db_path, activity)
    with pytest.raises(UnitNotFound):
        part.submit(t, 99999, [{"subPart": 1, "text": "a"}])


def test_phase_is_checked_before_the_answer_set(part, activity):
    t = join(part, activity, 1)  # DRAFT
    with pytest.raises(NotOpen):
        part.submit(t, unit(activity, 1).id, [{"subPart": 1, "text": "a"}])  # also missing (2)


def test_second_submission_by_any_member_of_the_group(part, activity, db_path):
    t1, t2 = join(part, activity, 3, "阿美"), join(part, activity, 3, "小明")
    open_(db_path, activity)
    u = unit(activity, 2)
    part.submit(t1, u.id, [{"subPart": 1, "text": "first"}])
    with pytest.raises(AlreadySubmitted) as info:
        part.submit(t2, u.id, [{"subPart": 1, "text": "second"}])
    assert str(info.value) == f"Your group has already submitted question {u.number}."
    assert info.value.submission["answers"] == [{"subPart": 1, "text": "first"}]
    assert info.value.submission["submittedBy"] == "阿美"
    assert "rank" not in set(walk_keys(info.value.submission))
    assert count(db_path, "submissions") == 1


# --- ranks ------------------------------------------------------------------------------------


def test_ranks_follow_arrival_order_and_only_rank_1_wins(part, activity, db_path):
    tokens = {g: join(part, activity, g) for g in (4, 1, 6)}
    open_(db_path, activity)
    u = unit(activity, 1)
    for g in (4, 1, 6):
        part.submit(tokens[g], u.id, answers_for(u))
    assert ranks(db_path, u.id) == [(4, 1), (1, 2), (6, 3)]
    conn = db.connect(db_path)
    try:
        subs = db.list_dashboard_submissions(conn, activity.id)
    finally:
        conn.close()
    assert [(s.group_number, s.is_winner) for s in subs] == [(4, True), (1, False), (6, False)]


def test_each_unit_has_its_own_ranks(part, activity, db_path):
    t1, t2 = join(part, activity, 1), join(part, activity, 2)
    open_(db_path, activity)
    u2, u3 = unit(activity, 2), unit(activity, 3)
    part.submit(t1, u2.id, answers_for(u2))
    part.submit(t2, u3.id, answers_for(u3))
    part.submit(t1, u3.id, answers_for(u3))
    assert ranks(db_path, u2.id) == [(1, 1)]
    assert ranks(db_path, u3.id) == [(2, 1), (1, 2)]


def test_group_and_submitter_come_from_the_participant(part, activity, db_path):
    t = join(part, activity, 5, "小華")
    open_(db_path, activity)
    u = unit(activity, 2)
    out = part.submit(t, u.id, answers_for(u))
    conn = db.connect(db_path)
    try:
        row = conn.execute("SELECT s.group_number, p.display_name FROM submissions s "
                           "JOIN participants p ON s.participant_id = p.id").fetchone()
    finally:
        conn.close()
    assert tuple(row) == (5, "小華")
    assert out["submittedBy"] == "小華" and out["unitId"] == u.id and out["unitNumber"] == u.number


def test_received_at_is_server_utc_with_milliseconds(part, activity, db_path):
    t = join(part, activity, 1)
    open_(db_path, activity)
    u = unit(activity, 2)
    out = part.submit(t, u.id, answers_for(u))
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", out["receivedAt"])


def test_time_never_orders_ranks(part, activity, db_path, monkeypatch):
    tokens = [join(part, activity, g) for g in (1, 2, 3)]
    open_(db_path, activity)
    times = iter(["2026-11-27T02:00:09.000Z", "2026-11-27T02:00:01.000Z", "2026-11-27T02:00:00.000Z"])
    monkeypatch.setattr(ps, "_utc_now_ms", lambda: next(times))
    u = unit(activity, 2)
    for t in tokens:
        part.submit(t, u.id, answers_for(u))
    # Later arrivals got *earlier* timestamps; ranks still follow arrival order.
    assert ranks(db_path, u.id) == [(1, 1), (2, 2), (3, 3)]


def test_response_never_carries_rank(part, activity, db_path):
    t = join(part, activity, 1)
    open_(db_path, activity)
    u = unit(activity, 1)
    out = part.submit(t, u.id, answers_for(u))
    assert set(out) == {"unitId", "unitNumber", "answers", "submittedBy", "receivedAt"}
    assert not {"rank", "isWinner"} & set(walk_keys(out))


def test_submit_is_all_or_nothing(part, activity, db_path, monkeypatch):
    t = join(part, activity, 1)
    open_(db_path, activity)
    u = unit(activity, 1)
    original = db.insert_submission

    def fail_after_insert(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("disk full")

    monkeypatch.setattr(db, "insert_submission", fail_after_insert)
    with pytest.raises(RuntimeError):
        part.submit(t, u.id, answers_for(u))
    assert count(db_path, "submissions") == 0
    assert count(db_path, "submission_answers") == 0
