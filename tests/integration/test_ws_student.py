"""/ws/student and GET /api/student/state snapshots (002 contracts/websocket.md › /ws/student).

State part (T008): snapshots on connect, after create and after re-import (FR-008, FR-031).
"""

from __future__ import annotations

from tests.live_helpers import (
    anonymous_state,
    create_activity,
    no_activity_state,
    reimport_same_tab,
    student_state,
)


def test_connect_without_activity_gets_null_state(student_client):
    s = student_client()
    with s.websocket_connect("/ws/student") as ws:
        assert ws.receive_json() == student_state(no_activity_state())


def test_create_pushes_draft_state_to_every_student_socket(client, student_client):
    s1, s2 = student_client(), student_client()
    with s1.websocket_connect("/ws/student") as w1, s2.websocket_connect("/ws/student") as w2:
        w1.receive_json()
        w2.receive_json()
        a = create_activity(client)
        expected = student_state(anonymous_state(a, "DRAFT"))
        assert w1.receive_json() == expected
        assert w2.receive_json() == expected


def test_reimport_pushes_a_fresh_snapshot(client, student_client):
    a = create_activity(client)
    s = student_client()
    with s.websocket_connect("/ws/student") as ws:
        assert ws.receive_json() == student_state(anonymous_state(a, "DRAFT"))
        reimport_same_tab(client, a)
        assert ws.receive_json() == student_state(anonymous_state(a, "DRAFT"))


def test_http_state_equals_socket_snapshot(client, student_client):
    s = student_client()
    assert s.get("/api/student/state").json() == no_activity_state()
    a = create_activity(client)
    with s.websocket_connect("/ws/student") as ws:
        snapshot = ws.receive_json()["state"]
    assert s.get("/api/student/state").json() == snapshot == anonymous_state(a, "DRAFT")


def test_student_state_needs_no_teacher_cookie(anon_client):
    r = anon_client.get("/api/student/state")
    assert r.status_code == 200
    assert r.json() == no_activity_state()
