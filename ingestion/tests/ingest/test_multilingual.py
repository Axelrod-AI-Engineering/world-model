"""Chinese and Korean text through recognition and extraction: names found by their characters, figures with CJK scales,
currencies and units, a bare ¥ read as yen or yuan. Every sentence is invented."""

from __future__ import annotations

from axelrod_ingest.contract.world_view import EntityView, ValueView, WorldView
from axelrod_ingest.extract import claims_of_chunk
from axelrod_ingest.gazetteer import Gazetteer
from axelrod_ingest.parse import normalize
from axelrod_ingest.text import tokens
from tests.ingest.multilingual import rules, world


def found(text: str) -> list[tuple]:
    return [(m.kind, m.entity_id, m.subentity_id, m.surface) for m in Gazetteer(world()).find(text)]


def signals(text: str, yen: str = "¥") -> list[tuple]:
    claims, _ = claims_of_chunk(rules(yen), 0, normalize(text), None)       # as the pipeline reads it
    return [(f.type, f.value_of, round(f.value, 6) if f.value is not None else round(f.delta, 6)) for f in claims.found]


def test_tokens_are_one_per_ideograph_or_syllable_and_keep_words_and_signs():
    assert [t for t, _a, _b in tokens("AEV 艾克米 영업이익은 ₩3tn")] == ["AEV", "艾", "克", "米", "영", "업", "이", "익", "은", "₩", "3tn"]


def test_names_are_found_by_their_characters_in_unspaced_text():
    assert found("艾克米电动上半年营业收入增长") == [("entity", "acme_ev", None, "艾克米电动"),
                                                    ("value", "acme_ev", "acme_ev.revenue", "营业收入")]
    assert found("에이크미코리아는 영업이익이 늘었다")[:2] == [("entity", "acme_kr", None, "에이크미코리아"),
                                                         ("value", "acme_kr", "acme_kr.operating_profit", "영업이익")]
    assert found("艾克米電動 淨利潤")[1][2] == "acme_ev.net_profit"                  # traditional characters


def test_a_short_alias_matches_only_at_the_start_of_a_run_never_inside_a_longer_word():
    view = WorldView(entities={"e": EntityView("e", "Eco", "company", ("艾克",), "CN", "autos", ("e.rev",))},
                     values={"e.rev": ValueView("e.rev", "e", "Eco revenue", "revenue_flow", unit="CNY bn/yr", scale=0.3,
                                                family="lognormal", mean=100.0, sd=30.0, aliases=("收入", "营业收入"))})
    gz = Gazetteer(view)

    def surfaces(text: str) -> list[str]:
        return [m.surface for m in gz.find(text, "e")]

    assert surfaces("利息收入增长") == []                     # interest income is not revenue
    assert surfaces("收入增长") == ["收入"]                   # at the start of a run
    assert surfaces("艾克的收入增长") == ["艾克", "收入"]      # after the particle 的 ("the company's revenue")
    assert surfaces("其他营业收入") == ["营业收入"]            # a longer alias matches inside a run
    assert surfaces("Revenue 收入") == ["收入"]               # after a space


def test_a_level_in_chinese_with_a_cny_scale():
    assert signals("艾克米电动营业收入为人民币1,200亿元。") == [("observe", "acme_ev.revenue", 120.0)]
    assert signals("艾克米电动净利润：人民币85.6亿元") == [("observe", "acme_ev.net_profit", 8.56)]
    assert signals("艾克米电动的销量达到420万辆。") == [("observe", "acme_ev.units", 4.2)]


def test_a_year_is_not_a_figure():
    assert signals("艾克米电动2026年营业收入为人民币1,200亿元。") == [("observe", "acme_ev.revenue", 120.0)]
    assert signals("艾克米电动营业收入为2026年") == []


def test_a_level_in_korean_with_scales_and_the_won():
    assert signals("에이크미코리아 매출액은 258조원을 기록했다.") == [("observe", "acme_kr.revenue", 258.0)]
    assert signals("에이크미코리아 영업이익은 3조 5,000억원이다.") == [("observe", "acme_kr.operating_profit", 3.5)]
    assert signals("에이크미코리아 영업이익은 순위 3위") == []                     # a rank is not a figure


def test_a_figure_in_the_wrong_currency_is_not_the_values():
    assert signals("에이크미코리아 매출액은 HK$258조") == []
    assert signals("艾克米电动营业收入为美元1,200亿元") == []


