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
