"""Phase transitions (Constitution IV, V): open (US1), end (US3), cancel (US5) and the dashboard.

ActivityService against a file DB, with a recording hub and a recording student publisher that
checks the committed phase at call time (publishing must happen after the commit).
"""

from __future__ import annotations

import pytest

from quizbuzzer import db
from quizbuzzer.models import Phase
from quizbuzzer.services.activity_service import (
    ActivityNotFound,
    ActivityService,
    PhaseConflict,
    ReimportRefused,
)

GROUP = "https://docs.google.com/spreadsheets/d/template_group/edit"
SINGLE = "https://docs.google.com/spreadsheets/d/template_single/edit"


class RecordingHub:
    def __init__(self):
        self.messages = []

    def publish_from_thread(self, message):
        self.messages.append(message)

    def types(self):
        return [m["type"] for m in self.messages]


@pytest.fixture
def init_db(db_path):
    conn = db.connect(db_path)
    db.init_schema(conn)
    conn.close()


def phase_in_db(db_path, activity_id):
    conn = db.connect(db_path)
    try:
        return db.get_activity_phase(conn, activity_id)
    finally:
        conn.close()


@pytest.fixture
def env(fake_adapter, db_path, init_db):
    class Env:
        pass

    e = Env()
    e.hub = RecordingHub()
    e.student_calls = []
    e.svc = ActivityService(fake_adapter, db_path, e.hub, student_publisher=lambda: e.student_calls.append(
        phase_in_db(db_path, e.current_id) if getattr(e, "current_id", None) else None
    ))
    return e


def confirm(svc, url=GROUP, group_count=6):
    p = svc.preview_import(url, 0)
    return svc.create_from_import(url, 0, group_count, p.fingerprint, True)


def set_phase(db_path, activity_id, phase):
    conn = db.connect(db_path)
    try:
        conn.execute("UPDATE activities SET phase = ? WHERE id = ?", (phase, activity_id))
    finally:
        conn.close()


@pytest.fixture
def draft(env):
    a = confirm(env.svc)
    env.current_id = a.id
    env.hub.messages.clear()
    env.student_calls.clear()
    return a


# --- US1: open ---------------------------------------------------------------------------


def test_open_moves_draft_to_open(env, draft, db_path):
    opened = env.svc.open_activity(draft.id)
    assert opened.phase is Phase.OPEN
    assert opened.id == draft.id and opened.units == draft.units
    assert phase_in_db(db_path, draft.id) is Phase.OPEN


@pytest.mark.parametrize("phase", ["OPEN", "CLOSED"])
def test_open_refused_unless_draft(env, draft, db_path, phase):
    set_phase(db_path, draft.id, phase)
    with pytest.raises(PhaseConflict) as info:
        env.svc.open_activity(draft.id)
    assert info.value.phase is Phase(phase)
    assert phase_in_db(db_path, draft.id) is Phase(phase)
    assert env.hub.messages == [] and env.student_calls == []


def test_open_message_says_already_open(env, draft):
    env.svc.open_activity(draft.id)
    with pytest.raises(PhaseConflict) as info:
        env.svc.open_activity(draft.id)
    assert "already OPEN" in str(info.value)


def test_open_missing_activity(env):
    with pytest.raises(ActivityNotFound):
        env.svc.open_activity(999)
    assert env.hub.messages == [] and env.student_calls == []


def test_open_publishes_after_commit(env, draft):
    env.svc.open_activity(draft.id)
    assert env.hub.types() == ["activity.state", "dashboard.state"]
    assert env.hub.messages[0]["activity"]["phase"] == "OPEN"
    assert env.hub.messages[1]["dashboard"]["phase"] == "OPEN"
    # The student publisher ran once, and saw the committed OPEN phase.
    assert env.student_calls == [Phase.OPEN]


def test_reimport_refused_after_open(env, draft):
    env.svc.open_activity(draft.id)
    p = env.svc.preview_import(GROUP, 0)
    with pytest.raises(ReimportRefused):
        env.svc.replace_questions(draft.id, GROUP, 0, p.fingerprint, True)


# --- Dashboard shape (contracts/rest-api.md › Dashboard) ---------------------------------


def _add_member(db_path, activity_id, group, name, token):
    conn = db.connect(db_path)
    try:
        return db.insert_participant(
            conn, activity_id=activity_id, group_number=group, display_name=name,
            token_hash=f"h-{token}", joined_at="2026-11-27T01:00:00Z",
        )
    finally:
        conn.close()


def _add_submission(db_path, unit, group, participant_id, rank, texts, at):
    conn = db.connect(db_path)
    try:
        sid = conn.execute(
            "INSERT INTO submissions (unit_id, group_number, participant_id, rank, received_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (unit.id, group, participant_id, rank, at),
        ).lastrowid
        for slot, text in zip(unit.slots, texts, strict=True):
            conn.execute(
                "INSERT INTO submission_answers (submission_id, slot_id, text) VALUES (?, ?, ?)",
                (sid, slot.id, text),
            )
    finally:
        conn.close()


