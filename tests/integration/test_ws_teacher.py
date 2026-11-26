"""WebSocket contract: /ws/teacher pushes activity.state (contracts/websocket.md; Principle IV)."""

from __future__ import annotations

GROUP = "https://docs.google.com/spreadsheets/d/template_group/edit"


def create(client, group_count=6):
    fp = client.post(
        "/api/teacher/import/preview", json={"url": GROUP, "sheetId": 0}
    ).json()["fingerprint"]
    r = client.post(
        "/api/teacher/activities",
        json={"url": GROUP, "sheetId": 0, "groupCount": group_count, "fingerprint": fp},
    )
    assert r.status_code == 201, r.text
    return r.json()


def summary(a):
    return {
        "id": a["id"],
        "title": a["title"],
        "phase": a["phase"],
        "groupCount": a["groupCount"],
        "totals": a["totals"],
        "importedAt": a["importedAt"],
    }


def test_connect_receives_null_state(client):
    with client.websocket_connect("/ws/teacher") as ws:
        assert ws.receive_json() == {"type": "activity.state", "activity": None}


def test_connect_receives_current_state(client):
    a = create(client)
    with client.websocket_connect("/ws/teacher") as ws:
        assert ws.receive_json() == {"type": "activity.state", "activity": summary(a)}


def test_create_pushes_to_every_teacher_socket(client):
    with client.websocket_connect("/ws/teacher") as ws1, client.websocket_connect("/ws/teacher") as ws2:
        ws1.receive_json()
        ws2.receive_json()
        a = create(client)
        expected = {"type": "activity.state", "activity": summary(a)}
        assert ws1.receive_json() == expected
        assert ws2.receive_json() == expected


def test_client_frames_are_ignored(client):
    with client.websocket_connect("/ws/teacher") as ws:
        ws.receive_json()
        ws.send_text("hello")
        ws.send_json({"type": "phase.set", "phase": "OPEN"})
        a = create(client)
        assert ws.receive_json()["activity"]["id"] == a["id"]
        assert a["phase"] == "DRAFT"


def test_disconnected_socket_is_dropped(client, app):
    with client.websocket_connect("/ws/teacher") as ws:
        ws.receive_json()
    create(client)  # must not fail although the socket is gone
    assert len(app.state.hub) == 0
