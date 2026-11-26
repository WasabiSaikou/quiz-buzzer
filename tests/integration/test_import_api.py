"""REST contract: /api/teacher/import/* (US1) and /api/teacher/activities (US2)."""

from __future__ import annotations

import pytest

from quizbuzzer.services.sheets_adapter import SheetNotFound, SheetNotShared, SheetsUnavailable

SHIFTED = "https://docs.google.com/spreadsheets/d/shifted_layout/edit"
SINGLE = "https://docs.google.com/spreadsheets/d/template_single/edit"
GROUP = "https://docs.google.com/spreadsheets/d/template_group/edit"
NO_HEADER_GRID = [["題目", "答案"], ["1", ""]]


def preview(client, url, sheet_id):
    r = client.post("/api/teacher/import/preview", json={"url": url, "sheetId": sheet_id})
    assert r.status_code == 200, r.text
    return r.json()


# --- US1 ------------------------------------------------------------------------------------


def test_tabs_preselects_gid(client):
    r = client.post("/api/teacher/import/tabs", json={"url": SHIFTED + "#gid=918273645"})
    assert r.status_code == 200
    assert r.json() == {
        "spreadsheetId": "shifted_layout",
        "spreadsheetTitle": "Shifted Layout 測試",
        "tabs": [
            {"sheetId": 0, "title": "講義", "index": 0},
            {"sheetId": 918273645, "title": "練習", "index": 1},
        ],
        "preselectedSheetId": 918273645,
    }


def test_tabs_preselects_first_tab(client):
    r = client.post("/api/teacher/import/tabs", json={"url": SINGLE})
    assert r.json()["preselectedSheetId"] == 0


def test_preview_shape(client):
    body = preview(client, GROUP, 0)
    assert body["spreadsheetId"] == "template_group"
    assert body["sheetId"] == 0
    assert body["tabTitle"] == "Sheet1"
    assert body["header"] == {"row": 4, "numberColumn": 2, "answerColumn": 7}
    assert body["units"][0] == {
        "number": 1,
        "kind": "GROUP_SET",
        "sourceRow": 5,
        "slots": [
            {"subPart": 1, "a1Ref": "G5", "row": 5, "column": 7},
            {"subPart": 2, "a1Ref": "G6", "row": 6, "column": 7},
        ],
    }
    assert body["totals"] == {"units": 4, "slots": 6, "errors": 0, "warnings": 0}
    assert body["issues"] == []
    assert len(body["fingerprint"]) == 64
    assert body["canConfirm"] is True


def test_preview_with_errors_still_returns_200(client, fake_adapter):
    fake_adapter.replace_tab("template_single", 0, NO_HEADER_GRID)
    body = preview(client, SINGLE, 0)
    assert body["canConfirm"] is False
    assert body["header"] is None
    assert body["issues"][0]["code"] == "header_not_found"
    assert body["issues"][0]["severity"] == "error"
    assert body["totals"]["errors"] == 1


def test_selecting_another_tab_rebuilds_preview(client):
    first = preview(client, SHIFTED, 0)
    second = preview(client, SHIFTED, 918273645)
    assert first["totals"]["units"] == 2 and first["tabTitle"] == "講義"
    assert second["totals"]["units"] == 6 and second["tabTitle"] == "練習"
    assert first["fingerprint"] != second["fingerprint"]


@pytest.mark.parametrize("path", ["/api/teacher/import/tabs", "/api/teacher/import/preview"])
def test_invalid_url_400(client, fake_adapter, path):
    r = client.post(path, json={"url": "https://example.com/x", "sheetId": 0})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_url"
    assert fake_adapter.calls == []


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (SheetNotShared("sa@example-project.iam.gserviceaccount.com"), 403, "not_shared"),
        (SheetNotFound("x"), 404, "not_found"),
        (SheetsUnavailable("x"), 502, "sheets_unavailable"),
    ],
)
@pytest.mark.parametrize("path", ["/api/teacher/import/tabs", "/api/teacher/import/preview"])
def test_adapter_errors(client, fake_adapter, exc, status, code, path):
    fake_adapter.fail_with(exc)
    r = client.post(path, json={"url": SINGLE, "sheetId": 0})
    assert r.status_code == status
    err = r.json()["error"]
    assert err["code"] == code
    if code == "not_shared":
        assert err["details"]["serviceAccountEmail"] == "sa@example-project.iam.gserviceaccount.com"


