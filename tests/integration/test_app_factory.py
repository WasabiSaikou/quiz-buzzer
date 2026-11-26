"""create_app starts with the fake adapter; errors use the contract envelope (rest-api.md)."""

from pydantic import BaseModel

from quizbuzzer import db
from quizbuzzer.realtime.hub import RealtimeHub
from quizbuzzer.services.sheets_adapter import (
    InvalidSheetUrl,
    SheetNotFound,
    SheetNotShared,
    SheetsUnavailable,
)


def test_app_starts_and_creates_schema(client, db_path, fake_adapter, app):
    assert app.state.adapter is fake_adapter
    assert isinstance(app.state.hub, RealtimeHub) and len(app.state.hub) == 0
    conn = db.connect(db_path)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    finally:
        conn.close()
    assert {"activities", "question_units", "answer_slots", "one_current_activity"} <= names


def test_teacher_page_is_served(client):
    r = client.get("/teacher")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")


def _add_raising_route(app, exc):
    @app.get("/_raise")
    def _raise():
        raise exc


def _check(client, status, code):
    r = client.get("/_raise")
    assert r.status_code == status
    body = r.json()
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    return body["error"]


def test_invalid_url_maps_to_400(app, client):
    _add_raising_route(app, InvalidSheetUrl("not a sheets link"))
    _check(client, 400, "invalid_url")


def test_not_shared_maps_to_403_with_email(app, client):
    _add_raising_route(app, SheetNotShared("sa@example-project.iam.gserviceaccount.com"))
    err = _check(client, 403, "not_shared")
    assert err["details"] == {"serviceAccountEmail": "sa@example-project.iam.gserviceaccount.com"}


def test_not_found_maps_to_404(app, client):
    _add_raising_route(app, SheetNotFound("x"))
    _check(client, 404, "not_found")


def test_sheets_unavailable_maps_to_502(app, client):
    _add_raising_route(app, SheetsUnavailable("timeout"))
    _check(client, 502, "sheets_unavailable")


def test_request_validation_uses_envelope(app, client):
    class Body(BaseModel):
        url: str

    @app.post("/_body")
    def _body(body: Body):
        return {}

    r = client.post("/_body", json={})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"
    assert r.json()["error"]["details"] == {"fields": ["url"]}


def test_student_page_is_served_and_root_redirects(anon_client):
    r = anon_client.get("/student")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    r = anon_client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/student"
