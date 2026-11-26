"""Shared fixtures: fake Sheets adapter, temp DB file, app + TestClient (research R9)."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quizbuzzer.config import Settings
from quizbuzzer.main import create_app
from tests.fakes.fake_sheets_adapter import FIXTURES_DIR, FakeSheetsAdapter

EDGE_CASES_DIR = FIXTURES_DIR / "edge_cases"
TEST_PASSCODE = "test-passcode"


@pytest.fixture
def fake_adapter() -> FakeSheetsAdapter:
    return FakeSheetsAdapter(FIXTURES_DIR)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    # A real file (not :memory:) so concurrency tests can open several connections.
    return tmp_path / "quizbuzzer-test.db"


@pytest.fixture
def settings(db_path: Path) -> Settings:
    # Never read the developer's real .env or credentials in tests.
    return Settings(
        credentials_path=None,
        db_path=db_path,
        host="127.0.0.1",
        port=8000,
        teacher_passcode=TEST_PASSCODE,
    )


@pytest.fixture
def app(fake_adapter: FakeSheetsAdapter, db_path: Path, settings: Settings):
    return create_app(adapter=fake_adapter, db_path=db_path, settings=settings)


@pytest.fixture
def client(app) -> TestClient:
    """An unlocked teacher client (002 research R9): 001's tests run unchanged behind the guard."""
    with TestClient(app) as c:
        r = c.post("/api/teacher/session", json={"passcode": TEST_PASSCODE})
        assert r.status_code == 204, r.text
        yield c


@pytest.fixture
def anon_client(app) -> TestClient:
    """A client with no cookies at all: a student page or a crafted request (002 FR-002)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def student_client(app):
    """Factory of separate TestClients (separate cookie jars) on the same app (002 research R9)."""
    with contextlib.ExitStack() as stack:

        def _make() -> TestClient:
            return stack.enter_context(TestClient(app))

        yield _make


def ws_headers(c: TestClient) -> dict[str, str]:
    """Cookie header built from a client's jar, for WebSocket connects (002 research R9)."""
    cookie = "; ".join(f"{name}={value}" for name, value in c.cookies.items())
    return {"cookie": cookie} if cookie else {}


@pytest.fixture
def load_grid():
    """Load an edge-case grid: tests/fixtures/sheets/edge_cases/<name>.json = {grid, merges}."""

    def _load(name: str) -> tuple[list[list[str]], list[tuple[int, int, int, int]]]:
        data = json.loads((EDGE_CASES_DIR / f"{name}.json").read_text(encoding="utf-8"))
        merges = [tuple(m) for m in data.get("merges", [])]
        return data["grid"], merges

    return _load
