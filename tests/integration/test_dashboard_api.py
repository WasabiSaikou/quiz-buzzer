"""Dashboard, End and the displayed activity over REST + WebSocket (002 US3; FR-026 – FR-029).

contracts/rest-api.md › Dashboard, POST …/end, Change to 001; contracts/websocket.md.
"""

from __future__ import annotations

from tests.live_helpers import (
    SINGLE,
    cookie,
    create_activity,
    next_of_type,
    open_activity,
    recv,
)


def join(s, activity, group, name):
    r = s.post("/api/student/join",
               json={"activityId": activity["id"], "groupNumber": group, "displayName": name})
    assert r.status_code == 201, r.text
    return r


def submit(s, unit, texts=None):
    texts = texts or [f"t{x['subPart']}" for x in unit["slots"]]
    return s.post("/api/student/submissions", json={
        "unitId": unit["id"],
        "answers": [{"subPart": x["subPart"], "text": t} for x, t in zip(unit["slots"], texts, strict=True)],
    })


def single(activity):
    return next(u for u in activity["units"] if len(u["slots"]) == 1)


def end(client, activity):
    r = client.post(f"/api/teacher/activities/{activity['id']}/end")
    assert r.status_code == 200, r.text
    return r.json()


def test_get_dashboard_200_and_404(client):
    a = create_activity(client)
    r = client.get(f"/api/teacher/activities/{a['id']}/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert (d["activityId"], d["phase"], d["groupCount"]) == (a["id"], "DRAFT", 6)
    assert [u["unitId"] for u in d["units"]] == [u["id"] for u in a["units"]]
    assert [g["memberCount"] for g in d["groups"]] == [0] * 6
    r = client.get("/api/teacher/activities/999/dashboard")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_every_teacher_tab_gets_dashboard_updates(client, student_client):
    a = create_activity(client)
    with client.websocket_connect("/ws/teacher") as t1, client.websocket_connect("/ws/teacher") as t2:
        for ws in (t1, t2):
            next_of_type(ws, "dashboard.state")  # on connect, after activity.state
        s1, s2 = student_client(), student_client()

        join(s1, a, 1, "小明")
        for ws in (t1, t2):
            assert next_of_type(ws, "dashboard.state")["dashboard"]["groups"][0]["members"] == ["小明"]

        join(s2, a, 2, "阿美")
        s2.delete("/api/student/membership")  # leave in DRAFT
        for ws in (t1, t2):
            next_of_type(ws, "dashboard.state")  # after join of s2
            assert next_of_type(ws, "dashboard.state")["dashboard"]["groups"][1]["memberCount"] == 0

        open_activity(client, a)
        for ws in (t1, t2):
            assert next_of_type(ws, "dashboard.state")["dashboard"]["phase"] == "OPEN"

        assert submit(s1, single(a), ["答案"]).status_code == 201
        for ws in (t1, t2):
            d = next_of_type(ws, "dashboard.state")["dashboard"]
            row = next(u for u in d["units"] if u["unitId"] == single(a)["id"])["submissions"][0]
            assert (row["rank"], row["isWinner"], row["groupNumber"], row["submittedBy"]) == (1, True, 1, "小明")
            assert row["answers"] == [{"subPart": 1, "text": "答案"}] and row["receivedAt"]

        end(client, a)
        for ws in (t1, t2):
            assert next_of_type(ws, "activity.state")["activity"]["phase"] == "CLOSED"
            assert next_of_type(ws, "dashboard.state")["dashboard"]["phase"] == "CLOSED"


def test_end_errors(client):
    a = create_activity(client)
    r = client.post(f"/api/teacher/activities/{a['id']}/end")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "phase_conflict" and err["details"] == {"phase": "DRAFT"}
    assert "Cancel activity" in err["message"]
    open_activity(client, a)
    end(client, a)
    r = client.post(f"/api/teacher/activities/{a['id']}/end")
    assert r.status_code == 409 and r.json()["error"]["details"] == {"phase": "CLOSED"}
    assert client.post("/api/teacher/activities/999/end").status_code == 404


def test_end_moves_students_to_closed_with_own_submissions_only(client, student_client):
    a = create_activity(client)
    s1, s2 = student_client(), student_client()
    t1 = join(s1, a, 1, "小明").cookies["qb_participant"]
    t2 = join(s2, a, 2, "阿美").cookies["qb_participant"]
    open_activity(client, a)
    assert submit(s1, single(a), ["mine-1"]).status_code == 201
    assert submit(s2, single(a), ["other-2"]).status_code == 201
    with s1.websocket_connect("/ws/student", headers=cookie(t1)) as w1, \
            s2.websocket_connect("/ws/student", headers=cookie(t2)) as w2:
        recv(w1)
        recv(w2)
        end(client, a)
        st1 = next_of_type(w1, "student.state")["state"]
        st2 = next_of_type(w2, "student.state")["state"]
    assert st1["activity"] == {"id": a["id"], "phase": "CLOSED", "groupCount": 6}
    assert [s["answers"][0]["text"] for s in st1["group"]["submissions"]] == ["mine-1"]
    assert [s["answers"][0]["text"] for s in st2["group"]["submissions"]] == ["other-2"]
    assert "other-2" not in repr(st1) and "mine-1" not in repr(st2)
    r = submit(s1, next(u for u in a["units"] if len(u["slots"]) == 2))
    assert r.status_code == 409 and r.json()["error"]["code"] == "activity_ended"


def test_final_dashboard_survives_refresh(client):
    a = create_activity(client)
    open_activity(client, a)
    end(client, a)
    current = client.get("/api/teacher/activities/current").json()["activity"]
    assert current["id"] == a["id"] and current["phase"] == "CLOSED"
    with client.websocket_connect("/ws/teacher") as ws:
        assert recv(ws)["activity"]["phase"] == "CLOSED"
        assert recv(ws)["dashboard"]["phase"] == "CLOSED"


def test_import_after_end_through_the_api(client):
    a = create_activity(client)
    open_activity(client, a)
    end(client, a)
    closed_before = client.get(f"/api/teacher/activities/{a['id']}").json()
    new = create_activity(client, url=SINGLE)  # 201: a CLOSED activity never blocks (FR-020a)
    assert new["id"] != a["id"] and new["phase"] == "DRAFT"
    assert client.get("/api/teacher/activities/current").json()["activity"] == new
    assert client.get(f"/api/teacher/activities/{a['id']}").json() == closed_before
