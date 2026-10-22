"""Tables (Oct 17): which column of a table a value is read in, deterministically.

Research tables put periods in a header line ("Fiscal Year Ending 03/26 03/27e 03/28e", "2023 2024 2025E", "1 Oct 3M
6M 12M", a spreadsheet's "FY2025 | Q1-2026 | Q2-2026") and a value's figures in a row under it. A row is read in one
column, chosen the way an analyst would (`pick`): for a flow (a year's profit or income), the fiscal year the document's
date falls in; for a level (a rate, a price, a ratio), the latest dated column that had passed by the document's date.
A header's columns are matched to a row's cells by count (`align`), allowing for side-by-side tables and for a level's
cells followed by its changes.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol, TypeVar

from axelrod_ingest.chunk import CELL

MONTHS = {m: k + 1 for k, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


PERIOD = re.compile(
    r"(?<![\w/.])(?:"
    r"(?P<fd_m>\d{1,2})/(?P<fd_d>\d{1,2})/(?P<fd_y>20\d{2})"                                     # 9/25/2026
    r"|(?P<iso_y>20\d{2})-(?P<iso_m>\d{2})-(?P<iso_d>\d{2})(?: 00:00:00)?"                       # 2026-09-30
    r"|(?P<dmy_d>\d{1,2})[ -](?P<dmy_mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?[ -](?P<dmy_y>20\d{2})"
    r"|(?P<dm_d>\d{1,2})[ -](?P<dm_mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"     # 1 Oct
    r"|(?P<q_q>[1-4])Q[-\s]?(?P<q_y>\d{2}|20\d{2})(?P<q_e>[EeFAa])?"                             # 3Q26E
    r"|Q(?P<q2_q>[1-4])[-\s]?(?P<q2_y>\d{2}|20\d{2})(?P<q2_e>[EeFAa])?"                            # Q2-2026
    r"|(?P<ym_y>20\d{2})/(?P<ym_m>\d{1,2})(?P<ym_e>[EeFfAa])?"                                    # 2027/3E
    r"|(?:FY)?(?P<my_m>\d{1,2})/(?P<my_y>20\d{2}|\d{1,2})(?P<my_e>[EeFfAa])?"                       # 3/27E, FY3/27
    r"|(?:FY|CY)['’]?(?P<fy_y>\d{2}|20\d{2})(?P<fy_e>[EeFfAa])?"                                  # FY2027, FY27E
    r"|(?P<y_y>20\d{2})(?P<y_e>[EeFfAa])?"                                                         # 2026E
    r"|(?P<h_n>\d{1,2})[MY]"                                                                     # 3M, 12M (horizons)
    r"|(?P<prev>Previous|Prior|Old|Initial|Original)|(?P<cur>Current|New|Revised|Updated)"
    r")(?![\w/])(?:\s?\((?:\d{1,2}[ -])?[A-Z][a-z]{2}[ -]\d{2,4}\))?")             # "Revised (1-Sep-26)"
HEADER_SHARE = 0.4                      # a header line is mostly periods
FIGURE = re.compile(r"\d+(?:[.,]\d+)*")
CELL_EDGE = re.compile(r" ?\| ?")        # cells joined by " | "; an empty cell's spaces collapse ("a | | b")
FIGURE_CELL = re.compile(r"[-+−(]?[$¥€£]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?%?\)?")


@dataclass(frozen=True)
class Period:
    text: str
    kind: str                           # date | quarter | year | horizon | prev | cur
    end: tuple[int, int] | None = None  # (year, month) the period ends in; a fiscal year's month is decided later
    day: int = 0                        # a date's day
    estimate: bool = False
    fiscal: bool = False                # a year whose end month is the company's fiscal year end
    plain: bool = False                 # a bare year ("2026E"): which fiscal year it names depends on the broker
    months: int = 0                     # a year's or quarter's length
    revision: str = ""                  # "prev" or "cur" when a second header line marks old and new estimates


def _est(mark: str | None) -> bool:
    """A period's suffix: E or F is an estimate, A an actual (or none)."""
    return bool(mark) and mark.lower() in "ef"


def _yy(y: str) -> int:
    return int(y) if len(y) == 4 else 2000 + int(y)


