"""GET /api/teacher/activities/{id}/results.csv (003 T026; contracts/rest-api.md; FR-019)."""

from __future__ import annotations

import re
from urllib.parse import unquote

from quizbuzzer.services.csv_export import to_csv
from tests.live_helpers import create_activity, open_activity


def join(student_client, a, g):
    s = student_client()
    r = s.post("/api/student/join", json={"activityId": a["id"], "groupNumber": g, "displayName": f"名{g}"})
    assert r.status_code == 201, r.text
    return s


def closed_with_answers(client, student_client):
    a = create_activity(client, group_count=6)
    s2 = join(student_client, a, 2)
    open_activity(client, a)
    unit = a["units"][2]  # single
    r = s2.post("/api/student/submissions",
                json={"unitId": unit["id"], "answers": [{"subPart": 1, "text": "=1+1, \"x\""}]})
    assert r.status_code == 201
    assert client.post(f"/api/teacher/activities/{a['id']}/end").status_code == 200
    return a


def test_csv_download_for_closed_activity(client, student_client, app):
    a = closed_with_answers(client, student_client)
    r = client.get(f"/api/teacher/activities/{a['id']}/results.csv")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    expected = to_csv(app.state.results.teacher_results(a["id"]))
    assert r.content == expected
    assert r.content.startswith(b"\xef\xbb\xbf")
    disposition = r.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert f'filename="activity-{a["id"]}.csv"' in disposition
    m = re.search(r"filename\*=UTF-8''([^;]+)", disposition)
    assert m, disposition
    name = unquote(m.group(1))
    assert name.startswith(f"activity-{a['id']}-") and name.endswith(".csv")
    assert not set('\\/:*?"<>|') & set(name)


def test_csv_refused_while_open(client):
    a = create_activity(client)
    open_activity(client, a)
    r = client.get(f"/api/teacher/activities/{a['id']}/results.csv")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "phase_conflict" and err["details"] == {"phase": "OPEN"}
    assert "downloaded" in err["message"]


def test_csv_refused_while_draft(client):
    a = create_activity(client)
    r = client.get(f"/api/teacher/activities/{a['id']}/results.csv")
    assert r.status_code == 409 and r.json()["error"]["details"] == {"phase": "DRAFT"}


def test_csv_unknown_activity(client):
    r = client.get("/api/teacher/activities/999/results.csv")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_csv_filename_strips_unsafe_characters():
    from quizbuzzer.services.results_service import csv_filename

    ascii_name, utf8_name = csv_filename(7, 'a/b\\c:d*e?f"g<h>i|j\x01k – 講義')
    assert ascii_name == "activity-7.csv"
    assert utf8_name.startswith("activity-7-") and utf8_name.endswith(".csv")
    assert not set('\\/:*?"<>|\x01') & set(utf8_name)
    assert "講義" in utf8_name
    long_name = csv_filename(7, "長" * 200)[1]
    assert len(long_name) <= len("activity-7-") + 60 + len(".csv")
