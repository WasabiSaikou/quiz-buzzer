"""Shared helpers for feature 002 integration tests (not a test module)."""

from __future__ import annotations

from typing import Any

GROUP = "https://docs.google.com/spreadsheets/d/template_group/edit"
SINGLE = "https://docs.google.com/spreadsheets/d/template_single/edit"
PASSCODE = "test-passcode"


def create_activity(client, url: str = GROUP, sheet_id: int = 0, group_count: int = 6) -> dict:
    """Create a DRAFT activity through the 001 API (teacher client)."""
    fp = client.post("/api/teacher/import/preview", json={"url": url, "sheetId": sheet_id}).json()[
        "fingerprint"
    ]
    r = client.post(
        "/api/teacher/activities",
        json={
            "url": url,
            "sheetId": sheet_id,
            "groupCount": group_count,
            "fingerprint": fp,
            "acknowledgeWarnings": True,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def reimport_same_tab(client, activity: dict, url: str = GROUP, sheet_id: int = 0) -> dict:
    fp = client.post("/api/teacher/import/preview", json={"url": url, "sheetId": sheet_id}).json()[
        "fingerprint"
    ]
    r = client.put(
        f"/api/teacher/activities/{activity['id']}/questions",
        json={"url": url, "sheetId": sheet_id, "fingerprint": fp, "acknowledgeWarnings": True},
    )
    assert r.status_code == 200, r.text
    return r.json()


def student_state(state: dict[str, Any]) -> dict[str, Any]:
    return {"type": "student.state", "state": state}


def no_activity_state() -> dict[str, Any]:
    return {"activity": None, "membership": None, "group": None}


def anonymous_state(activity: dict, phase: str | None = None) -> dict[str, Any]:
    return {
        "activity": {
            "id": activity["id"],
            "phase": phase or activity["phase"],
            "groupCount": activity["groupCount"],
        },
        "membership": None,
        "group": None,
    }


def next_of_type(ws, message_type: str, limit: int = 10) -> dict[str, Any]:
    """Receive until a message of `message_type` arrives (skipping other snapshot types).

    Only call this when such a message is certain to come: WebSocket receives block.
    """
    for _ in range(limit):
        message = ws.receive_json()
        if message["type"] == message_type:
            return message
    raise AssertionError(f"no {message_type} within {limit} messages")


def add_member(app, activity_id: int, group_number: int, name: str, token: str) -> int:
    """Create a participant directly (T015 db helper) with a known cookie token."""
    from quizbuzzer import db
    from quizbuzzer.services.participation_service import hash_token

    conn = db.connect(app.state.db_path)
    try:
        return db.insert_participant(
            conn,
            activity_id=activity_id,
            group_number=group_number,
            display_name=name,
            token_hash=hash_token(token),
            joined_at="2026-11-27T01:00:00Z",
        )
    finally:
        conn.close()


def cookie(token: str) -> dict[str, str]:
    return {"cookie": f"qb_participant={token}"}


def open_activity(client, activity: dict) -> dict:
    r = client.post(f"/api/teacher/activities/{activity['id']}/open")
    assert r.status_code == 200, r.text
    return r.json()