def period_of(m: re.Match) -> Period | None:
    g = m.groupdict()
    t = m.group(0)
    if g["fd_y"]:
        return Period(t, "date", (int(g["fd_y"]), int(g["fd_m"])), int(g["fd_d"]))
    if g["iso_y"]:
        return Period(t, "date", (int(g["iso_y"]), int(g["iso_m"])), int(g["iso_d"]))
    if g["dmy_y"]:
        return Period(t, "date", (int(g["dmy_y"]), MONTHS[g["dmy_mon"].lower()[:3]]), int(g["dmy_d"]))
    if g["dm_d"]:
        return Period(t, "date", (0, MONTHS[g["dm_mon"].lower()[:3]]), int(g["dm_d"]))   # the year: the document's
    for q, y, e in (("q_q", "q_y", "q_e"), ("q2_q", "q2_y", "q2_e")):
        if g[q]:
            return Period(t, "quarter", (_yy(g[y]), 3 * int(g[q])), estimate=_est(g[e]), months=3)
    if g["ym_y"]:
        month = int(g["ym_m"])
        return Period(t, "year", (int(g["ym_y"]), month), estimate=_est(g["ym_e"]), months=12) if 1 <= month <= 12 \
            else None
    if g["my_m"]:
        a, b = int(g["my_m"]), g["my_y"]
        month, year = (a, _yy(b)) if 1 <= a <= 12 else (int(b), _yy(str(a)))        # 3/27 is March 2027; 27/3 too
        if not 1 <= month <= 12:
            return None
        return Period(t, "year", (year, month), estimate=_est(g["my_e"]), months=12)
    if g["fy_y"]:
        return Period(t, "year", (_yy(g["fy_y"]), 12), estimate=_est(g["fy_e"]), fiscal=True, months=12)
    if g["y_y"]:
        return Period(t, "year", (int(g["y_y"]), 12), estimate=_est(g["y_e"]), fiscal=True, months=12, plain=True)
    if g["h_n"]:
        return Period(t, "horizon", estimate=True)
    return Period(t, "prev" if g["prev"] else "cur")


@dataclass(frozen=True)
class Header:
    periods: tuple[Period, ...]
    cells: tuple[int, ...] = ()         # for a spreadsheet row: each period's cell index


def cells_of(sent: str) -> list[tuple[int, int]]:
    """A spreadsheet row's cells, as spans of the row."""
    out, at = [], 0
    for m in CELL_EDGE.finditer(sent):
        out.append((at, m.start()))
        at = m.end()
    return [*out, (at, len(sent))]


def header_of(sent: str) -> Header | None:
    """A line of column periods ("Fiscal Year Ending 03/26 03/27e 03/28e", "FY2025 | Q1-2026 | Q2-2026"), or None. A
    spreadsheet's header row is the row of its periods among labels, with no figure of its own ("Series | Unit |
    30-Jun-2026 | 30-Sep-2026 | Current | Source")."""
    if CELL in sent:
        cells = [sent[a:b].strip() for a, b in cells_of(sent)]
        found = [(k, period_of(m)) for k, c in enumerate(cells) if (m := PERIOD.fullmatch(c))]
        found = [(k, p) for k, p in found if p is not None]
        at = {k for k, _p in found}
        filled = sum(1 for c in cells if c)
        figures = any(FIGURE_CELL.fullmatch(c) for k, c in enumerate(cells) if k not in at)
        if len(found) >= 2 and (len(found) * 2 >= filled or not figures):
            return Header(tuple(p for _k, p in found), tuple(k for k, _p in found))
        return None
    ms = [(m, period_of(m)) for m in PERIOD.finditer(sent)]
    ms = [(m, p) for m, p in ms if p is not None and p.kind not in ("prev", "cur")] or \
        [(m, p) for m, p in ms if p is not None]
    covered = sum(m.end() - m.start() for m, _p in ms)
    spans = [(m.start(), m.end()) for m, _p in ms]
    if any(not any(a <= d.start() and d.end() <= b for a, b in spans) for d in FIGURE.finditer(sent)):
        return None                                  # a figure that is not a period: a row or a sentence
    tail = len(ms) >= 2 and not sent[ms[-2][0].end():ms[-1][0].start()].strip() and not sent[ms[-1][0].end():].strip()
    marks = all(p.kind in ("prev", "cur") for _m, p in ms)      # "JPMe (New) JPMe (New) JPMe (Old)": a line of marks
    if len(ms) >= 2 and (covered >= HEADER_SHARE * len(sent.replace(" ", "")) or tail or marks) and len(sent) <= 300:
        return Header(tuple(p for _m, p in ms))
    return None