def test_dashboard_shape(env, draft, db_path):
    env.svc.open_activity(draft.id)
    group_set = next(u for u in draft.units if len(u.slots) == 2)
    single = next(u for u in draft.units if len(u.slots) == 1)
    p4 = _add_member(db_path, draft.id, 4, "小華", "a")
    p1 = _add_member(db_path, draft.id, 1, "小明", "b")
    _add_member(db_path, draft.id, 1, "小明", "c")  # duplicate names are kept
    _add_submission(db_path, group_set, 1, p1, 2, ["b1", "b2"], "2026-11-27T02:00:01.000Z")
    _add_submission(db_path, group_set, 4, p4, 1, ["a1", "a2"], "2026-11-27T02:00:00.500Z")

    d = env.svc.get_dashboard(draft.id)
    assert (d["activityId"], d["phase"], d["groupCount"]) == (draft.id, "OPEN", 6)
    assert [u["number"] for u in d["units"]] == [u.number for u in sorted(draft.units, key=lambda u: u.position)]
    gs = next(u for u in d["units"] if u["unitId"] == group_set.id)
    assert gs["kind"] == "GROUP_SET" and gs["subParts"] == [1, 2]
    assert gs["submissions"] == [
        {
            "rank": 1, "isWinner": True, "groupNumber": 4, "submittedBy": "小華",
            "receivedAt": "2026-11-27T02:00:00.500Z",
            "answers": [{"subPart": 1, "text": "a1"}, {"subPart": 2, "text": "a2"}],
        },
        {
            "rank": 2, "isWinner": False, "groupNumber": 1, "submittedBy": "小明",
            "receivedAt": "2026-11-27T02:00:01.000Z",
            "answers": [{"subPart": 1, "text": "b1"}, {"subPart": 2, "text": "b2"}],
        },
    ]
    assert next(u for u in d["units"] if u["unitId"] == single.id)["submissions"] == []
    assert d["groups"] == [
        {"number": 1, "members": ["小明", "小明"], "memberCount": 2},
        {"number": 2, "members": [], "memberCount": 0},
        {"number": 3, "members": [], "memberCount": 0},
        {"number": 4, "members": ["小華"], "memberCount": 1},
        {"number": 5, "members": [], "memberCount": 0},
        {"number": 6, "members": [], "memberCount": 0},
    ]


def test_dashboard_missing_activity(env):
    with pytest.raises(ActivityNotFound):
        env.svc.get_dashboard(999)


# --- US3: end, displayed activity, import after end (T033) --------------------------------


def test_end_moves_open_to_closed(env, draft, db_path):
    env.svc.open_activity(draft.id)
    env.hub.messages.clear()
    env.student_calls.clear()
    ended = env.svc.end_activity(draft.id)
    assert ended.phase is Phase.CLOSED
    assert phase_in_db(db_path, draft.id) is Phase.CLOSED
    assert env.hub.types() == ["activity.state", "dashboard.state"]
    assert env.hub.messages[0]["activity"]["phase"] == "CLOSED"
    assert env.student_calls == [Phase.CLOSED]  # published after the commit


def test_end_refused_for_draft_suggests_cancel(env, draft, db_path):
    with pytest.raises(PhaseConflict) as info:
        env.svc.end_activity(draft.id)
    assert info.value.phase is Phase.DRAFT
    assert "Cancel activity" in str(info.value)
    assert phase_in_db(db_path, draft.id) is Phase.DRAFT
    assert env.hub.messages == [] and env.student_calls == []


def test_end_refused_when_already_closed(env, draft, db_path):
    set_phase(db_path, draft.id, "CLOSED")
    with pytest.raises(PhaseConflict) as info:
        env.svc.end_activity(draft.id)
    assert info.value.phase is Phase.CLOSED
    assert env.hub.messages == [] and env.student_calls == []


def test_end_missing_activity(env):
    with pytest.raises(ActivityNotFound):
        env.svc.end_activity(999)


def test_closing_with_zero_submissions(env, draft):
    env.svc.open_activity(draft.id)
    env.svc.end_activity(draft.id)
    d = env.svc.get_dashboard(draft.id)
    assert d["phase"] == "CLOSED"
    assert len(d["units"]) == len(draft.units)
    assert all(u["submissions"] == [] for u in d["units"])
    assert [g["number"] for g in d["groups"]] == [1, 2, 3, 4, 5, 6]


def test_displayed_activity(env, db_path):
    assert env.svc.get_displayed_activity() is None
    a = confirm(env.svc)
    assert env.svc.get_displayed_activity().id == a.id  # the DRAFT one
    env.svc.open_activity(a.id)
    assert env.svc.get_displayed_activity().phase is Phase.OPEN
    env.svc.end_activity(a.id)
    shown = env.svc.get_displayed_activity()
    assert shown.id == a.id and shown.phase is Phase.CLOSED  # latest CLOSED when none current
    assert env.svc.get_current_activity() is None  # "current" still means DRAFT/OPEN only


