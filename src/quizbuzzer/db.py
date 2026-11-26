"""SQLite store (research R7; data-model.md). Standard sqlite3, no ORM.

Every write runs inside `transaction(conn)` (BEGIN IMMEDIATE ... COMMIT). Queries for
activities, units and slots are added by the user-story tasks.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from quizbuzzer.models import (
    Activity,
    AnswerSlot,
    ParsedUnit,
    Participant,
    Phase,
    QuestionUnit,
    Submission,
    SubmissionAnswer,
    UnitKind,
)

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

-- AUTOINCREMENT on units and slots: ids are never reused after a re-import deletes rows, so an
-- old unit/slot id can never be confused with a new one.
CREATE TABLE IF NOT EXISTS question_units (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL REFERENCES activities (id) ON DELETE CASCADE,
    number      INTEGER NOT NULL CHECK (number > 0),
    kind        TEXT    NOT NULL CHECK (kind IN ('SINGLE', 'GROUP_SET')),
    source_row  INTEGER NOT NULL CHECK (source_row > 0),
    position    INTEGER NOT NULL CHECK (position >= 0),
    UNIQUE (activity_id, number),
    UNIQUE (activity_id, position)
);

CREATE TABLE IF NOT EXISTS answer_slots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id     INTEGER NOT NULL REFERENCES question_units (id) ON DELETE CASCADE,
    sub_part    INTEGER NOT NULL CHECK (sub_part > 0),
    cell_row    INTEGER NOT NULL CHECK (cell_row > 0),
    cell_column INTEGER NOT NULL CHECK (cell_column > 0),
    a1_ref      TEXT    NOT NULL,
    UNIQUE (unit_id, sub_part)
);

-- Feature 002 (specs/002-live-buzz-activity/data-model.md). Groups are values, not rows.
CREATE TABLE IF NOT EXISTS participants (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id  INTEGER NOT NULL REFERENCES activities (id) ON DELETE CASCADE,
    group_number INTEGER NOT NULL CHECK (group_number BETWEEN 1 AND 12),
    display_name TEXT    NOT NULL CHECK (length(display_name) BETWEEN 1 AND 20),
    token_hash   TEXT    NOT NULL UNIQUE,
    joined_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS participants_by_group ON participants (activity_id, group_number);

-- rank is assigned in the submit transaction (BEGIN IMMEDIATE); the two UNIQUE constraints
-- make a second submission by one group, or a second row with the same rank, impossible.
CREATE TABLE IF NOT EXISTS submissions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id        INTEGER NOT NULL REFERENCES question_units (id) ON DELETE CASCADE,
    group_number   INTEGER NOT NULL CHECK (group_number BETWEEN 1 AND 12),
    participant_id INTEGER NOT NULL REFERENCES participants (id),
    rank           INTEGER NOT NULL CHECK (rank >= 1),
    received_at    TEXT    NOT NULL,
    UNIQUE (unit_id, group_number),
    UNIQUE (unit_id, rank)
);

CREATE TABLE IF NOT EXISTS submission_answers (
    submission_id INTEGER NOT NULL REFERENCES submissions (id) ON DELETE CASCADE,
    slot_id       INTEGER NOT NULL REFERENCES answer_slots (id),
    text          TEXT    NOT NULL CHECK (length(text) BETWEEN 1 AND 200),
    PRIMARY KEY (submission_id, slot_id)
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
    """Create the 001 and 002 tables and indexes if missing (idempotent; 002 research R5)."""
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


def replace_activity_questions(
    conn: sqlite3.Connection,
    activity_id: int,
    *,
    spreadsheet_id: str,
    sheet_id: int,
    tab_title: str,
    imported_at: str,
    units: Sequence[ParsedUnit],
) -> None:
    """Replace an activity's whole question set (FR-024). Never touches phase or group count.

    Runs inside the caller's transaction; does not begin or commit one itself.
    """
    conn.execute("DELETE FROM question_units WHERE activity_id = ?", (activity_id,))  # slots cascade
    insert_units_and_slots(conn, activity_id, units)
    conn.execute(
        "UPDATE activities SET source_spreadsheet_id = ?, source_sheet_id = ?, "
        "source_tab_title = ?, imported_at = ? WHERE id = ?",
        (spreadsheet_id, sheet_id, tab_title, imported_at, activity_id),
    )


def get_activity_phase(conn: sqlite3.Connection, activity_id: int) -> Phase | None:
    row = conn.execute("SELECT phase FROM activities WHERE id = ?", (activity_id,)).fetchone()
    return Phase(row["phase"]) if row else None


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


def find_latest_activity(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """The most recently CLOSED activity (002 research R7).

    Only one activity is ever non-CLOSED and ids only grow, so the highest CLOSED id is the
    one closed last; no closed_at column is needed.
    """
    return conn.execute(
        "SELECT id, title, phase FROM activities WHERE phase = 'CLOSED' ORDER BY id DESC LIMIT 1"
    ).fetchone()


# --- Feature 002 queries (specs/002-live-buzz-activity/data-model.md) ----------------------
# Every function takes the caller's connection, so it runs inside the caller's transaction.


def _participant(row: sqlite3.Row) -> Participant:
    return Participant(
        id=row["id"],
        activity_id=row["activity_id"],
        group_number=row["group_number"],
        display_name=row["display_name"],
        joined_at=row["joined_at"],
    )


def insert_participant(
    conn: sqlite3.Connection,
    *,
    activity_id: int,
    group_number: int,
    display_name: str,
    token_hash: str,
    joined_at: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO participants (activity_id, group_number, display_name, token_hash, joined_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (activity_id, group_number, display_name, token_hash, joined_at),
    )
    return int(cur.lastrowid)


def find_participant_by_token_hash(
    conn: sqlite3.Connection, token_hash: str
) -> Participant | None:
    row = conn.execute("SELECT * FROM participants WHERE token_hash = ?", (token_hash,)).fetchone()
    return _participant(row) if row else None


def get_participant(conn: sqlite3.Connection, participant_id: int) -> Participant | None:
    row = conn.execute("SELECT * FROM participants WHERE id = ?", (participant_id,)).fetchone()
    return _participant(row) if row else None


def list_group_members(conn: sqlite3.Connection, activity_id: int, group_number: int) -> list[str]:
    """Display names of one group's members, in join order (duplicates kept)."""
    return [
        r[0]
        for r in conn.execute(
            "SELECT display_name FROM participants WHERE activity_id = ? AND group_number = ? "
            "ORDER BY id",
            (activity_id, group_number),
        )
    ]


