"""No passcode, tokens, display names or answer text in logs (002 FR-004, FR-032; Principle VI)."""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from quizbuzzer.config import Settings
from quizbuzzer.main import create_app
from tests.live_helpers import create_activity, open_activity

SENTINEL = "zq9SENTINELx7"


def test_full_flow_logs_contain_no_student_data_or_secrets(fake_adapter, db_path, caplog):
    passcode = f"pass-{SENTINEL}"
    settings = Settings(credentials_path=None, db_path=db_path, host="127.0.0.1", port=8000,
                        teacher_passcode=passcode)
    app = create_app(adapter=fake_adapter, db_path=db_path, settings=settings)
    caplog.set_level(logging.DEBUG)
    secrets_seen = [passcode]
    with TestClient(app) as teacher, TestClient(app) as student:
        teacher.post("/api/teacher/session", json={"passcode": f"wrong-{SENTINEL}"})
        r = teacher.post("/api/teacher/session", json={"passcode": passcode})
        secrets_seen.append(r.cookies["qb_teacher"])
        a = create_activity(teacher)
        r = student.post("/api/student/join", json={
            "activityId": a["id"], "groupNumber": 1, "displayName": f"名-{SENTINEL}"})
        secrets_seen.append(r.cookies["qb_participant"])
        student.post("/api/student/join", json={  # refused: already joined
            "activityId": a["id"], "groupNumber": 2, "displayName": f"名2-{SENTINEL}"})
        open_activity(teacher, a)
        unit = next(u for u in a["units"] if len(u["slots"]) == 1)
        body = {"unitId": unit["id"], "answers": [{"subPart": 1, "text": f"ans-{SENTINEL}"}]}
        assert student.post("/api/student/submissions", json=body).status_code == 201
        student.post("/api/student/submissions", json=body)  # refused: already submitted
        student.post("/api/student/submissions", json={  # refused: too long
            "unitId": unit["id"], "answers": [{"subPart": 1, "text": SENTINEL * 30}]})
        teacher.post(f"/api/teacher/activities/{a['id']}/end")
        student.get("/api/student/state")

    assert caplog.records, "expected some log records to inspect"
    for record in caplog.records:
        text = record.getMessage()
        assert SENTINEL not in text, (record.name, text)
        for secret in secrets_seen:
            assert secret not in text, record.name
