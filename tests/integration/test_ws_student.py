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


# --- US4 (T042): teammates' live view and refresh / reconnect recovery ---------------------

import time  # noqa: E402

from tests.live_helpers import cookie, next_of_type, open_activity, recv  # noqa: E402


def _join(s, activity, group, name):
    r = s.post("/api/student/join",
               json={"activityId": activity["id"], "groupNumber": group, "displayName": name})
    assert r.status_code == 201, r.text
    return r.cookies["qb_participant"]


def _single(activity):
    return next(u for u in activity["units"] if len(u["slots"]) == 1)


def test_teammates_see_a_submission_live(client, student_client):
    a = create_activity(client)
    s1, s2 = student_client(), student_client()
    t1, t2 = _join(s1, a, 3, "阿美"), _join(s2, a, 3, "小明")
    open_activity(client, a)
    with s1.websocket_connect("/ws/student", headers=cookie(t1)) as w1, \
            s2.websocket_connect("/ws/student", headers=cookie(t2)) as w2:
        recv(w1)
        recv(w2)
        u = _single(a)
        r = s1.post("/api/student/submissions",
                    json={"unitId": u["id"], "answers": [{"subPart": 1, "text": "答案"}]})
        assert r.status_code == 201
        for ws in (w1, w2):
            subs = next_of_type(ws, "student.state")["state"]["group"]["submissions"]
            assert [(x["unitId"], x["submittedBy"], x["answers"]) for x in subs] == [
                (u["id"], "阿美", [{"subPart": 1, "text": "答案"}])
            ]


def test_member_list_updates_on_join_and_leave(client, student_client):
    a = create_activity(client)
    s1, s2 = student_client(), student_client()
    t1 = _join(s1, a, 2, "阿美")
    with s1.websocket_connect("/ws/student", headers=cookie(t1)) as w1:
        assert recv(w1)["state"]["group"]["members"] == ["阿美"]
        _join(s2, a, 2, "小明")
        assert next_of_type(w1, "student.state")["state"]["group"]["members"] == ["阿美", "小明"]
        assert s2.delete("/api/student/membership").status_code == 204  # DRAFT: change group
        assert next_of_type(w1, "student.state")["state"]["group"]["members"] == ["阿美"]


def test_student_recovers_state_after_refresh_and_missed_phase_changes(client, student_client):
    a = create_activity(client)
    s = student_client()
    token = _join(s, a, 4, "小華")
    open_activity(client, a)
    u = _single(a)
    assert s.post("/api/student/submissions",
                  json={"unitId": u["id"], "answers": [{"subPart": 1, "text": "mine"}]}).status_code == 201

    def snapshot():
        started = time.monotonic()
        with s.websocket_connect("/ws/student", headers=cookie(token)) as ws:
            state = recv(ws)["state"]
        assert time.monotonic() - started < 3.0  # SC-007
        assert s.get("/api/student/state").json() == state  # same state over HTTP
        return state

    live = snapshot()  # a "refresh": a brand-new socket, no join, no body
    assert live["membership"] == {"groupNumber": 4, "displayName": "小華"}
    assert live["activity"]["phase"] == "OPEN" and live["activity"]["units"]
    assert [x["unitId"] for x in live["group"]["submissions"]] == [u["id"]]

    # Disconnected while the teacher ends the activity: the next socket shows the new phase.
    assert client.post(f"/api/teacher/activities/{a['id']}/end").status_code == 200
    after = snapshot()
    assert after["activity"]["phase"] == "CLOSED"
    assert after["membership"] == live["membership"]
    assert after["group"]["submissions"] == live["group"]["submissions"]


def test_student_recovers_open_phase_missed_while_disconnected(client, student_client):
    a = create_activity(client)
    s = student_client()
    token = _join(s, a, 1, "小明")
    with s.websocket_connect("/ws/student", headers=cookie(token)) as ws:
        assert recv(ws)["state"]["activity"]["phase"] == "DRAFT"
    open_activity(client, a)  # nobody connected
    with s.websocket_connect("/ws/student", headers=cookie(token)) as ws:
        state = recv(ws)["state"]
    assert state["activity"]["phase"] == "OPEN" and state["activity"]["units"]


def test_teacher_recovers_the_live_state_on_reconnect(client, student_client):
    a = create_activity(client)
    s = student_client()
    _join(s, a, 1, "小明")
    open_activity(client, a)
    with client.websocket_connect("/ws/teacher") as ws:
        first = (recv(ws), recv(ws))
    started = time.monotonic()
    with client.websocket_connect("/ws/teacher") as ws:
        again = (recv(ws), recv(ws))
    assert time.monotonic() - started < 3.0
    assert again == first
    assert again[0]["activity"]["phase"] == "OPEN"
    assert again[1]["dashboard"] == client.get(f"/api/teacher/activities/{a['id']}/dashboard").json()
