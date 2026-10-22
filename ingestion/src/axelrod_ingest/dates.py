"""Dates (Oct 22): when a document was published, and what period it is about, from its content or its file name, never guessed.

Two times, kept apart:

- **Published** is when the document became available: a date given with the upload, else the last full date in the file name
  (the packs name files `27-Mar-2026_...` or `2026-02-01_...` after their publication), else the first full date in the opening
  text. A file name without a date (`undated`, `current`, `period-2025`, `monthly-10th`, `Feb-2024`: a month is no day) gives
  nothing, and the caller falls back to when the file arrived, saying so.
- **Period** is what it reports on: the month of a monthly announcement ("for the month of August 2025"), a quarter, a half, a
  fiscal year, or an end date ("for the year ended 31 December 2025", "截至2026年6月30日"). It is read from the opening text, else
  the file name, and kept with its end date. A monthly announcement published on 1 September 2025 has period end 2025-08-31.

A date is a full day. English ("27 March 2026", "Mar 27, 2026", "2026-03-27"), Chinese ("2026年3月27日", "二零二六年三月二十七日"), and
Korean ("2026년 3월 27일", "2026. 03. 27.") forms are read. Years run 2000 to 2099: the filings are recent, and a page number is not a year.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from axelrod_ingest.tables import MONTHS

HEAD = 3000                               # the opening text a publication date is looked for in
PERIOD_HEAD = 8000                        # ... and a period
MON = r"(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
CN_DIGIT = {c: str(k) for k, c in enumerate("〇一二三四五六七八九")} | {"零": "0"}
DATE_PATTERNS = [
    re.compile(r"\b(?P<y>20\d{2})-(?P<m>\d{2})-(?P<d>\d{2})\b"),
    re.compile(rf"\b{MON}\s+(?P<d>\d{{1,2}}),?\s+(?P<y>20\d{{2}})\b"),
    re.compile(rf"\b(?P<d>\d{{1,2}})[\s-]+{MON},?[\s-]+(?P<y>20\d{{2}})\b"),
    re.compile(r"(?P<y>20\d{2})\s*[年년]\s*(?P<m>\d{1,2})\s*[月월]\s*(?P<d>\d{1,2})\s*[日일]"),
    re.compile(r"(?<![\d.])(?P<y>20\d{2})\.\s?(?P<m>\d{1,2})\.\s?(?P<d>\d{1,2})(?!\d)"),
    re.compile(r"(?P<y>[〇零一二三四五六七八九]{4})\s*年\s*(?P<m>[一二三四五六七八九十]{1,3})\s*月\s*(?P<d>[一二三四五六七八九十]{1,3})\s*日"),
]
# a date in a file name: 2026-02-01, 20260201, 27-Mar-2026 (the day is part of it; "Mar-2026" is not a date)
FILENAME_PATTERNS = [
    re.compile(r"(?<!\d)(?P<y>20\d{2})[-_]?(?P<m>[01]\d)[-_]?(?P<d>[0-3]\d)(?!\d)"),
    re.compile(rf"(?<!\d)(?P<d>\d{{1,2}})-{MON}-(?P<y>20\d{{2}})(?!\d)", re.I),
]
# "截至2026年6月30日止六个月": the six months ended; "截至2026年3月27日" alone is only "as at", and ends no period
ENDED_ZH = re.compile(r"(?:截至|截止)\s*(?P<date>20\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)\s*止\s*(?P<what>年度|年|期间|六个月|三个月|九个月|十二个月|季度)")
ENDED_EN = re.compile(r"(?:(?P<n>one|three|six|nine|twelve|\d{1,2})[- ]months?|(?P<year>(?:fiscal )?year)|(?P<q>quarter)|"
                      r"(?P<h>half(?:-year)?)|period)\s+(?:period\s+)?(?:ended|ending)\s+(?P<date>[A-Za-z0-9,.\s-]{6,24})", re.I)
MONTHS_BY_WORD = {"one": 1, "three": 3, "six": 6, "nine": 9, "twelve": 12}
MONTH_OF = re.compile(rf"\b(?:for|in)\s+the\s+month\s+of\s+{MON}\s+(?P<y>20\d{{2}})\b", re.I)
MONTH_FOR = re.compile(rf"\bFOR[\s-]+{MON}[\s-]+(?P<y>20\d{{2}})\b", re.I)    # "VOLUNTARY ANNOUNCEMENT ... FOR AUGUST 2025"
MONTH_ZH = re.compile(r"(?P<y>20\d{2})\s*年\s*(?P<m>\d{1,2})\s*月份")
MONTHLY_CUE = re.compile(r"monthly|production[-_ ]and[-_ ]sales|production[-_ ]sales|\bP-S\b|sales[-_ ]volume", re.I)
# a month and year in a name ("Jun-2026"), but not the month of a full date ("1-Jul-2026")
MONTH_NAME_YEAR = re.compile(rf"(?<![A-Za-z])(?<!\d[-_ ]){MON}[-_ ](?P<y>20\d{{2}})(?!\d)", re.I)
ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4, "一": 1, "二": 2, "三": 3, "四": 4, "1": 1, "2": 2, "3": 3, "4": 4}
QUARTERS = [re.compile(p, re.I) for p in (
    r"\bQ(?P<n>[1-4])[-\s]?(?P<y>20\d{2})\b", r"\b(?P<y>20\d{2})[-\s]?Q(?P<n>[1-4])\b", r"\b(?P<n>[1-4])Q[-\s]?(?P<y>20\d{2})\b",
    r"\b(?P<n>first|second|third|fourth)\s+quarter\s+(?:of\s+)?(?P<y>20\d{2})\b",
    r"(?P<y>20\d{2})\s*年\s*第?\s*(?P<n>[一二三四1-4])\s*季度", r"(?P<y>20\d{2})\s*년\s*(?P<n>[1-4])\s*분기")]
HALVES = [re.compile(p, re.I) for p in (
    r"\bH(?P<n>[12])[-\s]?(?P<y>20\d{2})\b", r"\b(?P<n>[12])H[-\s]?(?P<y>20\d{2})\b",
    r"\b(?P<n>first|second)\s+half\s+(?:of\s+)?(?P<y>20\d{2})\b", r"\binterim\s+(?:report|results)(?:\s+announcement)?\s+(?P<n>)(?P<y>20\d{2})\b",
    r"\b(?P<y>20\d{2})\s+(?P<n>)interim\s+(?:report|results)\b",
    r"(?P<y>20\d{2}|[〇零一二三四五六七八九]{4})\s*年\s*(?P<n>上半年|下半年|半年度)", r"(?P<y>20\d{2})\s*년\s*(?P<n>상반기|하반기|반기)")]
HALF_NUMBER = {**ORDINAL, "": 1, "上半年": 1, "半年度": 1, "下半年": 2, "상반기": 1, "반기": 1, "하반기": 2}
YEARS = [re.compile(p, re.I) for p in (
    r"\bFY\s?(?P<y>20\d{2})\b", r"\b(?:full[- ]year|annual(?: report)?)\s+(?:results\s+)?(?:for\s+)?(?:the\s+year\s+)?(?P<y>20\d{2})\b",
    r"\b(?P<y>20\d{2})\s+annual\s+(?:report|results)\b",
    r"(?P<y>20\d{2}|[〇零一二三四五六七八九]{4})\s*年\s*(?:度|年度|年报|年度报告)", r"(?P<y>20\d{2})\s*년\s*(?:도|사업)")]


@dataclass(frozen=True)
class Period:
    end: date
    kind: str                              # month | quarter | half | year | date
    label: str                             # 2025-08, 2026-Q2, 2026-H1, 2025, or the end date
    source: str                            # content | filename
    match: str                             # the words it was read from


@dataclass(frozen=True)
class Dates:
    published: datetime | None
    source: str                            # upload | manifest | filename | content, "" when the document gives no date
    period: Period | None = None

    @property
    def forward(self) -> bool:
        """Whether the period ends after the document was published: a guidance or an outlook, not what happened."""
        return bool(self.period and self.published and self.period.end > self.published.date())

    def meta(self) -> dict[str, Any]:
        out: dict[str, Any] = {"published_source": self.source or "ingested_at"}
        if self.published is not None:
            out["published_at"] = self.published.isoformat()
        if self.period is not None:
            out.update({"period_end": self.period.end.isoformat(), "period": self.period.label,
                        "period_kind": self.period.kind, "period_source": self.period.source,
                        "period_match": self.period.match})
            if self.forward:
                out["period_forward"] = True
            elif self.published is not None:
                out["published_lag_days"] = (self.published.date() - self.period.end).days
        return out


def _utc(y: int, m: int, d: int) -> datetime | None:
    try:
        return datetime(y, m, d, tzinfo=UTC)
    except ValueError:
        return None


def chinese_number(s: str) -> int | None:
    """A Chinese numeral below 40 (十, 十一, 二十, 二十三, 三十一), or None."""
    if s.startswith("十"):
        tens, rest = 1, s[1:]
    elif len(s) >= 2 and s[1] == "十":
        tens, rest = "一二三".find(s[0]) + 1, s[2:]
        tens = tens or None
    else:
        tens, rest = 0, s
    ones = {"": 0, **{c: k + 1 for k, c in enumerate("一二三四五六七八九")}}.get(rest)
    return None if tens is None or ones is None else tens * 10 + ones


def _year(text: str) -> int:
    return int("".join(CN_DIGIT.get(c, c) for c in text))


def _part(g: dict, key: str) -> int | None:
    v = g.get(key)
    return None if v is None else int(v) if v.isdigit() else chinese_number(v)


def date_of(m: re.Match) -> datetime | None:
    """The day a date pattern's match names, or None when it is no real day."""
    g = m.groupdict()
    mon = g.get("mon")
    month = MONTHS[mon.lower()[:3]] if mon else _part(g, "m")
    day = _part(g, "d")
    return _utc(_year(g["y"]), month, day) if month and day else None


