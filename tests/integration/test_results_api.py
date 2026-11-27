"""Results over HTTP and WebSocket (003 T009, T020; contracts/rest-api.md).

Student part: results only for members of a CLOSED activity, through student.state.
Teacher part: GET /api/teacher/activities/{id}/results.
"""

from __future__ import annotations

from tests.live_helpers import cookie, create_activity, next_of_type, open_activity, recv


def join(student_client, activity, group, name):
    s = student_client()
    r = s.post("/api/student/join", json={"activityId": activity["id"], "groupNumber": group, "displayName": name})
    assert r.status_code == 201, r.text
    return s, r.cookies["qb_participant"]


def submit(s, unit, text):
    answers = [{"subPart": sl["subPart"], "text": f"{text}-{sl['subPart']}"} for sl in unit["slots"]]
    r = s.post("/api/student/submissions", json={"unitId": unit["id"], "answers": answers})
    assert r.status_code == 201, r.text


def end(client, activity):
    r = client.post(f"/api/teacher/activities/{activity['id']}/end")
    assert r.status_code == 200, r.text


def played(client, student_client):
    """template_group: units 1, 2 are 題組 (2 sub-parts), 3, 4 single. Groups 4, 1, 6 answer
    unit 2 in that order; nobody answers units 3 and 4; group 3 joins but never submits."""
    a = create_activity(client, group_count=6)
    students = {g: join(student_client, a, g, f"名{g}") for g in (4, 1, 6, 3)}
    open_activity(client, a)
    unit2 = a["units"][1]
    for g in (4, 1, 6):
        submit(students[g][0], unit2, f"g{g}")
    return a, students


# --- Student part (US1) -----------------------------------------------------------------------


def test_member_who_never_submitted_sees_full_results_after_close(client, student_client):
    a, students = played(client, student_client)
    end(client, a)
    state = students[3][0].get("/api/student/state").json()
    units = state["results"]["units"]
    assert [u["number"] for u in units] == [1, 2, 3, 4]
    unit2 = units[1]
    assert [(e["rank"], e["groupNumber"], e["isWinner"]) for e in unit2["submissions"]] == [
        (1, 4, True), (2, 1, False), (3, 6, False),
    ]
    assert unit2["submissions"][0]["answers"] == [
        {"subPart": 1, "text": "g4-1"}, {"subPart": 2, "text": "g4-2"},
    ]
    assert units[0]["submissions"] == [] and units[2]["submissions"] == []  # 無人作答
    assert "名4" not in str(state["results"])  # no submitter names for students


def test_connected_student_receives_results_in_the_closed_push(client, student_client):
    a, students = played(client, student_client)
    s3, token3 = students[3]
    with s3.websocket_connect("/ws/student", headers=cookie(token3)) as ws:
        recv(ws)  # snapshot on connect (OPEN)
        end(client, a)
        closed = next_of_type(ws, "student.state")
    assert closed["state"]["activity"]["phase"] == "CLOSED"
    assert [e["groupNumber"] for e in closed["state"]["results"]["units"][1]["submissions"]] == [4, 1, 6]


def test_browser_without_membership_gets_no_results(client, student_client, anon_client):
    a, _ = played(client, student_client)
    end(client, a)
    state = anon_client.get("/api/student/state").json()
    assert "results" not in state


def test_no_results_key_while_open(client, student_client):
    a, students = played(client, student_client)
    state = students[4][0].get("/api/student/state").json()
    assert state["activity"]["phase"] == "OPEN"
    assert "results" not in state


def test_refresh_after_close_returns_results(client, student_client):
    a, students = played(client, student_client)
    end(client, a)
    s1 = students[1][0]
    first = s1.get("/api/student/state").json()
    again = s1.get("/api/student/state").json()
    assert first == again and "results" in again
