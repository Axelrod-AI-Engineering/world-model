"""Dates: published and period kept apart, read from content or the file name, never guessed from a name that holds no date."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from axelrod_ingest.dates import Dates, chinese_number, dates_in, filename_date, period_of, resolve


def d(y: int, m: int, day: int) -> datetime:
    return datetime(y, m, day, tzinfo=UTC)


@pytest.mark.parametrize("text,want", [
    ("on 2026-03-27 the board", [d(2026, 3, 27)]),
    ("Mar. 27, 2026 and 5 September 2025", [d(2026, 3, 27), d(2025, 9, 5)]),
    ("以2026年3月27日为基准日", [d(2026, 3, 27)]),
    ("二零二六年三月二十七日，二零二五年十二月三十一日", [d(2026, 3, 27), d(2025, 12, 31)]),
    ("2026년 3월 27일 현재, 2026. 07. 23. 공시", [d(2026, 3, 27), d(2026, 7, 23)]),
    ("2026.7.23", [d(2026, 7, 23)]),
    ("2026-02-30 and 2026年13月1日 and 二零二六年二十月一日 and 2026.12", []),         # not real days
    ("page 2026 of 3000", []),
    ("FOR THE THREE-MONTH PERIOD ENDED\nMARCH 31, 2026 and 31 MARCH 2026 and SEPT 5, 2026", [d(2026, 3, 31), d(2026, 3, 31), d(2026, 9, 5)]),
])
def test_dates_in(text, want):
    assert [x for _p, x in dates_in(text)] == want


def test_dates_come_in_order_of_position():
    text = "later 2026-05-01 earlier 1 Jan 2026"
    assert [p for p, _ in dates_in(text)] == [text.index("2026-05"), text.index("1 Jan")]


@pytest.mark.parametrize("s,want", [("十", 10), ("十一", 11), ("二十", 20), ("二十三", 23), ("三十一", 31), ("一", 1), ("九", 9),
                                    ("四十", None), ("一二", None), ("二十十", None)])
def test_chinese_number(s, want):
    assert chinese_number(s) == want


@pytest.mark.parametrize("name,want", [
    ("001_1_27-Mar-2026_FY2025-annual-results.pdf", d(2026, 3, 27)),
    ("001_2_2025-09-01_VOLUNTARY-ANNOUNCEMENT-FOR-AUGUST-2025.pdf", d(2025, 9, 1)),
    ("note_20260201.md", d(2026, 2, 1)),
    ("001_1_29-Jan-2026_Q4-2025-call-transcript.html", d(2026, 1, 29)),
    ("001_1_15-Apr-2025-15-May-2025_Prior-IR-records.pdf", d(2025, 5, 15)),          # several dates: the last
    ("001_3_3-4-Jul-2025_Regulator-signal.html", d(2025, 7, 4)),
    ("001_3_19-May-20-May-2025_IPO-allotment.pdf", d(2025, 5, 20)),
    ("001_3_30-Jan-2026-27-Nov-2024_Buyback.html", d(2026, 1, 30)),
    # names that hold no date
    ("001_2_undated_HKEX-announcements.html", None), ("001_1_current_Financial-highlights.html", None),
    ("001_1_period-2025-Q4_2025-Q4-Earnings-presentation.pdf", None), ("001_1_monthly-10th_STATS.pdf", None),
    ("001_2_1st-2nd-of-each-month_Monthly-P-S-back-series.pdf", None), ("001_3_Feb-2024_Ratings.html", None),
    ("001_1_Jan-Jul-2026-Sep-2026_Industry-Research.html", None), ("report_2026-13-45.txt", None), ("31-Feb-2026_x.pdf", None),
])
def test_filename_date(name, want):
    assert filename_date(name) == want


@pytest.mark.parametrize("text,name,end,kind,label,source", [
    ("for the year ended 31 December 2025", "", date(2025, 12, 31), "year", "2025", "content"),
    ("For the six months ended 30 June 2026 (unaudited)", "", date(2026, 6, 30), "half", "2026-H1", "content"),
    ("for the three months ended 30 September 2026", "", date(2026, 9, 30), "quarter", "2026-Q3", "content"),
    ("for the nine months ended 30 September 2026", "", date(2026, 9, 30), "date", "2026-09-30", "content"),
    ("for the 1 month ended 31 July 2026", "", date(2026, 7, 31), "month", "2026-07", "content"),
    ("for the 12-month period ended March 31, 2026", "", date(2026, 3, 31), "year", "2026-03-31", "content"),      # a March year: the date
    ("for the fiscal year ended 31 March 2026", "", date(2026, 3, 31), "year", "2026-03-31", "content"),
    ("the quarter ended 30 June 2026", "", date(2026, 6, 30), "quarter", "2026-Q2", "content"),
    ("the half-year ended 30 June 2026", "", date(2026, 6, 30), "half", "2026-H1", "content"),
    ("the period ending 31 May 2026", "", date(2026, 5, 31), "date", "2026-05-31", "content"),
    ("for the three months ended 31 July 2026", "", date(2026, 7, 31), "quarter", "2026-07-31", "content"),
    ("INTERIM FINANCIAL STATEMENTS\nFOR THE THREE-MONTH PERIOD ENDED\nMARCH 31, 2026 (Unaudited)", "", date(2026, 3, 31), "quarter", "2026-Q1", "content"),
    ("for the six months ended 30 September 2026", "", date(2026, 9, 30), "half", "2026-09-30", "content"),
    ("for the six months ended 31 December 2025", "", date(2025, 12, 31), "half", "2025-H2", "content"),
    ("for the 1 month ended 15 July 2026", "", date(2026, 7, 15), "month", "2026-07-15", "content"),
    ("截至2026年6月30日止六个月", "", date(2026, 6, 30), "half", "2026-H1", "content"),
    ("截至2025年12月31日止年度", "", date(2025, 12, 31), "year", "2025", "content"),
    ("截至2026年9月30日止三个月", "", date(2026, 9, 30), "quarter", "2026-Q3", "content"),
    ("截至2026年9月30日止期间", "", date(2026, 9, 30), "date", "2026-09-30", "content"),
    ("截至2026年3月27日，公司股本为", "", None, None, None, None),                   # "as at": no period
    # a month
    ("the total production and sales volume of the Company for the month of August 2025 (Units)", "", date(2025, 8, 31),
     "month", "2025-08", "content"),
    ("VOLUNTARY ANNOUNCEMENT PRODUCTION AND SALES VOLUME FOR AUGUST 2025", "", date(2025, 8, 31), "month", "2025-08", "content"),
    ("", "001_1_1-Jul-2026_Monthly-P-S-Jun-2026.pdf", date(2026, 6, 30), "month", "2026-06", "filename"),
    ("", "001_2_2026-02-01_VOLUNTARY-ANNOUNCEMENT-PRODUCTION-AND-SALES-VOLUME-FOR-JANUARY-2026.pdf", date(2026, 1, 31),
     "month", "2026-01", "filename"),
    ("2026年9月份产销快报", "", date(2026, 9, 30), "month", "2026-09", "content"),
    ("2026年13月份产销", "", None, None, None, None),
    # a quarter
    ("Q2 2026 results", "", date(2026, 6, 30), "quarter", "2026-Q2", "content"),
    ("2026-Q3 report", "", date(2026, 9, 30), "quarter", "2026-Q3", "content"),
    ("3Q26 report 3Q2026", "", date(2026, 9, 30), "quarter", "2026-Q3", "content"),
    ("results for the first quarter of 2026", "", date(2026, 3, 31), "quarter", "2026-Q1", "content"),
    ("2026 FIRST QUARTERLY REPORT", "", date(2026, 3, 31), "quarter", "2026-Q1", "content"),
    ("Third Quarterly Report 2025", "", date(2025, 9, 30), "quarter", "2025-Q3", "content"),
    ("the second quarter results 2026", "", date(2026, 6, 30), "quarter", "2026-Q2", "content"),
    ("2026年第三季度报告", "", date(2026, 9, 30), "quarter", "2026-Q3", "content"),
    ("2026 년 1 분기 실적", "", date(2026, 3, 31), "quarter", "2026-Q1", "content"),
    ("", "001_1_period-2026-Q1_2026-Q1-Earnings-presentation.pdf", date(2026, 3, 31), "quarter", "2026-Q1", "filename"),
    # a half
    ("H1 2026 interim", "", date(2026, 6, 30), "half", "2026-H1", "content"),
    ("INTERIM REPORT 2026 Contents", "", date(2026, 6, 30), "half", "2026-H1", "content"),
    ("2026 interim results of the Group", "", date(2026, 6, 30), "half", "2026-H1", "content"),
    ("Interim Results Announcement 2025", "", date(2025, 6, 30), "half", "2025-H1", "content"),
    ("2H 2025 outlook", "", date(2025, 12, 31), "half", "2025-H2", "content"),
    ("the second half of 2025", "", date(2025, 12, 31), "half", "2025-H2", "content"),
    ("艾克米股份有限公司 2026 年半年度报告", "", date(2026, 6, 30), "half", "2026-H1", "content"),
    ("二零二六年上半年，本集团", "", date(2026, 6, 30), "half", "2026-H1", "content"),
    ("2025 年下半年", "", date(2025, 12, 31), "half", "2025-H2", "content"),
    ("2026 년 상반기 영업실적, 2025년 하반기", "", date(2026, 6, 30), "half", "2026-H1", "content"),
    ("", "001_Interim-Report_2026-08-28_H1-2026_English-Chinese.pdf", date(2026, 6, 30), "half", "2026-H1", "filename"),
    # a year
    ("FY2025 annual results", "", date(2025, 12, 31), "year", "2025", "content"),
    ("2025 Annual Report of the Company", "", date(2025, 12, 31), "year", "2025", "content"),
    ("2025 Environmental, Social and Governance (ESG) Report", "", date(2025, 12, 31), "year", "2025", "content"),
    ("2025 Sustainability Report", "", date(2025, 12, 31), "year", "2025", "content"),
    ("Annual Report 2025", "", date(2025, 12, 31), "year", "2025", "content"),
    ("full-year results for the year 2025", "", date(2025, 12, 31), "year", "2025", "content"),
    ("2025年年度报告", "", date(2025, 12, 31), "year", "2025", "content"),
    ("二零二五年年度报告", "", date(2025, 12, 31), "year", "2025", "content"),
    ("2025 년도 사업보고서", "", date(2025, 12, 31), "year", "2025", "content"),
    ("", "001_1_period-2025_FY2025-Business-Report-Korean.pdf", date(2025, 12, 31), "year", "2025", "filename"),
    # none
    ("A page about the plant", "001_2_undated_HKEX.html", None, None, None, None),
])
def test_period_of(text, name, end, kind, label, source):
    p = period_of(text, name)
    if end is None:
        assert p is None
    else:
        assert (p.end, p.kind, p.label, p.source) == (end, kind, label, source)


def test_the_periods_title_comes_before_a_later_mention_and_content_before_the_file_name():
    p = period_of("Q2 2026 results. Compared with Q2 2025 and Q1 2026", "x_FY2024.pdf")
    assert p.label == "2026-Q2" and p.source == "content" and p.match == "Q2 2026"
    assert period_of("nothing here", "x_FY2024.pdf").source == "filename"


def test_an_end_date_beats_a_mention_of_quarters():
    assert period_of("Q1 2026 table. For the year ended 31 December 2025", "").label == "2025"


def test_ended_without_a_real_date_is_skipped():
    assert period_of("the year ended soon, the half-year ended 31 June 2026", "") is None


def test_a_date_after_arrival_cannot_be_its_publication():
    arrived = d(2026, 10, 22)
    got = resolve("Investor page. Statements for 31 December 2026 and 2018-12-31.", "x_current_page.html", not_after=arrived)
    assert (got.published, got.source) == (d(2018, 12, 31), "content")
    assert resolve("Due 2027-01-01.", "a_2027-01-01_x.pdf", manifest=True, not_after=arrived) == Dates(None, "", None)
    assert resolve("on 2026-10-22", "x.pdf", not_after=arrived).published == arrived            # arrival itself is fine


def test_a_period_after_publication_is_forward_and_a_period_before_it_has_a_lag():
    fwd = resolve("2026 annual guidance. FY2026", "x_29-Jan-2026_guidance.pdf", manifest=True)
    assert fwd.forward and fwd.meta()["period_forward"] is True and "published_lag_days" not in fwd.meta()
    back = resolve("results for the year ended 31 December 2025", "x_27-Mar-2026_results.pdf", manifest=True)
    assert not back.forward and back.meta()["published_lag_days"] == 86 and "period_forward" not in back.meta()
    assert not resolve("FY2025", "x_undated.pdf", manifest=True).forward and resolve("", "x.pdf").forward is False


def test_resolve_prefers_upload_then_manifest_name_then_content_then_name():
    text = "Note of 5 October 2026. For the year ended 31 December 2025."
    name = "x_27-Mar-2026_report.pdf"
    up = d(2026, 1, 1)
    assert resolve(text, name, upload=up, manifest=True) == Dates(up, "upload", period_of(text, name))
    got = resolve(text, name, manifest=True)
    assert (got.published, got.source) == (d(2026, 3, 27), "manifest") and got.period.end == date(2025, 12, 31)
    got = resolve(text, name)
    assert (got.published, got.source) == (d(2026, 10, 5), "content")
    got = resolve("no dates here", name)
    assert (got.published, got.source) == (d(2026, 3, 27), "filename")
    got = resolve("no dates here", "a_undated_report.pdf", manifest=True)
    assert got == Dates(None, "", None)
    assert resolve("no dates", "a_undated.pdf", manifest=True).meta() == {"published_source": "ingested_at"}


def test_dates_meta_records_both_times_and_the_evidence():
    got = resolve("", "001_1_1-Sep-2025_Monthly-P-S-Aug-2025.pdf", manifest=True)
    assert got.meta() == {"published_source": "manifest", "published_at": "2025-09-01T00:00:00+00:00",
                          "period_end": "2025-08-31", "period": "2025-08", "period_kind": "month", "period_source": "filename",
                          "period_match": "Aug-2025", "published_lag_days": 1}
