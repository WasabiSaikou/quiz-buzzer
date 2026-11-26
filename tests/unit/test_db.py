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
    # Feature 002 adds its three tables; groups are values, never a table (002 research R4).
    assert {"participants", "submissions", "submission_answers"} <= tables
    assert "groups" not in tables


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


# --- Feature 002 schema (specs/002-live-buzz-activity/data-model.md) -------------------------

_001_SCHEMA_ONLY = """
CREATE TABLE activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('DRAFT', 'OPEN', 'CLOSED')),
    group_count INTEGER NOT NULL CHECK (group_count BETWEEN 2 AND 12),
    source_spreadsheet_id TEXT NOT NULL, source_sheet_id INTEGER NOT NULL,
    source_tab_title TEXT NOT NULL, created_at TEXT NOT NULL, imported_at TEXT NOT NULL);
CREATE TABLE question_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL REFERENCES activities (id) ON DELETE CASCADE,
    number INTEGER NOT NULL, kind TEXT NOT NULL, source_row INTEGER NOT NULL,
    position INTEGER NOT NULL);
CREATE TABLE answer_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id INTEGER NOT NULL REFERENCES question_units (id) ON DELETE CASCADE,
    sub_part INTEGER NOT NULL, cell_row INTEGER NOT NULL, cell_column INTEGER NOT NULL,
    a1_ref TEXT NOT NULL);
"""


def _unit_with_slots(conn, aid, number=1, n_slots=1):
    uid = conn.execute(
        "INSERT INTO question_units (activity_id, number, kind, source_row, position) "
        "VALUES (?, ?, ?, ?, ?)",
        (aid, number, "SINGLE" if n_slots == 1 else "GROUP_SET", 4 + number, number - 1),
    ).lastrowid
    slot_ids = [
        conn.execute(
            "INSERT INTO answer_slots (unit_id, sub_part, cell_row, cell_column, a1_ref) "
            "VALUES (?, ?, ?, 7, 'G1')",
            (uid, k, 4 + number + k),
        ).lastrowid
        for k in range(1, n_slots + 1)
    ]
    return uid, slot_ids


def _participant(conn, aid, group=1, name="小明", token_hash=None):
    token_hash = token_hash or f"hash-{aid}-{group}-{name}-{conn.total_changes}"
    return conn.execute(
        "INSERT INTO participants (activity_id, group_number, display_name, token_hash, joined_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (aid, group, name, token_hash, NOW),
    ).lastrowid


def _submission(conn, uid, group, pid, rank):
    return conn.execute(
        "INSERT INTO submissions (unit_id, group_number, participant_id, rank, received_at) "
        "VALUES (?, ?, ?, ?, '2026-11-27T02:14:09.512Z')",
        (uid, group, pid, rank),
    ).lastrowid


def test_002_tables_are_added_to_an_existing_001_database(db_path):
    conn = db.connect(db_path)
    try:
        conn.executescript(_001_SCHEMA_ONLY)
        aid = insert_activity(conn)
        before = conn.execute("SELECT * FROM activities").fetchall()
        db.init_schema(conn)
        db.init_schema(conn)  # idempotent
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"participants", "submissions", "submission_answers"} <= tables
        assert [tuple(r) for r in conn.execute("SELECT * FROM activities")] == [
            tuple(r) for r in before
        ]
        assert aid == 1
    finally:
        conn.close()


@pytest.mark.parametrize("group, ok", [(0, False), (1, True), (12, True), (13, False)])
def test_participant_group_number_check(conn, group, ok):
    aid = insert_activity(conn, group_count=12)
    if ok:
        _participant(conn, aid, group=group)
    else:
        with pytest.raises(sqlite3.IntegrityError):
            _participant(conn, aid, group=group)


@pytest.mark.parametrize("name, ok", [("", False), ("名", True), ("x" * 20, True), ("x" * 21, False)])
def test_participant_display_name_length_check(conn, name, ok):
    aid = insert_activity(conn)
    if ok:
        _participant(conn, aid, name=name)
    else:
        with pytest.raises(sqlite3.IntegrityError):
            _participant(conn, aid, name=name)


def test_participant_token_hash_is_unique(conn):
    aid = insert_activity(conn)
    _participant(conn, aid, token_hash="same")
    with pytest.raises(sqlite3.IntegrityError):
        _participant(conn, aid, group=2, token_hash="same")


def test_submission_rank_and_group_checks(conn):
    aid = insert_activity(conn)
    uid, _ = _unit_with_slots(conn, aid)
    pid = _participant(conn, aid)
    with pytest.raises(sqlite3.IntegrityError):
        _submission(conn, uid, 1, pid, rank=0)
    with pytest.raises(sqlite3.IntegrityError):
        _submission(conn, uid, 13, pid, rank=1)
    _submission(conn, uid, 1, pid, rank=1)


def test_one_submission_per_group_per_unit(conn):
    aid = insert_activity(conn)
    uid, _ = _unit_with_slots(conn, aid)
    pid = _participant(conn, aid, group=1)
    _submission(conn, uid, 1, pid, rank=1)
    with pytest.raises(sqlite3.IntegrityError):  # UNIQUE (unit_id, group_number)
        _submission(conn, uid, 1, pid, rank=2)


def test_one_row_per_rank_per_unit(conn):
    aid = insert_activity(conn)
    uid, _ = _unit_with_slots(conn, aid)
    p1, p2 = _participant(conn, aid, group=1), _participant(conn, aid, group=2)
    _submission(conn, uid, 1, p1, rank=1)
    with pytest.raises(sqlite3.IntegrityError):  # UNIQUE (unit_id, rank): never two winners
        _submission(conn, uid, 2, p2, rank=1)


@pytest.mark.parametrize(
    "text, ok", [("", False), ("答", True), ("字" * 200, True), ("字" * 201, False)]
)
def test_submission_answer_text_length_counts_characters(conn, text, ok):
    aid = insert_activity(conn)
    uid, (slot_id,) = _unit_with_slots(conn, aid)
    pid = _participant(conn, aid)
    sid = _submission(conn, uid, 1, pid, rank=1)
    sql = "INSERT INTO submission_answers (submission_id, slot_id, text) VALUES (?, ?, ?)"
    if ok:
        conn.execute(sql, (sid, slot_id, text))
    else:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, (sid, slot_id, text))


def test_submission_answer_one_row_per_slot(conn):
    aid = insert_activity(conn)
    uid, (slot_id,) = _unit_with_slots(conn, aid)
    pid = _participant(conn, aid)
    sid = _submission(conn, uid, 1, pid, rank=1)
    sql = "INSERT INTO submission_answers (submission_id, slot_id, text) VALUES (?, ?, 'a')"
    conn.execute(sql, (sid, slot_id))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, (sid, slot_id))


def test_deleting_an_activity_cascades_to_all_002_rows(conn):
    aid = insert_activity(conn)
    uid, (s1, s2) = _unit_with_slots(conn, aid, n_slots=2)
    pid = _participant(conn, aid)
    sid = _submission(conn, uid, 1, pid, rank=1)
    conn.executemany(
        "INSERT INTO submission_answers (submission_id, slot_id, text) VALUES (?, ?, 'a')",
        [(sid, s1), (sid, s2)],
    )
    conn.execute("DELETE FROM activities WHERE id = ?", (aid,))
    for table in ("participants", "question_units", "answer_slots", "submissions",
                  "submission_answers"):
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0, table
