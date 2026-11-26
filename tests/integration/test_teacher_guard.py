"""Teacher guard: every /api/teacher/* route and /ws/teacher need the passcode (002 FR-001–FR-003, SC-006).

contracts/rest-api.md › Teacher access; contracts/websocket.md › /ws/teacher.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from starlette.websockets import WebSocketDisconnect

PASSCODE = "test-passcode"
TEACHER_REQUIRED = {"error": {"code": "teacher_required", "message": "Teacher passcode required."}}

# 001 routes that must stay in the guarded set (so the list cannot silently shrink).
ROUTES_001 = {
    "import_tabs",
    "import_preview",
    "create_activity",
    "current_activity",
    "get_activity",
    "reimport_preview",
    "replace_questions",
}


def all_api_routes(routes):
    """Flatten included routers (FastAPI wraps them; their routes keep the router prefix)."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):
            yield from all_api_routes(route.original_router.routes)


def teacher_routes(app):
    for route in all_api_routes(app.routes):
        if route.path.startswith("/api/teacher"):
            if route.path == "/api/teacher/session":
                continue
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                yield route, method


def test_guarded_set_includes_every_001_route(app):
    names = {route.name for route, _ in teacher_routes(app)}
    assert ROUTES_001 <= names, ROUTES_001 - names


def test_every_teacher_route_needs_the_passcode(app, anon_client):
    checked = 0
    for route, method in teacher_routes(app):
        path = route.path.replace("{activity_id}", "1")
        # A malformed body must still get 401, never a 422 that echoes field names.
        r = anon_client.request(
            method, path, content=b"{not json", headers={"content-type": "application/json"}
        )
        assert r.status_code == 401, (method, path, r.status_code, r.text)
        assert r.json() == TEACHER_REQUIRED, (method, path)
        checked += 1
    assert checked >= len(ROUTES_001)


def test_unknown_teacher_path_is_also_guarded(anon_client):
    r = anon_client.get("/api/teacher/does-not-exist")
    assert r.status_code == 401
    assert r.json() == TEACHER_REQUIRED


def test_wrong_passcode_is_refused_without_cookie(anon_client):
    r = anon_client.post("/api/teacher/session", json={"passcode": "nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "wrong_passcode"
    assert "details" not in r.json()["error"]
    assert "set-cookie" not in r.headers
    assert anon_client.get("/api/teacher/activities/current").status_code == 401


def test_right_passcode_sets_session_cookie(anon_client):
    r = anon_client.post("/api/teacher/session", json={"passcode": PASSCODE})
    assert r.status_code == 204
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("qb_teacher=")
    lowered = cookie.lower()
    assert "httponly" in lowered
    assert "samesite=strict" in lowered
    assert "path=/" in lowered
    assert "max-age" not in lowered and "expires" not in lowered
    assert PASSCODE not in r.text and PASSCODE not in str(r.headers)
    assert anon_client.get("/api/teacher/activities/current").status_code == 200


@pytest.mark.parametrize("body", [{}, {"passcode": 123}, None])
def test_session_body_validation(anon_client, body):
    r = anon_client.post("/api/teacher/session", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


def test_teacher_socket_without_cookie_is_closed_4401(anon_client):
    with anon_client.websocket_connect("/ws/teacher") as ws:
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
    assert info.value.code == 4401


def test_teacher_socket_with_cookie_receives_state(anon_client):
    anon_client.post("/api/teacher/session", json={"passcode": PASSCODE})
    with anon_client.websocket_connect("/ws/teacher") as ws:
        assert ws.receive_json()["type"] == "activity.state"
