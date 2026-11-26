"""Two simultaneous confirmations create exactly one current activity (FR-020a; research R7)."""

from __future__ import annotations

import sqlite3
import threading

import pytest

from quizbuzzer import db
from quizbuzzer.services.activity_service import ActivityService, CurrentActivityExists

GROUP = "https://docs.google.com/spreadsheets/d/template_group/edit"
SINGLE = "https://docs.google.com/spreadsheets/d/template_single/edit"


@pytest.fixture
def init_db(db_path):
    conn = db.connect(db_path)
    db.init_schema(conn)
    conn.close()


@pytest.mark.parametrize("attempt", range(5))
def test_simultaneous_confirms_create_one_activity(fake_adapter, db_path, init_db, attempt):
    jobs = [(GROUP, 0), (SINGLE, 0)]
    services = [ActivityService(fake_adapter, db_path) for _ in jobs]
    fingerprints = [s.preview_import(u, sid).fingerprint for s, (u, sid) in zip(services, jobs)]
    barrier = threading.Barrier(len(jobs))
    results: list[object] = [None] * len(jobs)

    def run(i):
        url, sheet_id = jobs[i]
        barrier.wait()
        try:
            results[i] = services[i].create_from_import(url, sheet_id, 4, fingerprints[i], False)
        except Exception as exc:  # noqa: BLE001 - recorded and asserted below
            results[i] = exc

    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(jobs))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    errors = [r for r in results if isinstance(r, Exception)]
    created = [r for r in results if r is not None and not isinstance(r, Exception)]
    assert len(created) == 1, results
    assert len(errors) == 1 and isinstance(errors[0], CurrentActivityExists), results

    conn = db.connect(db_path)
    try:
        current = conn.execute(
            "SELECT count(*) FROM activities WHERE phase IN ('DRAFT', 'OPEN')"
        ).fetchone()[0]
    finally:
        conn.close()
    assert current == 1


def test_index_rejects_insert_that_bypasses_the_service(fake_adapter, db_path, init_db):
    service = ActivityService(fake_adapter, db_path)
    p = service.preview_import(GROUP, 0)
    service.create_from_import(GROUP, 0, 4, p.fingerprint, False)

    conn = db.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO activities (title, phase, group_count, source_spreadsheet_id, "
                "source_sheet_id, source_tab_title, created_at, imported_at) VALUES "
                "('x', 'DRAFT', 4, 's', 0, 't', '2026-11-26T00:00:00Z', '2026-11-26T00:00:00Z')"
            )
    finally:
        conn.close()
