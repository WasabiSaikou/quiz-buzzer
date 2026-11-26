"""Teacher activity control over REST + WebSocket pushes (002 US1 open, US5 cancel).

contracts/rest-api.md › Teacher activity control; contracts/websocket.md.
"""

from __future__ import annotations

from tests.live_helpers import (
    add_member,
    anonymous_state,
    cookie,
    create_activity,
    next_of_type,
    open_activity,
)

# --- US1: open (T020) ---------------------------------------------------------------------


def test_open_returns_open_activity(client):
    a = create_activity(client)
    opened = open_activity(client, a)
    assert opened["phase"] == "OPEN"
    assert opened["id"] == a["id"] and opened["units"] == a["units"]


def test_open_twice_is_409_phase_conflict(client):
    a = create_activity(client)
    open_activity(client, a)
    r = client.post(f"/api/teacher/activities/{a['id']}/open")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "phase_conflict"
    assert err["details"] == {"phase": "OPEN"}
    assert "already OPEN" in err["message"]


def test_open_unknown_activity_is_404(client):
    r = client.post("/api/teacher/activities/999/open")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_open_pushes_to_every_teacher_socket(client):
    a = create_activity(client)
    with client.websocket_connect("/ws/teacher") as t1, client.websocket_connect("/ws/teacher") as t2:
        next_of_type(t1, "activity.state")
        next_of_type(t2, "activity.state")
        open_activity(client, a)
        for ws in (t1, t2):
            assert next_of_type(ws, "activity.state")["activity"]["phase"] == "OPEN"
            assert next_of_type(ws, "dashboard.state")["dashboard"]["phase"] == "OPEN"


def test_open_pushes_each_student_its_own_snapshot(app, client, student_client):
    a = create_activity(client)
    add_member(app, a["id"], 2, "小明", "tok-joined")
    joined, anon = student_client(), student_client()
    with joined.websocket_connect("/ws/student", headers=cookie("tok-joined")) as wj, \
            anon.websocket_connect("/ws/student") as wa:
        first = wj.receive_json()["state"]
        assert first["activity"]["phase"] == "DRAFT" and first["membership"]["groupNumber"] == 2
        assert wa.receive_json()["state"] == anonymous_state(a, "DRAFT")

        open_activity(client, a)

        mine = next_of_type(wj, "student.state")["state"]
        assert mine["activity"]["phase"] == "OPEN"
        assert [u["unitId"] for u in mine["activity"]["units"]] == [u["id"] for u in a["units"]]
        assert mine["membership"] == {"groupNumber": 2, "displayName": "小明"}
        assert next_of_type(wa, "student.state")["state"] == anonymous_state(a, "OPEN")
