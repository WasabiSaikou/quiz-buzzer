"""REST contract: re-import into a DRAFT activity (US3; contracts/rest-api.md)."""

from __future__ import annotations

import pytest

from quizbuzzer import db

URL = "https://docs.google.com/spreadsheets/d/reimport/edit"
NO_HEADER_GRID = [["題目", "答案"], ["1", ""]]
WARNING_GRID = [["題號", "作答"], ["1", "答：______"], ["2", ""]]


def numbered_grid(n):
    return [["題號", "作答"]] + [[str(i), ""] for i in range(1, n + 1)]


@pytest.fixture(autouse=True)
def reimport_sheet(fake_adapter):
    fake_adapter.add_spreadsheet(
        "reimport",
        "Re-import Book",
        [
            {"sheetId": 0, "title": "Five", "index": 0, "grid": numbered_grid(5)},
            {"sheetId": 5, "title": "Seven", "index": 1, "grid": numbered_grid(7)},
        ],
    )
    return fake_adapter


@pytest.fixture
def draft(client):
    fp = client.post("/api/teacher/import/preview", json={"url": URL, "sheetId": 0}).json()["fingerprint"]
    r = client.post(
        "/api/teacher/activities",
        json={"url": URL, "sheetId": 0, "groupCount": 5, "fingerprint": fp},
    )
    assert r.status_code == 201
    return r.json()


def reimport_preview(client, activity_id, sheet_id=5):
    return client.post(
        f"/api/teacher/activities/{activity_id}/reimport/preview",
        json={"url": URL, "sheetId": sheet_id},
    )


def put_questions(client, activity_id, fingerprint, sheet_id=5, ack=False):
    return client.put(
        f"/api/teacher/activities/{activity_id}/questions",
        json={"url": URL, "sheetId": sheet_id, "fingerprint": fingerprint, "acknowledgeWarnings": ack},
    )


def set_phase(db_path, activity_id, phase):
    conn = db.connect(db_path)
    try:
        conn.execute("UPDATE activities SET phase = ? WHERE id = ?", (phase, activity_id))
    finally:
        conn.close()


def test_reimport_preview_200(client, draft):
    r = reimport_preview(client, draft["id"])
    assert r.status_code == 200
    body = r.json()
    assert body["tabTitle"] == "Seven" and body["totals"]["units"] == 7 and body["canConfirm"]


def test_put_questions_replaces_set(client, draft):
    fp = reimport_preview(client, draft["id"]).json()["fingerprint"]
    r = put_questions(client, draft["id"], fp)
    assert r.status_code == 200, r.text
    a = r.json()
    assert [u["number"] for u in a["units"]] == [1, 2, 3, 4, 5, 6, 7]
    assert (a["phase"], a["groupCount"], a["id"], a["createdAt"]) == (
        "DRAFT", 5, draft["id"], draft["createdAt"])
    assert a["source"] == {"spreadsheetId": "reimport", "sheetId": 5, "tabTitle": "Seven"}
    assert not {u["id"] for u in a["units"]} & {u["id"] for u in draft["units"]}
    assert client.get(f"/api/teacher/activities/{draft['id']}").json() == a


@pytest.mark.parametrize("phase", ["OPEN", "CLOSED"])
def test_reimport_refused_409(client, db_path, draft, phase):
    fp = client.post("/api/teacher/import/preview", json={"url": URL, "sheetId": 5}).json()["fingerprint"]
    set_phase(db_path, draft["id"], phase)
    for r in (reimport_preview(client, draft["id"]), put_questions(client, draft["id"], fp)):
        assert r.status_code == 409
        err = r.json()["error"]
        assert err["code"] == "reimport_refused"
        assert err["details"] == {"phase": phase}
        assert phase in err["message"]
    units = client.get(f"/api/teacher/activities/{draft['id']}").json()["units"]
    assert len(units) == 5


def test_put_rechecks_phase_at_confirm(client, db_path, draft):
    fp = reimport_preview(client, draft["id"]).json()["fingerprint"]
    set_phase(db_path, draft["id"], "OPEN")
    r = put_questions(client, draft["id"], fp)
    assert r.status_code == 409 and r.json()["error"]["code"] == "reimport_refused"


def test_put_preview_changed_409(client, reimport_sheet, draft):
    fp = reimport_preview(client, draft["id"]).json()["fingerprint"]
    reimport_sheet.replace_tab("reimport", 5, numbered_grid(8))
    r = put_questions(client, draft["id"], fp)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "preview_changed" and err["details"]["preview"]["totals"]["units"] == 8


def test_put_import_errors_422(client, reimport_sheet, draft):
    reimport_sheet.replace_tab("reimport", 5, NO_HEADER_GRID)
    fp = reimport_preview(client, draft["id"]).json()["fingerprint"]
    r = put_questions(client, draft["id"], fp)
    assert r.status_code == 422 and r.json()["error"]["code"] == "import_errors"


def test_put_warnings_not_acknowledged_422(client, reimport_sheet, draft):
    reimport_sheet.replace_tab("reimport", 5, WARNING_GRID)
    fp = reimport_preview(client, draft["id"]).json()["fingerprint"]
    r = put_questions(client, draft["id"], fp, ack=False)
    assert r.status_code == 422 and r.json()["error"]["code"] == "warnings_not_acknowledged"
    assert put_questions(client, draft["id"], fp, ack=True).status_code == 200


def test_unknown_activity_404(client):
    fp = client.post("/api/teacher/import/preview", json={"url": URL, "sheetId": 5}).json()["fingerprint"]
    for r in (reimport_preview(client, 999), put_questions(client, 999, fp)):
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"


def test_replace_pushes_activity_state(client, draft):
    fp = reimport_preview(client, draft["id"]).json()["fingerprint"]
    with client.websocket_connect("/ws/teacher") as ws:
        assert ws.receive_json()["activity"]["totals"] == {"units": 5, "slots": 5}
        assert put_questions(client, draft["id"], fp).status_code == 200
        msg = ws.receive_json()
        assert msg["type"] == "activity.state"
        assert msg["activity"]["id"] == draft["id"]
        assert msg["activity"]["totals"] == {"units": 7, "slots": 7}


def test_reimport_never_writes_to_sheet(client, reimport_sheet, draft):
    before = reimport_sheet.snapshot()
    fp = reimport_preview(client, draft["id"]).json()["fingerprint"]
    assert put_questions(client, draft["id"], fp).status_code == 200
    assert reimport_sheet.snapshot() == before