def dates_in(text: str) -> list[tuple[int, datetime]]:
    """Every full date in `text` with where it starts, in order of position."""
    found = [(m.start(), dt) for pat in DATE_PATTERNS for m in pat.finditer(text) if (dt := date_of(m))]
    return sorted(found)


def filename_date(name: str) -> datetime | None:
    """The latest full date in a file name (a name of several dates is available from the last), or None."""
    found = [dt for pat in FILENAME_PATTERNS for m in pat.finditer(name) if (dt := date_of(m))]
    return max(found) if found else None


def _end_of_month(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def _label(end: date, kind: str) -> str:
    """A period as its usual short name where its end date allows (calendar quarters, halves, years), else the end date."""
    last = end.day == calendar.monthrange(end.year, end.month)[1]
    if kind == "year" and (end.month, end.day) == (12, 31):
        return str(end.year)
    if kind == "half" and end.month in (6, 12) and last:
        return f"{end.year}-H{end.month // 6}"
    if kind == "quarter" and end.month % 3 == 0 and last:
        return f"{end.year}-Q{end.month // 3}"
    if kind == "month" and last:
        return f"{end.year}-{end.month:02d}"
    return end.isoformat()


def _period(match: re.Match, source: str, end: date, kind: str, label: str) -> Period:
    return Period(end, kind, label, source, " ".join(match.group(0).split())[:80])


def _ended(text: str, source: str) -> Period | None:
    m = ENDED_ZH.search(text)
    if m and (dt := dates_in(m.group("date"))):
        kind = {"年度": "year", "年": "year", "十二个月": "year", "六个月": "half", "三个月": "quarter", "季度": "quarter"}.get(
            m.group("what"), "date")
        end = dt[0][1].date()
        return _period(m, source, end, kind, _label(end, kind))
    for m in ENDED_EN.finditer(text):
        dt = dates_in(m.group("date"))
        if not dt:
            continue
        end = dt[0][1].date()
        months = MONTHS_BY_WORD.get((m.group("n") or "").lower()) or (int(m.group("n")) if m.group("n") else 0)
        kind = ("month" if months == 1 else "quarter" if months == 3 else "half" if months == 6 else "year" if months == 12
                else "year" if m.group("year") else "quarter" if m.group("q") else "half" if m.group("h") else "date")
        return _period(m, source, end, kind, _label(end, kind))
    return None


def _month(text: str, source: str, cue: bool) -> Period | None:
    m = MONTH_OF.search(text) or (MONTH_FOR.search(text) or MONTH_NAME_YEAR.search(text) if cue else None)
    if m:
        y, mo = int(m.group("y")), MONTHS[m.group("mon").lower()[:3]]
        return _period(m, source, _end_of_month(y, mo), "month", f"{y}-{mo:02d}")
    m = MONTH_ZH.search(text)
    if m and 1 <= int(m.group("m")) <= 12:
        y, mo = int(m.group("y")), int(m.group("m"))
        return _period(m, source, _end_of_month(y, mo), "month", f"{y}-{mo:02d}")
    return None


def _first(patterns: list[re.Pattern], text: str) -> re.Match | None:
    """The match that starts earliest in the text, of any of the patterns (the title's period before a table's)."""
    found = [m for p in patterns if (m := p.search(text))]
    return min(found, key=lambda m: m.start()) if found else None


def _quarter(text: str, source: str) -> Period | None:
    m = _first(QUARTERS, text)
    if m is None:
        return None
    q, y = ORDINAL[m.group("n").lower()], _year(m.group("y"))
    return _period(m, source, _end_of_month(y, 3 * q), "quarter", f"{y}-Q{q}")


def _half(text: str, source: str) -> Period | None:
    m = _first(HALVES, text)
    if m is None:
        return None
    h, y = HALF_NUMBER[m.group("n").lower()], _year(m.group("y"))
    return _period(m, source, _end_of_month(y, 6 * h), "half", f"{y}-H{h}")


def _fiscal_year(text: str, source: str) -> Period | None:
    m = _first(YEARS, text)
    if m is None:
        return None
    y = _year(m.group("y"))
    return _period(m, source, date(y, 12, 31), "year", str(y))


def period_of(text: str, filename: str = "") -> Period | None:
    """What the document reports on, from its opening text, else its file name: an end date, a month, a quarter, a half, a year
    (in that order within each; the calendar year, as the three issuers' fiscal years are). None when neither says."""
    for source, where in (("content", text[:PERIOD_HEAD]), ("filename", filename.replace("_", " "))):
        cue = bool(MONTHLY_CUE.search(where))
        for got in (_ended(where, source), _month(where, source, cue), _quarter(where, source), _half(where, source),
                    _fiscal_year(where, source)):
            if got is not None:
                return got
    return None


def resolve(text: str, filename: str = "", *, upload: datetime | None = None, manifest: bool = False,
            not_after: datetime | None = None) -> Dates:
    """A document's dates. Published: the upload's date; else, for a file a manifest lists (its name was written for the
    publication), the file name's; else the first full date in the opening text; else the file name's; else none. A date
    after `not_after` (when the document arrived) cannot be its publication and is passed over. And the period it is about."""
    period = period_of(text, filename)
    if upload is not None:
        return Dates(upload, "upload", period)

    def possible(d: datetime | None) -> datetime | None:
        return d if d is not None and (not_after is None or d <= not_after) else None

    named = possible(filename_date(filename))
    if manifest and named is not None:
        return Dates(named, "manifest", period)
    found = [dt for _p, dt in dates_in(text[:HEAD]) if possible(dt)]
    if found:
        return Dates(found[0], "content", period)
    return Dates(named, "filename" if named else "", period)
