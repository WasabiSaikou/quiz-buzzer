"""Student REST contract (002 contracts/rest-api.md › Student API; FR-009 – FR-020)."""

from __future__ import annotations

import pytest

from tests.live_helpers import create_activity, open_activity


def walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


def join(s, activity, group=1, name="小明"):
    return s.post("/api/student/join",
                  json={"activityId": activity["id"], "groupNumber": group, "displayName": name})


def body_for(unit, texts=None):
    texts = texts or [f"t{s['subPart']}" for s in unit["slots"]]
    return {"unitId": unit["id"],
            "answers": [{"subPart": s["subPart"], "text": t} for s, t in zip(unit["slots"], texts, strict=True)]}


def group_set(activity):
    return next(u for u in activity["units"] if len(u["slots"]) == 2)


def single(activity):
    return next(u for u in activity["units"] if len(u["slots"]) == 1)


# --- join ---------------------------------------------------------------------------------


def test_join_201_sets_participant_cookie(client, student_client):
    a = create_activity(client)
    s = student_client()
    r = join(s, a, 3, " 小明 ")
    assert r.status_code == 201
    assert r.json()["membership"] == {"groupNumber": 3, "displayName": "小明"}
    assert r.json()["activity"]["phase"] == "DRAFT"
    cookie = r.headers["set-cookie"].lower()
    assert cookie.startswith("qb_participant=")
    for attr in ("httponly", "samesite=strict", "path=/", "max-age=43200"):
        assert attr in cookie, attr
    assert s.get("/api/student/state").json() == r.json()


@pytest.mark.parametrize("group, name, field, maxv", [
    (0, "小明", "groupNumber", 6), (7, "小明", "groupNumber", 6), ("2", "小明", "groupNumber", 6),
    (1, "", "displayName", 20), (1, "　", "displayName", 20), (1, "名" * 21, "displayName", 20),
])
def test_join_invalid_422(client, student_client, group, name, field, maxv):
    a = create_activity(client)
    r = join(student_client(), a, group, name)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_join"
    assert err["details"] == {"field": field, "max": maxv}


def test_join_refused_without_current_activity(student_client):
    r = student_client().post("/api/student/join",
                              json={"activityId": 1, "groupNumber": 1, "displayName": "小明"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "join_refused"
    assert r.json()["error"]["details"] == {"phase": None}


def test_already_joined_409(client, student_client):
    a = create_activity(client)
    s = student_client()
    join(s, a)
    r = join(s, a, 2)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_joined"


# --- change group -----------------------------------------------------------------------------


def test_leave_204_clears_cookie_in_draft(client, student_client):
    a = create_activity(client)
    s = student_client()
    join(s, a)
    r = s.delete("/api/student/membership")
    assert r.status_code == 204
    assert "qb_participant=" in r.headers["set-cookie"]
    assert s.get("/api/student/state").json()["membership"] is None
    assert join(s, a, 4).status_code == 201


def test_leave_refused_once_open(client, student_client):
    a = create_activity(client)
    s = student_client()
    join(s, a)
    open_activity(client, a)
    r = s.delete("/api/student/membership")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "group_change_refused"
    assert err["details"] == {"phase": "OPEN"}
    assert err["message"] == "Groups are fixed once the activity has opened."


def test_leave_without_cookie_401(client, student_client):
    create_activity(client)
    r = student_client().delete("/api/student/membership")
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_a_member"


# --- submissions ------------------------------------------------------------------------------


def test_submit_201_shape_without_rank(client, student_client):
    a = create_activity(client)
    s = student_client()
    join(s, a, 2, "阿美")
    open_activity(client, a)
    u = group_set(a)
    r = s.post("/api/student/submissions", json=body_for(u, [" 光合作用 ", "葉綠體"]))
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["unitId"] == u["id"] and out["unitNumber"] == u["number"]
    assert out["answers"] == [{"subPart": 1, "text": "光合作用"}, {"subPart": 2, "text": "葉綠體"}]
    assert out["submittedBy"] == "阿美" and out["receivedAt"].endswith("Z")
    assert not {"rank", "isWinner"} & set(walk_keys(out))


def test_submit_errors_in_contract_order(client, student_client):
    a = create_activity(client)
    s = student_client()
    u = single(a)

    # 422 invalid_answers runs before anything else, even without a membership.
    r = s.post("/api/student/submissions", json=body_for(u, ["   "]))
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_answers"
    assert err["details"] == {"subParts": [1], "reasons": {"1": "empty"}}

    r = s.post("/api/student/submissions", json=body_for(u))
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_a_member"

    join(s, a, 1)
    r = s.post("/api/student/submissions", json=body_for(u))
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_open"
    assert r.json()["error"]["message"] == "The activity has not opened yet."

    open_activity(client, a)
    r = s.post("/api/student/submissions", json={"unitId": 99999, "answers": [{"subPart": 1, "text": "x"}]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unit_not_found"

    assert s.post("/api/student/submissions", json=body_for(u, ["first"])).status_code == 201
    r = s.post("/api/student/submissions", json=body_for(u, ["second"]))
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "already_submitted"
    assert err["message"] == f"Your group has already submitted question {u['number']}."
    assert err["details"]["submission"]["answers"] == [{"subPart": 1, "text": "first"}]
    assert not {"rank", "isWinner"} & set(walk_keys(err))


def test_submit_after_close_is_activity_ended(app, client, student_client):
    a = create_activity(client)
    s = student_client()
    join(s, a, 1)
    open_activity(client, a)
    from tests.live_helpers import set_db_phase

    set_db_phase(app.state.db_path, a["id"], "CLOSED")  # US3 adds POST …/end
    r = s.post("/api/student/submissions", json=body_for(single(a)))
    assert r.status_code == 409
    assert r.json()["error"] == {"code": "activity_ended", "message": "The activity has ended."}


def test_group_comes_from_the_cookie_not_the_body(client, student_client):
    a = create_activity(client)
    s = student_client()
    join(s, a, 2)
    open_activity(client, a)
    body = body_for(single(a)) | {"groupNumber": 5}
    assert s.post("/api/student/submissions", json=body).status_code == 201
    other = student_client()
    join(other, a, 5)
    # Group 5 has not submitted: the extra field was ignored, the submission belongs to group 2.
    assert other.post("/api/student/submissions", json=body_for(single(a))).status_code == 201


def test_teammates_cannot_resubmit(client, student_client):
    a = create_activity(client)
    s1, s2 = student_client(), student_client()
    join(s1, a, 3, "阿美")
    join(s2, a, 3, "小明")
    open_activity(client, a)
    assert s1.post("/api/student/submissions", json=body_for(single(a))).status_code == 201
    r = s2.post("/api/student/submissions", json=body_for(single(a)))
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_submitted"
