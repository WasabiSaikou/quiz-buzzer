"""SQLite store (research R7; data-model.md). Standard sqlite3, no ORM.

Every write runs inside `transaction(conn)` (BEGIN IMMEDIATE ... COMMIT). Queries for
activities, units and slots are added by the user-story tasks.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    title                 TEXT    NOT NULL,
    phase                 TEXT    NOT NULL CHECK (phase IN ('DRAFT', 'OPEN', 'CLOSED')),
    group_count           INTEGER NOT NULL CHECK (group_count BETWEEN 2 AND 12),
    source_spreadsheet_id TEXT    NOT NULL,
    source_sheet_id       INTEGER NOT NULL,
    source_tab_title      TEXT    NOT NULL,
    created_at            TEXT    NOT NULL,
    imported_at           TEXT    NOT NULL
);

-- At most one current (DRAFT/OPEN) activity (FR-020a). Every current row indexes the same
-- value (1), so a second one violates uniqueness; CLOSED rows are outside the index.
CREATE UNIQUE INDEX IF NOT EXISTS one_current_activity
    ON activities ((phase IN ('DRAFT', 'OPEN')))
    WHERE phase IN ('DRAFT', 'OPEN');

CREATE TABLE IF NOT EXISTS question_units (
    id          INTEGER PRIMARY KEY,
    activity_id INTEGER NOT NULL REFERENCES activities (id) ON DELETE CASCADE,
    number      INTEGER NOT NULL CHECK (number > 0),
    kind        TEXT    NOT NULL CHECK (kind IN ('SINGLE', 'GROUP_SET')),
    source_row  INTEGER NOT NULL CHECK (source_row > 0),
    position    INTEGER NOT NULL CHECK (position >= 0),
    UNIQUE (activity_id, number),
    UNIQUE (activity_id, position)
);

CREATE TABLE IF NOT EXISTS answer_slots (
    id          INTEGER PRIMARY KEY,
    unit_id     INTEGER NOT NULL REFERENCES question_units (id) ON DELETE CASCADE,
    sub_part    INTEGER NOT NULL CHECK (sub_part > 0),
    cell_row    INTEGER NOT NULL CHECK (cell_row > 0),
    cell_column INTEGER NOT NULL CHECK (cell_column > 0),
    a1_ref      TEXT    NOT NULL,
    UNIQUE (unit_id, sub_part)
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection in autocommit mode; writes use `transaction()` explicitly."""
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the 001 tables and index if missing (idempotent)."""
    conn.executescript(SCHEMA)


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE ... COMMIT; ROLLBACK on any exception (all-or-nothing, FR-023)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
