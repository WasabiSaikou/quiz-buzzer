"""CSV of all submissions of a CLOSED activity (diagrams/003-seq-download-csv.puml; research R6).

Pure function, no I/O. UTF-8 with a BOM (so Excel detects UTF-8), RFC 4180 quoting and CRLF line
endings, one row per answer slot. Answers starting with = + - @ get a leading ' so spreadsheet
programs show them as text and never run them as formulas (FR-018).
"""

from __future__ import annotations

import csv
import io

from quizbuzzer.models import ActivityResults, UnitKind

HEADER = ["question_no", "sub_part", "group", "answer", "rank", "is_winner", "submitted_at"]
FORMULA_PREFIXES = ("=", "+", "-", "@")
BOM = "﻿"


def guard_formula(text: str) -> str:
    """FR-018: prefix ' when the first character could start a formula."""
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def iso_with_offset(received_at: str) -> str:
    """'…Z' (UTC) -> '…+00:00': ISO 8601 with an explicit UTC offset (FR-016)."""
    return received_at[:-1] + "+00:00" if received_at.endswith("Z") else received_at


def to_csv(results: ActivityResults) -> bytes:
    buf = io.StringIO(newline="")
    # QUOTE_MINIMAL quotes any field holding the delimiter, a quote, CR or LF, doubling quotes.
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(HEADER)
    for unit in results.units:  # sheet order
        for entry in unit.entries:  # rank order
            for sub_part, text in entry.answers:  # sub-part order
                writer.writerow(
                    [
                        unit.number,
                        sub_part if unit.kind is UnitKind.GROUP_SET else "",
                        entry.group_number,
                        guard_formula(text),
                        entry.rank,
                        "true" if entry.is_winner else "false",
                        iso_with_offset(entry.received_at),
                    ]
                )
    return (BOM + buf.getvalue()).encode("utf-8")
