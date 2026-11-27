"""Push latency at classroom scale (002 SC-001, SC-002): 60 student sockets, 12 groups, 2 teachers.

Pushes are delivered before the HTTP response that caused them returns, so the measured time
covers the server's work plus delivery into every socket.
"""

from __future__ import annotations

import contextlib
import time

from tests.live_helpers import add_member, cookie, create_activity, next_of_type, recv

GROUPS = 12
PER_GROUP = 5  # 60 student sockets


def test_phase_change_and_submission_reach_everyone_within_one_second(app, client, student_client):
    a = create_activity(client, group_count=GROUPS)
    tokens = {}
    for g in range(1, GROUPS + 1):
        for i in range(PER_GROUP):
            token = f"tok-{g}-{i}"
            add_member(app, a["id"], g, f"s{g}-{i}", token)
            tokens[(g, i)] = token
    s = student_client()
    with contextlib.ExitStack() as stack:
        students = {key: stack.enter_context(s.websocket_connect("/ws/student", headers=cookie(t)))
                    for key, t in tokens.items()}
        teachers = [stack.enter_context(client.websocket_connect("/ws/teacher")) for _ in range(2)]
        for ws in students.values():
            recv(ws)
        for ws in teachers:
            next_of_type(ws, "dashboard.state")

        started = time.monotonic()
        assert client.post(f"/api/teacher/activities/{a['id']}/open").status_code == 200
        for ws in students.values():
            assert next_of_type(ws, "student.state")["state"]["activity"]["phase"] == "OPEN"
        for ws in teachers:
            next_of_type(ws, "dashboard.state")
        open_seconds = time.monotonic() - started
        print(f"OPEN reached 60 student + 2 teacher sockets in {open_seconds:.3f} s")
        assert open_seconds < 1.0, f"OPEN reached all 62 sockets in {open_seconds:.3f} s"

        submitter = student_client()
        unit = next(u for u in a["units"] if len(u["slots"]) == 1)
        started = time.monotonic()
        r = submitter.post("/api/student/submissions", headers=cookie(tokens[(7, 0)]),
                           json={"unitId": unit["id"], "answers": [{"subPart": 1, "text": "x"}]})
        assert r.status_code == 201, r.text
        for ws in teachers:
            next_of_type(ws, "dashboard.state")
        for i in range(PER_GROUP):
            next_of_type(students[(7, i)], "student.state")
        submit_seconds = time.monotonic() - started
        print(f"submission reached 2 teacher + 5 group sockets in {submit_seconds:.3f} s")
        assert submit_seconds < 1.0, f"submission reached teachers + group in {submit_seconds:.3f} s"

        # 003 SC-001 (T035): the CLOSED snapshot now carries the full results for every member.
        for g in range(1, GROUPS + 1):
            for u in a["units"]:
                answers = [{"subPart": sl["subPart"], "text": f"g{g}"} for sl in u["slots"]]
                if g == 7 and u["id"] == unit["id"]:
                    continue  # already submitted above
                r = submitter.post("/api/student/submissions", headers=cookie(tokens[(g, 0)]),
                                   json={"unitId": u["id"], "answers": answers})
                assert r.status_code == 201, r.text
        for ws in teachers:  # drain the submission pushes
            while True:
                try:
                    recv(ws, timeout=0.2)
                except AssertionError:
                    break
        for ws in students.values():
            while True:
                try:
                    recv(ws, timeout=0.05)
                except AssertionError:
                    break
        started = time.monotonic()
        assert client.post(f"/api/teacher/activities/{a['id']}/end").status_code == 200
        for ws in students.values():
            state = next_of_type(ws, "student.state")["state"]
            assert state["activity"]["phase"] == "CLOSED"
            assert len(state["results"]["units"]) == len(a["units"])
        close_seconds = time.monotonic() - started
        print(f"CLOSED with results reached 60 student sockets in {close_seconds:.3f} s")
        assert close_seconds < 1.0, f"CLOSED with results reached all students in {close_seconds:.3f} s"
