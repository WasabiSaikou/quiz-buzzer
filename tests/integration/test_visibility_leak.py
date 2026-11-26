"""SC-005 leak test (Constitution III; FR-023, FR-024): visibility, tests first.

One recording student in group 1 keeps every WebSocket message and every HTTP response it
receives during a full OPEN activity in which groups 2-6 submit every unit with unique marker
answers and names. Until the activity is CLOSED nothing about other groups may reach it:
no marker, no name, no rank, no other group number, and not even a message at the moment
another group submits (timing would leak that someone answered).
"""

from __future__ import annotations

import json

from tests.live_helpers import cookie, create_activity, next_of_type, open_activity, recv

OTHER_GROUPS = (2, 3, 4, 5, 6)


def walk(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path, k, v
            yield from walk(v, path + (k,))
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v, path)


def assert_no_message(ws, timeout=0.3):
    """Pushes are delivered before the HTTP response that caused them returns."""
    try:
        message = recv(ws, timeout=timeout)
    except AssertionError:
        return
    raise AssertionError(f"unexpected message to the recorder: {message}")


def answers(unit, text):
    return [{"subPart": s["subPart"], "text": f"{text}-{s['subPart']}"} for s in unit["slots"]]


def test_one_student_never_learns_anything_about_other_groups(client, student_client):
    a = create_activity(client, group_count=6)
    recorded = []  # everything the recorder receives

    rec = student_client()
    r = rec.post("/api/student/join", json={"activityId": a["id"], "groupNumber": 1, "displayName": "REC"})
    recorded.append(r.json())
    token = r.cookies["qb_participant"]

    others = {}
    for g in OTHER_GROUPS:
        s = student_client()
        assert s.post("/api/student/join", json={
            "activityId": a["id"], "groupNumber": g, "displayName": f"name-g{g}"}).status_code == 201
        others[g] = s

    with rec.websocket_connect("/ws/student", headers=cookie(token)) as ws:
        recorded.append(recv(ws))
        open_activity(client, a)
        recorded.append(next_of_type(ws, "student.state"))

        first = a["units"][0]
        r = rec.post("/api/student/submissions", json={"unitId": first["id"], "answers": answers(first, "own")})
        assert r.status_code == 201
        recorded.append(r.json())
        recorded.append(next_of_type(ws, "student.state"))  # own group's update: expected

        for unit in a["units"]:
            for g, s in others.items():
                r = s.post("/api/student/submissions",
                           json={"unitId": unit["id"], "answers": answers(unit, f"LEAK-g{g}-u{unit['number']}")})
                assert r.status_code == 201, r.text
                assert_no_message(ws)  # not even a message at that moment

        # The recorder's own errors while other groups' submissions exist.
        r = rec.post("/api/student/submissions", json={"unitId": first["id"], "answers": answers(first, "again")})
        assert r.json()["error"]["code"] == "already_submitted"
        recorded.append(r.json())
        second = a["units"][1]
        bad = [{"subPart": s["subPart"], "text": "  "} for s in second["slots"]]
        r = rec.post("/api/student/submissions", json={"unitId": second["id"], "answers": bad})
        assert r.json()["error"]["code"] == "invalid_answers"
        recorded.append(r.json())
        recorded.append(rec.get("/api/student/state").json())
        assert_no_message(ws)

        text = json.dumps(recorded, ensure_ascii=False)
        for g in OTHER_GROUPS:
            assert f"LEAK-g{g}" not in text, g
            assert f"name-g{g}" not in text, g
        for path, key, value in walk(recorded):
            assert key not in {"rank", "isWinner", "count", "total"}, (path, key)
            if key == "groupNumber":
                assert path[-1:] == ("membership",) and value == 1, (path, value)

        # After CLOSED the student still sees only its own group (results for all are 003).
        assert client.post(f"/api/teacher/activities/{a['id']}/end").status_code == 200
        closed = next_of_type(ws, "student.state")
    assert closed["state"]["activity"]["phase"] == "CLOSED"
    assert "LEAK-g" not in json.dumps(closed, ensure_ascii=False)
