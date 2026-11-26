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
