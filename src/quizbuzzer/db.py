"""SQLite store (research R7; data-model.md). Standard sqlite3, no ORM.

Every write runs inside `transaction(conn)` (BEGIN IMMEDIATE ... COMMIT). Queries for
activities, units and slots are added by the user-story tasks.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from quizbuzzer.models import Activity, AnswerSlot, ParsedUnit, Phase, QuestionUnit, UnitKind

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


# --- Activity queries (data-model.md › Activity, QuestionUnit, AnswerSlot) ------------------


def insert_activity(
    conn: sqlite3.Connection,
    *,
    title: str,
    phase: str,
    group_count: int,
    spreadsheet_id: str,
    sheet_id: int,
    tab_title: str,
    created_at: str,
    imported_at: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO activities (title, phase, group_count, source_spreadsheet_id, "
        "source_sheet_id, source_tab_title, created_at, imported_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (title, phase, group_count, spreadsheet_id, sheet_id, tab_title, created_at, imported_at),
    )
    return int(cur.lastrowid)


def insert_units_and_slots(
    conn: sqlite3.Connection, activity_id: int, units: Sequence[ParsedUnit]
) -> None:
    """Insert units in sheet order (position = index) and their slots."""
    for position, unit in enumerate(units):
        cur = conn.execute(
            "INSERT INTO question_units (activity_id, number, kind, source_row, position) "
            "VALUES (?, ?, ?, ?, ?)",
            (activity_id, unit.number, unit.kind.value, unit.source_row, position),
        )
        unit_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO answer_slots (unit_id, sub_part, cell_row, cell_column, a1_ref) "
            "VALUES (?, ?, ?, ?, ?)",
            [(unit_id, s.sub_part, s.row, s.column, s.a1_ref) for s in unit.slots],
        )


def find_current_activity(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """The single DRAFT/OPEN activity (id, title, phase), if any."""
    return conn.execute(
        "SELECT id, title, phase FROM activities WHERE phase IN ('DRAFT', 'OPEN') "
        "ORDER BY id LIMIT 1"
    ).fetchone()


def get_activity_with_units(conn: sqlite3.Connection, activity_id: int) -> Activity | None:
    row = conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
    if row is None:
        return None
    slots_by_unit: dict[int, list[AnswerSlot]] = {}
    for s in conn.execute(
        "SELECT s.* FROM answer_slots s JOIN question_units u ON s.unit_id = u.id "
        "WHERE u.activity_id = ? ORDER BY u.position, s.id",
        (activity_id,),
    ):
        slots_by_unit.setdefault(s["unit_id"], []).append(
            AnswerSlot(
                id=s["id"],
                sub_part=s["sub_part"],
                cell_row=s["cell_row"],
                cell_column=s["cell_column"],
                a1_ref=s["a1_ref"],
            )
        )
    units = tuple(
        QuestionUnit(
            id=u["id"],
            number=u["number"],
            kind=UnitKind(u["kind"]),
            source_row=u["source_row"],
            position=u["position"],
            slots=tuple(slots_by_unit.get(u["id"], ())),
        )
        for u in conn.execute(
            "SELECT * FROM question_units WHERE activity_id = ? ORDER BY position", (activity_id,)
        )
    )
    return Activity(
        id=row["id"],
        title=row["title"],
        phase=Phase(row["phase"]),
        group_count=row["group_count"],
        source_spreadsheet_id=row["source_spreadsheet_id"],
        source_sheet_id=row["source_sheet_id"],
        source_tab_title=row["source_tab_title"],
        created_at=row["created_at"],
        imported_at=row["imported_at"],
        units=units,
    )


def list_closed_activity_ids(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM activities WHERE phase = 'CLOSED' ORDER BY id")]


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
