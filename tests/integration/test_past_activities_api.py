"""Past CLOSED activities (003 T031; FR-023; contracts/rest-api.md)."""

from __future__ import annotations

from tests.integration.test_teacher_guard import teacher_routes
from tests.live_helpers import create_activity, open_activity


def close(client, a):
    open_activity(client, a)
    assert client.post(f"/api/teacher/activities/{a['id']}/end").status_code == 200


def test_closed_list_newest_first_and_open_one(client):
    a = create_activity(client)
    close(client, a)
    b = create_activity(client, url="https://docs.google.com/spreadsheets/d/template_single/edit")
    close(client, b)
    c = create_activity(client)  # DRAFT: never listed
    r = client.get("/api/teacher/activities/closed")
    assert r.status_code == 200, r.text
    listed = r.json()["activities"]
    assert [x["id"] for x in listed] == [b["id"], a["id"]]
    assert c["id"] not in [x["id"] for x in listed]
    assert set(listed[0]) == {"id", "title", "createdAt", "groupCount", "unitCount", "submissionCount"}
    assert listed[0]["unitCount"] == 6 and listed[1]["unitCount"] == 4
    assert listed[0]["submissionCount"] == 0
    older = client.get(f"/api/teacher/activities/{a['id']}/results").json()
    assert older["activityId"] == a["id"] and older["title"] == a["title"]
    assert [u["number"] for u in older["units"]] == [1, 2, 3, 4]


def test_closed_list_empty(client):
    r = client.get("/api/teacher/activities/closed")
    assert r.status_code == 200 and r.json() == {"activities": []}


def test_003_routes_are_in_the_guarded_set(app):
    paths = {(route.path, method) for route, method in teacher_routes(app)}
    assert {
        ("/api/teacher/activities/closed", "GET"),
        ("/api/teacher/activities/{activity_id}/results", "GET"),
        ("/api/teacher/activities/{activity_id}/export", "POST"),
        ("/api/teacher/activities/{activity_id}/results.csv", "GET"),
    } <= paths
