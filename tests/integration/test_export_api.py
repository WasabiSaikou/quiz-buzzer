"""POST /api/teacher/activities/{id}/export end to end on the fake sheet (003 T019).

contracts/rest-api.md › export. The fake adapter is both reader and writer (conftest).
"""

from __future__ import annotations

import pytest

from quizbuzzer.services.sheets_adapter import SheetNotShared, SheetsUnavailable
from tests.fakes.fake_sheets_adapter import FAKE_SERVICE_ACCOUNT_EMAIL
from tests.live_helpers import create_activity, open_activity

SID = "template_group"  # units 1, 2 題組 (G5/G6, G8/G9); 3 single G11; 4 single G13


def join(student_client, a, g):
    s = student_client()
    r = s.post("/api/student/join", json={"activityId": a["id"], "groupNumber": g, "displayName": f"名{g}"})
    assert r.status_code == 201, r.text
    return s


def submit(s, unit, texts):
    answers = [{"subPart": sl["subPart"], "text": t} for sl, t in zip(unit["slots"], texts, strict=True)]
    r = s.post("/api/student/submissions", json={"unitId": unit["id"], "answers": answers})
    assert r.status_code == 201, r.text


def end(client, a):
    assert client.post(f"/api/teacher/activities/{a['id']}/end").status_code == 200


def export(client, a):
    return client.post(f"/api/teacher/activities/{a['id']}/export")


@pytest.fixture
def played(client, student_client):
    a = create_activity(client, group_count=6)
    s2, s5 = join(student_client, a, 2), join(student_client, a, 5)
    open_activity(client, a)
    u1, _u2, u3, _u4 = a["units"]
    submit(s5, u1, ["甲", "乙"])  # winner of unit 1
    submit(s2, u1, ["LOSER", "LOSER"])
    submit(s2, u3, ["=1+1"])  # winner of unit 3
    end(client, a)
    return a


def grid(fake_adapter):
    return fake_adapter.read_tab(SID, 0).grid


def test_export_writes_winners_at_new_cells_and_reports(client, fake_adapter, played):
    g = grid(fake_adapter)
    fake_adapter.replace_tab(SID, 0, [[], []] + g)  # two rows inserted above everything
    r = export(client, played)
    assert r.status_code == 200, r.text
    assert r.json() == {"cellsWritten": 3, "unitsWritten": 2, "unitsSkipped": 2}
    after = grid(fake_adapter)
    assert after[6][6] == "（1）甲" and after[7][6] == "（2）乙"  # G7, G8
    assert after[12][6] == "=1+1"  # G13, stored as text
    assert after[9][6] == "（1）" and after[10][6] == "（2）"  # unit 2 untouched
    assert "LOSER" not in repr(after)


def test_repeated_export_gives_the_same_result(client, fake_adapter, played):
    first = export(client, played).json()
    snap = fake_adapter.snapshot()
    second = export(client, played).json()
    assert first == second and fake_adapter.snapshot() == snap
    assert len(fake_adapter.writes) == 2


def test_blocked_export_lists_problems_and_writes_nothing(client, fake_adapter, played):
    g = grid(fake_adapter)
    del g[10]  # unit 3 (winner) deleted
    del g[5]  # unit 1 sub-part 2 deleted
    fake_adapter.replace_tab(SID, 0, g)
    before = fake_adapter.snapshot()
    r = export(client, played)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "export_blocked"
    assert [(p["kind"], p["questionNumber"], p["subPart"]) for p in err["details"]["problems"]] == [
        ("missing_sub_part", 1, 2),
        ("missing_question", 3, None),
    ]
    assert fake_adapter.writes == [] and fake_adapter.snapshot() == before


def test_parse_error_problem_carries_the_001_code(client, fake_adapter, played):
    g = grid(fake_adapter)
    g[7][1] = "1"  # duplicate question number
    fake_adapter.replace_tab(SID, 0, g)
    err = export(client, played).json()["error"]
    assert err["code"] == "export_blocked"
    assert all(p["kind"] == "parse_error" and p["code"] for p in err["details"]["problems"])
    assert fake_adapter.writes == []


def test_view_only_names_the_service_account(client, fake_adapter, played):
    fake_adapter.make_read_only(SID)
    r = export(client, played)
    assert r.status_code == 403
    err = r.json()["error"]
    assert err["code"] == "sheet_read_only"
    assert err["details"] == {"serviceAccountEmail": FAKE_SERVICE_ACCOUNT_EMAIL}
    assert "Editor" in err["message"]
    assert fake_adapter.writes == []


def test_not_shared_names_the_service_account(client, fake_adapter, played):
    fake_adapter.fail_with(SheetNotShared(FAKE_SERVICE_ACCOUNT_EMAIL))
    r = export(client, played)
    fake_adapter.fail_with(None)
    assert r.status_code == 403
    err = r.json()["error"]
    assert err["code"] == "export_not_shared"
    assert err["details"] == {"serviceAccountEmail": FAKE_SERVICE_ACCOUNT_EMAIL}
    assert "Editor" in err["message"]


def test_tab_gone_is_not_found(client, fake_adapter, played):
    fake_adapter.delete_tab(SID, 0)
    r = export(client, played)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_google_down_is_sheets_unavailable(client, fake_adapter, played):
    fake_adapter.fail_with(SheetsUnavailable("down"))
    r = export(client, played)
    fake_adapter.fail_with(None)
    assert r.status_code == 502 and r.json()["error"]["code"] == "sheets_unavailable"


@pytest.mark.parametrize("phase", ["DRAFT", "OPEN"])
def test_refused_before_closed(client, fake_adapter, phase):
    a = create_activity(client)
    if phase == "OPEN":
        open_activity(client, a)
    r = export(client, a)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "phase_conflict" and err["details"] == {"phase": phase}
    assert fake_adapter.writes == []


def test_unknown_activity(client):
    r = client.post("/api/teacher/activities/999/export")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_zero_submissions_writes_nothing(client, fake_adapter):
    a = create_activity(client)
    open_activity(client, a)
    end(client, a)
    r = export(client, a)
    assert r.status_code == 200
    assert r.json() == {"cellsWritten": 0, "unitsWritten": 0, "unitsSkipped": 4}
    assert fake_adapter.writes == []
