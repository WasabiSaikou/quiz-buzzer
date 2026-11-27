"""CSV of all submissions, tests first (003 T025; FR-015 – FR-018; research R6).

Quoting, BOM, CRLF, row order, column contents and the formula prefix.
"""

from __future__ import annotations

import csv
import io

import pytest

from quizbuzzer.models import (
    Activity,
    AnswerSlot,
    Phase,
    QuestionUnit,
    Submission,
    SubmissionAnswer,
    UnitKind,
)
from quizbuzzer.services.csv_export import HEADER, to_csv
from quizbuzzer.services.results_service import build_results

BOM = b"\xef\xbb\xbf"


def activity():
    units = (
        QuestionUnit(id=1, number=1, kind=UnitKind.SINGLE, source_row=5, position=0,
                     slots=(AnswerSlot(id=11, sub_part=1, cell_row=5, cell_column=7, a1_ref="G5"),)),
        QuestionUnit(id=2, number=2, kind=UnitKind.GROUP_SET, source_row=7, position=1,
                     slots=(AnswerSlot(id=21, sub_part=1, cell_row=7, cell_column=7, a1_ref="G7"),
                            AnswerSlot(id=22, sub_part=2, cell_row=8, cell_column=7, a1_ref="G8"))),
        QuestionUnit(id=3, number=3, kind=UnitKind.SINGLE, source_row=10, position=2,
                     slots=(AnswerSlot(id=31, sub_part=1, cell_row=10, cell_column=7, a1_ref="G10"),)),
    )
    return Activity(id=9, title="T", phase=Phase.CLOSED, group_count=6, source_spreadsheet_id="s",
                    source_sheet_id=0, source_tab_title="Tab", created_at="x", imported_at="x",
                    units=units)


def sub(sid, unit_id, number, group, rank, answers, at="2026-11-27T02:14:09.512Z"):
    return Submission(id=sid, unit_id=unit_id, unit_number=number, group_number=group,
                      participant_id=1, submitted_by="名", rank=rank, received_at=at,
                      answers=tuple(SubmissionAnswer(slot_id=s, sub_part=k, text=t) for s, k, t in answers))


def results(subs):
    return build_results(activity(), subs)


def rows(data: bytes):
    assert data.startswith(BOM)
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"), newline="")))


def test_bom_header_and_crlf():
    data = to_csv(results([sub(1, 1, 1, 4, 1, [(11, 1, "a")])]))
    assert data.startswith(BOM)
    text = data[len(BOM):].decode("utf-8")
    assert text.split("\r\n")[0] == "question_no,sub_part,group,answer,rank,is_winner,submitted_at"
    assert HEADER == ["question_no", "sub_part", "group", "answer", "rank", "is_winner", "submitted_at"]
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")


def test_one_row_per_slot_ordered_unit_rank_sub_part():
    subs = [
        sub(3, 2, 2, 5, 2, [(22, 2, "y2"), (21, 1, "y1")]),
        sub(2, 2, 2, 1, 1, [(21, 1, "x1"), (22, 2, "x2")], at="2026-11-27T02:14:08.000Z"),
        sub(1, 1, 1, 4, 1, [(11, 1, "s")]),
    ]
    assert rows(to_csv(results(subs)))[1:] == [
        ["1", "", "4", "s", "1", "true", "2026-11-27T02:14:09.512+00:00"],
        ["2", "1", "1", "x1", "1", "true", "2026-11-27T02:14:08.000+00:00"],
        ["2", "2", "1", "x2", "1", "true", "2026-11-27T02:14:08.000+00:00"],
        ["2", "1", "5", "y1", "2", "false", "2026-11-27T02:14:09.512+00:00"],
        ["2", "2", "5", "y2", "2", "false", "2026-11-27T02:14:09.512+00:00"],
    ]


@pytest.mark.parametrize("answer", ["a,b", 'say "hi"', "line1\nline2", "line1\r\nline2", 'm,"x"\n'])
def test_special_characters_round_trip_as_one_field(answer):
    data = to_csv(results([sub(1, 1, 1, 4, 1, [(11, 1, answer)])]))
    (row,) = rows(data)[1:]
    assert len(row) == 7
    assert row[3] == answer


def test_quoting_doubles_inner_quotes():
    data = to_csv(results([sub(1, 1, 1, 4, 1, [(11, 1, 'say "hi"')])]))
    assert b'"say ""hi"""' in data


@pytest.mark.parametrize("first", ["=", "+", "-", "@"])
def test_formula_like_answers_get_a_leading_apostrophe(first):
    answer = f"{first}SUM(A1)"
    (row,) = rows(to_csv(results([sub(1, 1, 1, 4, 1, [(11, 1, answer)])])))[1:]
    assert row[3] == "'" + answer


@pytest.mark.parametrize("answer", ["a-b", "x=1", "e@mail", " =1", "１+1"])
def test_formula_characters_later_in_the_text_are_left_alone(answer):
    (row,) = rows(to_csv(results([sub(1, 1, 1, 4, 1, [(11, 1, answer)])])))[1:]
    assert row[3] == answer


def test_formula_prefix_combined_with_quoting():
    (row,) = rows(to_csv(results([sub(1, 1, 1, 4, 1, [(11, 1, '=A1,"x"')])])))[1:]
    assert row[3] == "'=A1,\"x\""


def test_chinese_text_survives():
    data = to_csv(results([sub(1, 1, 1, 4, 1, [(11, 1, "光合作用（葉綠體）")])]))
    assert rows(data)[1][3] == "光合作用（葉綠體）"
    assert "光合作用".encode() in data  # UTF-8, not a legacy code page


def test_zero_submissions_gives_header_only():
    assert rows(to_csv(results([]))) == [HEADER]