def revise(header: Header | None, marks: Header) -> Header | None:
    """A header of periods with a line of Old/New marks under it ("FY3/27 FY3/28 FY3/27 FY3/28" over "New New Old
    Old"): the periods, each marked old or new; None when the marks do not fit the periods."""
    if header is None or header.cells or len(marks.periods) != len(header.periods) \
            or any(p.kind in ("prev", "cur") for p in header.periods):
        return None
    return Header(tuple(replace(p, revision=q.kind) for p, q in zip(header.periods, marks.periods)))


def end_of(p: Period, fy_month: int, year: int) -> tuple[int, int, int]:
    """(year, month, day) a period ends on: a fiscal year in its company's month, a date without a year in `year`."""
    y, mo = p.end if p.end else (0, 0)
    if p.fiscal:
        mo = fy_month
    if p.kind == "date":
        return (y or year, mo, p.day)
    return (y, mo, calendar.monthrange(y, mo)[1] if y else 28)


def pick(periods: list[Period], *, flow: bool, date: datetime | None, fy_month: int = 12) -> int | None:
    """The column a value is read in: for a flow (a year's profit, income), the fiscal year the document's date falls
    in (else the first estimated year); for a level (a rate, a price, a ratio), a column headed "Current", else the
    latest full date, else the latest period that had ended by the document's date (else the last one), never an
    estimate."""
    today = (date.year, date.month, date.day) if date else None
    ends = [end_of(p, fy_month, today[0] if today else 0) for p in periods]
    if flow:
        # a bare year is ambiguous for a company whose fiscal year does not end in December ("2026E" is FY3/26 to
        # some, FY3/27 to others): such columns are not read
        years = [k for k, p in enumerate(periods) if p.kind == "year" and not (p.plain and fy_month != 12)]
        if today:
            inside = [k for k in years if _minus_months(ends[k], periods[k].months) < today <= ends[k]]
            return inside[0] if inside else None
        est = [k for k in years if periods[k].estimate]
        return est[0] if est else None
    current = [k for k, p in enumerate(periods) if p.kind == "cur"]
    if current:
        return current[-1]                           # "30-Jun-2026 | 30-Sep-2026 | Current": the current column
    dated = [k for k, p in enumerate(periods) if p.kind == "date" and p.end and p.end[0]]
    # an estimate is never a level, even for a period that has ended ("9/26E" in October): the latest actual is
    cands = [k for k in dated or [k for k, p in enumerate(periods) if p.kind in ("date", "quarter", "year")]
             if not periods[k].estimate]
    if today:
        cands = [k for k in cands if ends[k] <= today]
        return max(cands, key=lambda k: (ends[k], k)) if cands else None
    return cands[-1] if cands else None


def _minus_months(end: tuple[int, int, int], months: int) -> tuple[int, int, int]:
    y, m, _d = end
    k = y * 12 + (m - 1) - months
    return (k // 12, k % 12 + 1, 31)


class Cell(Protocol):
    unit: str                           # "%", "bp", ... or ""
    signed: bool                        # written with a sign: a change, not a level


C = TypeVar("C", bound=Cell)


def _style(n: Cell) -> tuple:
    return (n.unit, n.signed)


def align(periods: list[Period], run: list[C], *, rate: bool) -> tuple[list[Period], list[C]] | None:
    """Columns matched to cells: the whole header to the whole row, else the header's first block (up to a repeated
    period: side-by-side tables) to the row's first block (up to a change of style: a level, then its % changes),
    else the header to the row's cells in the value's own unit (a rate's percents among its bp changes)."""
    blocks = [periods]
    for k, p in enumerate(periods):
        if any(q.text == p.text for q in periods[:k]):
            blocks = [periods[:k]]
            break
    first = [run[0]]
    for n in run[1:]:
        if _style(n) != _style(first[0]):
            break
        first.append(n)
    own = [n for n in run if (n.unit == "%") == rate and n.unit in ("%", "")]
    for ps, ns in ((periods, run), (blocks[0], first), (periods, own)):
        if ps and len(ps) == len(ns):
            return ps, ns
    return None


