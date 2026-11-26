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