def test_unknown_tab_404(client):
    r = client.post("/api/teacher/import/preview", json={"url": SINGLE, "sheetId": 777})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_import_never_writes_to_sheet(client, fake_adapter):
    before = fake_adapter.snapshot()
    client.post("/api/teacher/import/tabs", json={"url": SHIFTED})
    preview(client, SHIFTED, 0)
    preview(client, SHIFTED, 918273645)
    preview(client, GROUP, 0)
    assert fake_adapter.snapshot() == before


# --- US2: POST /api/teacher/activities, GET current / {id} ---------------------------------

WARNING_GRID = [["題號", "作答"], ["1", "答：______"], ["2", ""]]


def slots_of(units):
    return [
        (u["number"], u["kind"], u["sourceRow"], [(s["subPart"], s["a1Ref"], s["row"], s["column"]) for s in u["slots"]])
        for u in units
    ]


def create(client, url=GROUP, sheet_id=0, group_count=6, ack=False, fingerprint=None):
    if fingerprint is None:
        fingerprint = preview(client, url, sheet_id)["fingerprint"]
    return client.post(
        "/api/teacher/activities",
        json={
            "url": url,
            "sheetId": sheet_id,
            "groupCount": group_count,
            "fingerprint": fingerprint,
            "acknowledgeWarnings": ack,
        },
    )


def test_create_activity_201(client):
    p = preview(client, GROUP, 0)
    r = create(client, fingerprint=p["fingerprint"])
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["phase"] == "DRAFT" and a["groupCount"] == 6
    assert a["title"] == "template_group – Sheet1"
    assert a["source"] == {"spreadsheetId": "template_group", "sheetId": 0, "tabTitle": "Sheet1"}
    assert a["createdAt"] == a["importedAt"]
    assert a["totals"] == {"units": 4, "slots": 6}
    assert slots_of(a["units"]) == slots_of(p["units"])
    assert [u["position"] for u in a["units"]] == [0, 1, 2, 3]
    assert all(isinstance(u["id"], int) for u in a["units"])
    assert all(isinstance(s["id"], int) for u in a["units"] for s in u["slots"])


@pytest.mark.parametrize("bad", [1, 13, "six", None])
def test_create_invalid_group_count_422(client, bad):
    r = create(client, group_count=bad)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_group_count"
    assert "2" in err["message"] and "12" in err["message"]


def test_create_import_errors_422(client, fake_adapter):
    fake_adapter.replace_tab("template_single", 0, NO_HEADER_GRID)
    r = create(client, SINGLE)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "import_errors"
    assert err["details"]["preview"]["canConfirm"] is False


def test_create_warnings_not_acknowledged_422(client, fake_adapter):
    fake_adapter.replace_tab("template_single", 0, WARNING_GRID)
    r = create(client, SINGLE, ack=False)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "warnings_not_acknowledged"
    assert create(client, SINGLE, ack=True).status_code == 201


def test_create_preview_changed_409(client, fake_adapter):
    fp = preview(client, SINGLE, 0)["fingerprint"]
    grid = fake_adapter.read_tab("template_single", 0).grid + [["", "7", "新題目"]]
    fake_adapter.replace_tab("template_single", 0, grid)
    r = create(client, SINGLE, fingerprint=fp)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "preview_changed"
    assert err["details"]["preview"]["totals"]["units"] == 7
    assert client.get("/api/teacher/activities/current").json() == {"activity": None}


def test_create_when_current_exists_409(client):
    first = create(client).json()
    r = create(client, SINGLE)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "current_activity_exists"
    assert err["details"]["activity"] == {"id": first["id"], "title": first["title"], "phase": "DRAFT"}
    assert "re-import" in err["message"].lower()


