"""Ranking under real concurrency (Constitution I; SC-003, SC-004; research R3).

Threads, each with its own ParticipationService (own connections), race on one file DB behind a
barrier. The server's transaction order alone decides ranks.
"""

from __future__ import annotations

import threading

import pytest

from quizbuzzer import db
from quizbuzzer.services.participation_service import AlreadySubmitted, ParticipationService
from tests.live_helpers import answers_for, init_schema, make_activity

ROUNDS = 100
GROUPS = 12


def race(calls):
    barrier = threading.Barrier(len(calls))
    results, errors = [None] * len(calls), [None] * len(calls)

    def run(i, fn):
        barrier.wait()
        try:
            results[i] = fn()
        except Exception as exc:  # noqa: BLE001 - asserted by the caller
            errors[i] = exc

    threads = [threading.Thread(target=run, args=(i, fn)) for i, fn in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results, errors


def unit_ranks(db_path, unit_id):
    conn = db.connect(db_path)
    try:
        return [tuple(r) for r in conn.execute(
            "SELECT group_number, rank FROM submissions WHERE unit_id = ? ORDER BY rank", (unit_id,))]
    finally:
        conn.close()


@pytest.mark.slow
def test_twelve_groups_at_once_100_rounds(fake_adapter, db_path):
    init_schema(db_path)
    activity = make_activity(fake_adapter, db_path, n_units=ROUNDS + 1, group_count=GROUPS, phase="DRAFT")
    joiner = ParticipationService(db_path)
    tokens = {g: joiner.join(None, activity.id, g, f"g{g}")[0] for g in range(1, GROUPS + 1)}
    conn = db.connect(db_path)
    conn.execute("UPDATE activities SET phase = 'OPEN' WHERE id = ?", (activity.id,))
    conn.close()
    services = {g: ParticipationService(db_path) for g in tokens}
    singles = [u for u in activity.units if len(u.slots) == 1][:ROUNDS]
    assert len(singles) == ROUNDS

    for unit in singles:
        calls = [
            (lambda g=g, u=unit: services[g].submit(tokens[g], u.id, answers_for(u)))
            for g in tokens
        ]
        results, errors = race(calls)
        assert errors == [None] * GROUPS, errors
        got = unit_ranks(db_path, unit.id)
        assert sorted(r for _, r in got) == list(range(1, GROUPS + 1)), got  # no gaps, no repeats
        assert sorted(g for g, _ in got) == list(range(1, GROUPS + 1))
        assert [r for _, r in got].count(1) == 1  # exactly one winner


def test_two_members_of_one_group_exactly_one_accepted(fake_adapter, db_path):
    init_schema(db_path)
    activity = make_activity(fake_adapter, db_path, n_units=51, group_count=4, phase="DRAFT")
    joiner = ParticipationService(db_path)
    ta, _ = joiner.join(None, activity.id, 2, "阿美")
    tb, _ = joiner.join(None, activity.id, 2, "小明")
    conn = db.connect(db_path)
    conn.execute("UPDATE activities SET phase = 'OPEN' WHERE id = ?", (activity.id,))
    conn.close()
    sa, sb = ParticipationService(db_path), ParticipationService(db_path)
    for unit in [u for u in activity.units if len(u.slots) == 1][:50]:
        results, errors = race([
            lambda u=unit: sa.submit(ta, u.id, answers_for(u, ["from-a"])),
            lambda u=unit: sb.submit(tb, u.id, answers_for(u, ["from-b"])),
        ])
        accepted = [r for r in results if r is not None]
        refused = [e for e in errors if e is not None]
        assert len(accepted) == 1 and len(refused) == 1, (results, errors)
        assert isinstance(refused[0], AlreadySubmitted)
        assert refused[0].submission["answers"] == accepted[0]["answers"]
        assert unit_ranks(db_path, unit.id) == [(2, 1)]
