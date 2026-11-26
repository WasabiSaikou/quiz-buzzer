"""Phase changes are all-or-nothing under concurrency (FR-006, FR-008b; 002 research R5).

Threads with their own service instances race on one file DB behind a barrier.
"""

from __future__ import annotations

import threading

import pytest

from quizbuzzer import db
from quizbuzzer.models import Phase
from quizbuzzer.services.activity_service import ActivityService, PhaseConflict

GROUP = "https://docs.google.com/spreadsheets/d/template_group/edit"


@pytest.fixture
def init_db(db_path):
    conn = db.connect(db_path)
    db.init_schema(conn)
    conn.close()


def new_draft(fake_adapter, db_path):
    svc = ActivityService(fake_adapter, db_path)
    p = svc.preview_import(GROUP, 0)
    return svc.create_from_import(GROUP, 0, 6, p.fingerprint, True)


def race(*calls):
    """Run each callable in its own thread behind one barrier; return (results, errors)."""
    barrier = threading.Barrier(len(calls))
    results, errors = [None] * len(calls), [None] * len(calls)

    def run(i, fn):
        barrier.wait()
        try:
            results[i] = fn()
        except Exception as exc:  # noqa: BLE001 - recorded and asserted by the caller
            errors[i] = exc

    threads = [threading.Thread(target=run, args=(i, fn)) for i, fn in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


def phase_of(db_path, activity_id):
    conn = db.connect(db_path)
    try:
        return db.get_activity_phase(conn, activity_id)
    finally:
        conn.close()


def close_activity(db_path, activity_id):
    conn = db.connect(db_path)
    try:
        conn.execute("UPDATE activities SET phase = 'CLOSED' WHERE id = ?", (activity_id,))
    finally:
        conn.close()


def test_two_simultaneous_opens_exactly_one_wins(fake_adapter, db_path, init_db):
    for _ in range(20):
        a = new_draft(fake_adapter, db_path)
        s1, s2 = ActivityService(fake_adapter, db_path), ActivityService(fake_adapter, db_path)
        results, errors = race(lambda: s1.open_activity(a.id), lambda: s2.open_activity(a.id))
        wins = [r for r in results if r is not None]
        assert len(wins) == 1, (results, errors)
        losers = [e for e in errors if e is not None]
        assert len(losers) == 1 and isinstance(losers[0], PhaseConflict), errors
        assert losers[0].phase is Phase.OPEN
        assert phase_of(db_path, a.id) is Phase.OPEN
        close_activity(db_path, a.id)  # free the slot for the next round