def test_a_bare_yen_sign_is_the_documents_yuan_or_yen():
    text = "Acme EV revenue was ¥120bn."
    assert signals(text, "CNY") == [("observe", "acme_ev.revenue", 120.0)]
    assert signals(text, "¥") == []                                   # the yen is not the yuan the value is in
    assert signals("Acme Japan revenue was ¥41tn.", "¥") == [("observe", "acme_jp.revenue", 41.0)]
    assert signals("Acme Japan revenue was ¥41tn.", "CNY") == []
    assert signals("Acme Japan revenue was JP¥41tn.", "CNY") == [("observe", "acme_jp.revenue", 41.0)]   # named, so kept


def test_a_half_year_or_a_quarter_is_not_a_years_flow():
    assert signals("2026年上半年，艾克米电动营业收入为人民币600亿元。") == []
    assert signals("2026年第三季度，艾克米电动净利润为人民币22亿元。") == []
    assert signals("艾克米电动2026年前三季度营业收入为人民币900亿元。") == []
    assert signals("에이크미코리아 2026년 상반기 매출액은 120조원이다.") == []
    assert signals("에이크미코리아 3분기 영업이익은 3조원이다.") == []
    assert signals("艾克米电动2025年度营业收入为人民币1,200亿元。") == [("observe", "acme_ev.revenue", 120.0)]


def test_a_flow_is_not_read_in_a_table_dated_inside_the_year():
    header = "Group results 30 June 2026 2025\n"
    claims, _ = claims_of_chunk(rules("CNY"), 0, header + "Acme EV revenue 14,743 18,719\n", None)
    assert claims.found == []


def test_a_report_of_last_year_is_not_history_for_a_document_about_that_year():
    from datetime import UTC, datetime

    from axelrod_ingest.extract import Reading
    text = normalize("艾克米电动2025年度营业收入为人民币1,200亿元。")
    published = datetime(2026, 3, 27, tzinfo=UTC)
    plain, _ = claims_of_chunk(rules("CNY"), 0, text, Reading(date=published))
    assert plain.found == []                                           # about 2025, in a note of 2026: history
    about, reading = claims_of_chunk(rules("CNY"), 0, text, Reading(date=published, ref=datetime(2025, 12, 31, tzinfo=UTC)))
    assert [(f.value_of, f.value) for f in about.found] == [("acme_ev.revenue", 120.0)]
    assert reading.when == datetime(2025, 12, 31, tzinfo=UTC) and Reading(date=published).when == published
    assert Reading().when is None


def test_a_years_flow_in_a_table_is_read_in_the_year_the_document_reports_on():
    from datetime import UTC, datetime

    from axelrod_ingest.extract import Reading
    table = "Fiscal year ending 2025 2024\nAcme EV revenue 120 110\n"
    published = datetime(2026, 3, 27, tzinfo=UTC)
    none, _ = claims_of_chunk(rules("CNY"), 0, table, Reading(date=published))
    got, _ = claims_of_chunk(rules("CNY"), 0, table, Reading(date=published, ref=datetime(2025, 12, 31, tzinfo=UTC)))
    assert none.found == [] and [(f.value_of, f.value) for f in got.found] == [("acme_ev.revenue", 120.0)]


def test_a_bare_year_is_never_a_level():
    from axelrod_ingest.extract import numbers
    assert [n.year for n in numbers("2025 and 2,025 and 2025bn and 1999.5 and 3025 and +2025 and 2025%")] == [
        True, False, False, False, False, False, False]
    assert signals("营业收入列示如下:\n2025 2024\n二零二五年 二零二四年") == []
    assert signals("Acme EV revenue | 2025") == [] and signals("Acme EV revenue 2025") == []


def test_a_table_row_is_no_key_data_line_and_a_scale_less_flow_is_no_level():
    assert signals("Acme EV net profit 7 (15,510) (18,356) (18,606)") == []       # a note number, then the columns
    assert signals("Acme EV net profit RMB 10") == []                               # ten yuan, not ten billion
    assert signals("Acme EV net profit RMB 10bn") == [("observe", "acme_ev.net_profit", 10.0)]


def test_a_remark_beside_a_rows_figures_is_no_move():
    row = "Investment income 2,688,328 1,339,222 100.74% Increase in net profit of certain investee companies"
    assert signals("Acme EV " + row) == []
    assert signals("Acme EV net profit increase by 10%") == [("move", "acme_ev.net_profit", 0.1)]


def test_a_forecast_in_chinese_or_korean_is_no_level_and_a_quarter_mark_stops_a_flow():
    assert signals("彭博预计艾克米电动净利润约85.6亿元。") == []
    assert signals("艾克米电动净利润约85.6亿元。") == [("observe", "acme_ev.net_profit", 8.56)]
    assert signals("艾克米电动Q1净利润为人民币22亿元。") == [] and signals("艾克米电动3Q净利润为人民币22亿元。") == []
    assert signals("시장은 에이크미코리아 영업이익이 3조원일 것으로 예상했다.") == []
