"""Schema guarantees from data-model.md / research R7 (foundation for FR-020a, FR-023)."""

import sqlite3

import pytest

from quizbuzzer import db

NOW = "2026-11-26T08:00:00Z"


def insert_activity(conn, phase="DRAFT", group_count=4):
    cur = conn.execute(
        "INSERT INTO activities (title, phase, group_count, source_spreadsheet_id, "
        "source_sheet_id, source_tab_title, created_at, imported_at) "
        "VALUES ('t', ?, ?, 'sid', 0, 'Sheet1', ?, ?)",
        (phase, group_count, NOW, NOW),
    )
    return cur.lastrowid


@pytest.fixture
def conn(db_path):
    c = db.connect(db_path)
    db.init_schema(c)
    yield c
    c.close()


def test_init_schema_is_idempotent(conn):
    db.init_schema(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"activities", "question_units", "answer_slots"} <= tables
    # Later-feature tables are not created by 001.
    assert not tables & {"groups", "participants", "submissions"}


def test_connection_pragmas(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


@pytest.mark.parametrize("second", ["DRAFT", "OPEN"])
def test_index_allows_only_one_current_activity(conn, second):
    insert_activity(conn, "DRAFT")
    with pytest.raises(sqlite3.IntegrityError):
        insert_activity(conn, second)


def test_closed_activities_do_not_count_as_current(conn):
    insert_activity(conn, "CLOSED")
    insert_activity(conn, "CLOSED")
    insert_activity(conn, "OPEN")
    assert conn.execute("SELECT count(*) FROM activities").fetchone()[0] == 3


@pytest.mark.parametrize("bad", [1, 13])
def test_group_count_check(conn, bad):
    with pytest.raises(sqlite3.IntegrityError):
        insert_activity(conn, group_count=bad)


def test_phase_check(conn):
    with pytest.raises(sqlite3.IntegrityError):
        insert_activity(conn, phase="ARCHIVED")


def test_unit_and_slot_constraints_and_cascade(conn):
    aid = insert_activity(conn)
    uid = conn.execute(
        "INSERT INTO question_units (activity_id, number, kind, source_row, position) "
        "VALUES (?, 1, 'SINGLE', 5, 0)",
        (aid,),
    ).lastrowid
    conn.execute(
        "INSERT INTO answer_slots (unit_id, sub_part, cell_row, cell_column, a1_ref) "
        "VALUES (?, 1, 5, 7, 'G5')",
        (uid,),
    )
    with pytest.raises(sqlite3.IntegrityError):  # duplicate number in one activity
        conn.execute(
            "INSERT INTO question_units (activity_id, number, kind, source_row, position) "
            "VALUES (?, 1, 'SINGLE', 7, 1)",
            (aid,),
        )
    with pytest.raises(sqlite3.IntegrityError):  # duplicate sub_part in one unit
        conn.execute(
            "INSERT INTO answer_slots (unit_id, sub_part, cell_row, cell_column, a1_ref) "
            "VALUES (?, 1, 6, 7, 'G6')",
            (uid,),
        )
    with pytest.raises(sqlite3.IntegrityError):  # FK enforced
        conn.execute(
            "INSERT INTO question_units (activity_id, number, kind, source_row, position) "
            "VALUES (999, 1, 'SINGLE', 5, 0)"
        )
    conn.execute("DELETE FROM activities WHERE id = ?", (aid,))
    assert conn.execute("SELECT count(*) FROM question_units").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM answer_slots").fetchone()[0] == 0


def test_transaction_rolls_back_on_error(conn):
    with pytest.raises(RuntimeError):
        with db.transaction(conn):
            insert_activity(conn)
            raise RuntimeError("boom")
    assert conn.execute("SELECT count(*) FROM activities").fetchone()[0] == 0


def test_transaction_commits(conn, db_path):
    with db.transaction(conn):
        insert_activity(conn)
    other = db.connect(db_path)
    try:
        assert other.execute("SELECT count(*) FROM activities").fetchone()[0] == 1
    finally:
        other.close()
