"""Tables: header periods, the column a value is read in, and how a header's columns meet a row's cells."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from axelrod_wm.ingest.tables import (
    PERIOD,
    Header,
    Period,
    _minus_months,
    align,
    end_of,
    header_of,
    period_of,
    pick,
)

OCT = datetime(2026, 10, 5, tzinfo=UTC)


def period(text: str) -> Period | None:
    return period_of(PERIOD.fullmatch(text))


@pytest.mark.parametrize("text,kind,end,estimate", [
    ("9/25/2026", "date", (2026, 9), False),
    ("2026-09-30 00:00:00", "date", (2026, 9), False),
    ("2026-09-30", "date", (2026, 9), False),
    ("31-Jul-2026", "date", (2026, 7), False),
    ("1 Oct", "date", (0, 10), False),                     # the year is the document's
    ("3Q26E", "quarter", (2026, 9), True),
    ("Q2-2026", "quarter", (2026, 6), False),
    ("3/27E", "year", (2027, 3), True),
    ("FY3/27", "year", (2027, 3), False),
    ("27/3E", "year", (2027, 3), True),                    # year/month when the first number cannot be a month
    ("12/25", "year", (2025, 12), False),
    ("FY2027", "year", (2027, 12), False),
    ("FY27E", "year", (2027, 12), True),
    ("2026E", "year", (2026, 12), True),
    ("12M", "horizon", None, True),
    ("Previous", "prev", None, False),
    ("New", "cur", None, False),
])
def test_period_of(text, kind, end, estimate):
    p = period(text)
    assert (p.kind, p.end, p.estimate, p.text) == (kind, end, estimate, text)


def test_period_flags():
    assert period("FY2027").fiscal and not period("FY2027").plain
    assert period("2026E").fiscal and period("2026E").plain
    assert period("3/27E").months == 12 and period("3Q26").months == 3
    assert period("31-Jul-2026").day == 31
    assert period("27/27") is None                         # neither month/year nor year/month


def test_header_of_a_line():
    h = header_of("Fiscal Year Ending 03/26 03/27e 03/28e 03/29e")
    assert [p.text for p in h.periods] == ["03/26", "03/27e", "03/28e", "03/29e"] and h.cells == ()
    assert [p.text for p in header_of("1 Oct 3M 6M 12M").periods] == ["1 Oct", "3M", "6M", "12M"]
    assert [p.kind for p in header_of("(¥) Previous Current").periods] == ["prev", "cur"]
    # periods at the end of a wordy line still head a table
    assert len(header_of("Operating profit (ordinary profit ex realised gains) 2023 2024 2025E").periods) == 3


@pytest.mark.parametrize("text", [
    "Operating profit 607.2 657.1 571.2",                 # figures that are not periods: a row
    "Price (31 Jul 2026) ¥6,994",
    "The 2025 results beat the plan for most lines and the 2026 outlook improved meaningfully again.",
    "2025 2026 " + "word " * 80,                          # too long
    "only 2026 here",
])
def test_lines_that_are_not_headers(text):
    assert header_of(text) is None


def test_header_of_a_spreadsheet_row():
    h = header_of("USD |  | FY2025 | Q1-2026 | Q2-2026")
    assert [p.text for p in h.periods] == ["FY2025", "Q1-2026", "Q2-2026"] and h.cells == (2, 3, 4)
    assert header_of("label | FY2025 | note | other | text") is None          # periods must be half the cells
    assert header_of("Value | Level") is None


def test_end_and_minus_months():
    assert end_of(period("FY2027"), 3, 0) == (2027, 3, 31)                    # a fiscal year ends in its company's month
    assert end_of(period("1 Oct"), 12, 2026) == (2026, 10, 1)
    assert end_of(period("1 Oct"), 12, 0) == (0, 10, 1)
    assert end_of(Period("x", "horizon"), 12, 2026) == (0, 0, 28)
    assert _minus_months((2027, 3, 31), 12) == (2026, 3, 31)


def ps(*texts: str) -> list[Period]:
    return [period(t) for t in texts]


def test_pick_a_flow_reads_the_fiscal_year_of_the_document():
    cols = ps("3/26", "3/27E", "3/28E")
    assert pick(cols, flow=True, date=OCT, fy_month=3) == 1
    assert pick(ps("2025", "2026E", "2027E"), flow=True, date=OCT) == 1
    assert pick(ps("FY2026", "FY2027"), flow=True, date=OCT, fy_month=3) == 1        # FY2027 ends March 2027
    # a bare year is ambiguous for a March year-end: not read
    assert pick(ps("2026E", "2027E"), flow=True, date=OCT, fy_month=3) is None
    assert pick(ps("2023", "2024"), flow=True, date=OCT) is None                     # no column for now
    assert pick(ps("3Q26", "4Q26"), flow=True, date=OCT) is None                     # quarters are not years
    # without a date: the first estimated year
    assert pick(ps("2025", "2026E", "2027E"), flow=True, date=None) == 1
    assert pick(ps("2024", "2025"), flow=True, date=None) is None


def test_pick_a_level_reads_the_latest_period_passed():
    assert pick(ps("2Q26", "3Q26", "9/25/2026", "6/30"), flow=False, date=OCT) == 2   # a full date first
    assert pick(ps("6/26", "9/26E", "12/26E"), flow=False, date=OCT) == 0          # an estimate is never a level
    assert pick(ps("1 Oct", "3M", "6M"), flow=False, date=OCT) == 0
    assert pick(ps("12/27E", "12/28E"), flow=False, date=OCT) is None
    # without a date: the last column not estimated
    assert pick(ps("12/25", "12/26E"), flow=False, date=None) == 0
    assert pick(ps("12/26E"), flow=False, date=None) is None


@dataclass
class C:
    unit: str = ""
    signed: bool = False


def test_align():
    cols = ps("2024", "2025", "2026E")
    row = [C(), C(), C()]
    assert align(cols, row, rate=False) == (cols, row)
    # side by side: the header repeats, the row stops at its own block
    twice = ps("1 Oct", "3M", "6M", "1 Oct", "3M", "6M")
    assert align(twice, row, rate=False) == (twice[:3], row)
    # a level's cells, then its changes
    six = ps("2023", "2024", "2025", "2026E", "2027E", "2028E", "2026E", "2027E")
    cells = [C()] * 6 + [C("%", True)] * 3
    assert align(six, cells, rate=False) == (six[:6], cells[:6])
    # a rate's percents among its bp changes
    four = ps("2Q26", "3Q26", "9/25/2026", "6/30")
    mixed = [C("%"), C("%"), C("bp"), C("bp"), C("%"), C("%")]
    assert align(four, mixed, rate=True) == (four, [mixed[0], mixed[1], mixed[4], mixed[5]])
    assert align(cols, [C(), C()], rate=False) is None
    assert align(ps("2024", "2025", "2024", "2025"), [C(), C(), C()], rate=False) is None


def test_header_is_a_record():
    assert Header(tuple(ps("2025"))) == Header(tuple(ps("2025")), ())


def test_year_month_periods_and_actuals():
    p = period("2027/3E")
    assert (p.kind, p.end, p.estimate) == ("year", (2027, 3), True)
    assert period("2026/3A").estimate is False and period("2025A").estimate is False and period("3Q26A").kind == "quarter"
    assert period("2026/13") is None


def test_revise_marks_old_and_new_columns():
    from axelrod_wm.ingest.tables import revise
    h = header_of("FY3/27 FY3/28 FY3/27 FY3/28")
    marks = header_of("New New Old Old")
    assert [p.revision for p in revise(h, marks).periods] == ["cur", "cur", "prev", "prev"]
    assert revise(None, marks) is None
    assert revise(header_of("FY3/27 FY3/28"), marks) is None
    assert revise(header_of("x | FY2026 | FY2027 | FY2028 | FY2029"), marks) is None
    assert revise(header_of("Old Old New New"), marks) is None


def test_cells_of_a_sheet_row():
    from axelrod_wm.ingest.tables import cells_of
    row = "a | | b | c"                                      # an empty cell's spaces collapse
    assert [row[x:y] for x, y in cells_of(row)] == ["a", "", "b", "c"]
    row = "| x"                                              # a leading empty cell
    assert [row[x:y] for x, y in cells_of(row)] == ["", "x"]


def test_a_header_row_among_labels_and_its_current_column():
    h = header_of("Variable | Unit | 31-Dec-2025 | 31-Mar-2026 | Current | As of | Source (current) | Notes")
    assert [p.text for p in h.periods] == ["31-Dec-2025", "31-Mar-2026", "Current"] and h.cells == (2, 3, 4)
    assert pick(list(h.periods), flow=False, date=datetime(2026, 10, 5, tzinfo=UTC)) == 2
    # a row with a figure of its own is a row, not a header
    assert header_of("BoJ | % | 31-Dec-2025 | 31-Mar-2026 | 0.75 | x | y | z") is None
