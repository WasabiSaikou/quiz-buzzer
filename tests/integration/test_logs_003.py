"""No answer text or display names in logs during results, export and CSV (003 T034, FR-024)."""

from __future__ import annotations

import logging

from tests.live_helpers import create_activity, open_activity

SENTINEL = "zq9SENTINEL003x"
SID = "template_group"


def test_results_export_and_csv_log_no_student_data(client, student_client, fake_adapter, caplog):
    caplog.set_level(logging.DEBUG)
    a = create_activity(client)
    s = student_client()
    r = s.post("/api/student/join", json={
        "activityId": a["id"], "groupNumber": 1, "displayName": f"名-{SENTINEL}"})
    assert r.status_code == 201
    open_activity(client, a)
    unit = a["units"][2]  # single
    body = {"unitId": unit["id"], "answers": [{"subPart": 1, "text": f"=ans-{SENTINEL}"}]}
    assert s.post("/api/student/submissions", json=body).status_code == 201
    assert client.post(f"/api/teacher/activities/{a['id']}/end").status_code == 200

    s.get("/api/student/state")
    assert client.get(f"/api/teacher/activities/{a['id']}/results").status_code == 200
    assert client.get(f"/api/teacher/activities/{a['id']}/results.csv").status_code == 200
    assert client.post(f"/api/teacher/activities/{a['id']}/export").status_code == 200

    grid = fake_adapter.read_tab(SID, 0).grid
    del grid[10]  # the winning question disappears: blocked export
    fake_adapter.replace_tab(SID, 0, grid)
    assert client.post(f"/api/teacher/activities/{a['id']}/export").status_code == 409

    assert caplog.records, "expected some log records to inspect"
    assert any("export" in rec.getMessage() for rec in caplog.records)
    for record in caplog.records:
        assert SENTINEL not in record.getMessage(), (record.name, record.getMessage())