def _rows(db_path, activity_id):
    conn = db.connect(db_path)
    try:
        return (
            [tuple(r) for r in conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,))],
            [tuple(r) for r in conn.execute(
                "SELECT * FROM question_units WHERE activity_id = ? ORDER BY id", (activity_id,))],
        )
    finally:
        conn.close()


def test_import_after_end_creates_a_new_draft(env, db_path):
    a = confirm(env.svc)
    env.svc.open_activity(a.id)
    env.svc.end_activity(a.id)
    before = _rows(db_path, a.id)
    new = confirm(env.svc, SINGLE)  # FR-020a: a CLOSED activity never blocks an import
    assert new.id != a.id and new.phase is Phase.DRAFT
    assert _rows(db_path, a.id) == before
    assert env.svc.get_displayed_activity().id == new.id


# --- US5: cancel a DRAFT activity (T045) -----------------------------------------------------

from quizbuzzer.services.activity_service import CancelRefused  # noqa: E402
from quizbuzzer.services.participation_service import (  # noqa: E402
    NotAMember,
    ParticipationService,
)


def _count(db_path, sql, *args):
    conn = db.connect(db_path)
    try:
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()


def test_cancel_deletes_a_draft_with_everything_it_owns(env, draft, db_path):
    part = ParticipationService(db_path)
    part.join(None, draft.id, 1, "小明")
    env.svc.cancel_activity(draft.id)
    assert _count(db_path, "SELECT count(*) FROM activities WHERE id = ?", draft.id) == 0
    assert _count(db_path, "SELECT count(*) FROM question_units WHERE activity_id = ?", draft.id) == 0
    assert _count(db_path, "SELECT count(*) FROM answer_slots") == 0
    assert _count(db_path, "SELECT count(*) FROM participants") == 0


def test_cancel_refused_for_open(env, draft, db_path):
    env.svc.open_activity(draft.id)
    env.hub.messages.clear()
    env.student_calls.clear()
    with pytest.raises(CancelRefused) as info:
        env.svc.cancel_activity(draft.id)
    assert info.value.phase is Phase.OPEN
    assert "can only be ended" in str(info.value)
    assert phase_in_db(db_path, draft.id) is Phase.OPEN
    assert env.hub.messages == [] and env.student_calls == []


def test_cancel_refused_for_closed_and_rows_kept(env, draft, db_path):
    set_phase(db_path, draft.id, "CLOSED")
    before = _rows(db_path, draft.id)
    with pytest.raises(CancelRefused) as info:
        env.svc.cancel_activity(draft.id)
    assert info.value.phase is Phase.CLOSED
    assert _rows(db_path, draft.id) == before


def test_cancel_missing_activity(env):
    with pytest.raises(ActivityNotFound):
        env.svc.cancel_activity(999)


def test_cancel_publishes_the_displayed_activity_after_commit(env, draft):
    env.svc.cancel_activity(draft.id)
    assert env.hub.messages == [{"type": "activity.state", "activity": None}]  # no dashboard
    assert env.student_calls == [None]  # ran once, after the row was gone


def test_cancel_shows_the_latest_closed_activity_to_teachers(env, db_path):
    old = confirm(env.svc)
    env.svc.open_activity(old.id)
    env.svc.end_activity(old.id)
    new = confirm(env.svc, SINGLE)
    env.hub.messages.clear()
    env.svc.cancel_activity(new.id)
    assert [m["type"] for m in env.hub.messages] == ["activity.state"]
    assert env.hub.messages[0]["activity"]["id"] == old.id
    assert env.hub.messages[0]["activity"]["phase"] == "CLOSED"


def test_after_cancel_a_new_import_succeeds(env, draft):
    env.svc.cancel_activity(draft.id)
    again = confirm(env.svc, SINGLE)
    assert again.phase is Phase.DRAFT and again.id != draft.id


def test_reimport_into_a_cancelled_activity_is_not_found(env, draft):
    p = env.svc.preview_import(GROUP, 0)
    env.svc.cancel_activity(draft.id)
    with pytest.raises(ActivityNotFound):
        env.svc.replace_questions(draft.id, GROUP, 0, p.fingerprint, True)


def test_memberships_of_a_cancelled_activity_stop_working(env, draft, db_path):
    part = ParticipationService(db_path)
    token, _ = part.join(None, draft.id, 1, "小明")
    unit_id = draft.units[0].id
    env.svc.cancel_activity(draft.id)
    assert part.resolve_key(token) is None
    with pytest.raises(NotAMember):
        part.submit(token, unit_id, [{"subPart": 1, "text": "x"}])