def _submissions(conn: sqlite3.Connection, where: str, params: tuple) -> list[Submission]:
    rows = conn.execute(
        "SELECT s.*, u.number AS unit_number, p.display_name AS submitted_by "
        "FROM submissions s JOIN question_units u ON s.unit_id = u.id "
        "JOIN participants p ON s.participant_id = p.id "
        f"WHERE {where} ORDER BY u.position, s.rank",
        params,
    ).fetchall()
    answers: dict[int, list[SubmissionAnswer]] = {}
    if rows:
        ids = [r["id"] for r in rows]
        marks = ",".join("?" * len(ids))
        for a in conn.execute(
            "SELECT a.submission_id, a.slot_id, a.text, sl.sub_part FROM submission_answers a "
            f"JOIN answer_slots sl ON a.slot_id = sl.id WHERE a.submission_id IN ({marks}) "
            "ORDER BY sl.sub_part",
            ids,
        ):
            answers.setdefault(a["submission_id"], []).append(
                SubmissionAnswer(slot_id=a["slot_id"], sub_part=a["sub_part"], text=a["text"])
            )
    return [
        Submission(
            id=r["id"],
            unit_id=r["unit_id"],
            unit_number=r["unit_number"],
            group_number=r["group_number"],
            participant_id=r["participant_id"],
            submitted_by=r["submitted_by"],
            rank=r["rank"],
            received_at=r["received_at"],
            answers=tuple(answers.get(r["id"], ())),
        )
        for r in rows
    ]


def list_group_submissions(
    conn: sqlite3.Connection, activity_id: int, group_number: int
) -> list[Submission]:
    """One group's own submissions in this activity, in sheet order."""
    return _submissions(
        conn, "u.activity_id = ? AND s.group_number = ?", (activity_id, group_number)
    )


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