def test_get_current_and_by_id(client):
    assert client.get("/api/teacher/activities/current").json() == {"activity": None}
    created = create(client).json()
    assert client.get("/api/teacher/activities/current").json() == {"activity": created}
    assert client.get(f"/api/teacher/activities/{created['id']}").json() == created
    r = client.get("/api/teacher/activities/999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_create_missing_fields_uses_envelope(client):
    r = client.post("/api/teacher/activities", json={"url": GROUP})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


def test_create_never_writes_to_sheet(client, fake_adapter):
    before = fake_adapter.snapshot()
    assert create(client).status_code == 201
    assert fake_adapter.snapshot() == before


# --- Polish: log hygiene (Principle VI) and preview performance (SC-001) -------------------

SENTINEL = "SENTINEL-秘密-7f3a9c"


def test_logs_never_contain_cell_text_or_credentials(
    fake_adapter, db_path, tmp_path, caplog, monkeypatch
):
    import logging

    from fastapi.testclient import TestClient

    from quizbuzzer.config import Settings
    from quizbuzzer.main import create_app

    key_path = tmp_path / f"key-{SENTINEL}.json"
    settings = Settings(credentials_path=key_path, db_path=db_path, host="127.0.0.1", port=8000)
    grid = [
        ["題號", "題目", "作答"],
        ["1", f"question text {SENTINEL}", f"答：{SENTINEL}"],  # -> slot_cell_has_text warning
        ["", "", f"note {SENTINEL}"],  # -> stray_answer_text warning
        ["2", f"{SENTINEL}", "（1）"],
        ["", "", f"（2）{SENTINEL}"],
    ]
    fake_adapter.add_spreadsheet(
        "logcheck", f"Book {SENTINEL}",
        [
            {"sheetId": 0, "title": f"Tab {SENTINEL}", "index": 0, "grid": grid},
            {"sheetId": 1, "title": "Other", "index": 1, "grid": [["題號", "作答"], ["1", SENTINEL]]},
        ],
    )
    url = "https://docs.google.com/spreadsheets/d/logcheck/edit"
    caplog.set_level(logging.DEBUG)
    with TestClient(create_app(adapter=fake_adapter, db_path=db_path, settings=settings)) as c:
        c.post("/api/teacher/import/tabs", json={"url": url})
        p = c.post("/api/teacher/import/preview", json={"url": url, "sheetId": 0}).json()
        assert any(SENTINEL in i["message"] for i in p["issues"])  # the teacher does see it
        a = c.post("/api/teacher/activities", json={
            "url": url, "sheetId": 0, "groupCount": 4, "fingerprint": p["fingerprint"],
            "acknowledgeWarnings": True}).json()
        c.post("/api/teacher/activities", json={  # refused: current activity exists
            "url": url, "sheetId": 0, "groupCount": 4, "fingerprint": p["fingerprint"],
            "acknowledgeWarnings": True})
        p2 = c.post(f"/api/teacher/activities/{a['id']}/reimport/preview",
                    json={"url": url, "sheetId": 1}).json()
        c.put(f"/api/teacher/activities/{a['id']}/questions", json={
            "url": url, "sheetId": 1, "fingerprint": p2["fingerprint"], "acknowledgeWarnings": False})
        fake_adapter.fail_with(SheetNotShared("sa@example.com"))
        c.post("/api/teacher/import/preview", json={"url": url, "sheetId": 0})

    assert caplog.records, "expected some log records to inspect"
    for record in caplog.records:
        text = record.getMessage()
        assert SENTINEL not in text, record.name
        assert str(key_path) not in text, record.name


def test_preview_of_200_row_sheet_is_fast(client, fake_adapter):
    import time

    grid = [["", "題號", "題目", "", "作答"]]
    n = 1
    while len(grid) < 201:  # 200 rows below the header: singles, 題組 and spacer rows
        if n % 3 == 0:
            grid += [["", str(n), f"q{n}", "", "（1）"], ["", "", "", "", "（2）"], ["", "", "", "", "（3）"]]
        else:
            grid += [["", str(n), f"q{n}", "", ""]]
        grid.append([])
        n += 1
    grid = grid[:201]
    fake_adapter.add_spreadsheet(
        "big", "Big", [{"sheetId": 0, "title": "Sheet1", "index": 0, "grid": grid}]
    )
    start = time.perf_counter()
    body = preview(client, "https://docs.google.com/spreadsheets/d/big/edit", 0)
    elapsed = time.perf_counter() - start
    assert body["totals"]["units"] > 50
    # SC-001 allows 5 s end to end; local parse + HTTP must leave almost all of it for Google.
    assert elapsed < 1.0, f"preview took {elapsed:.3f}s"
