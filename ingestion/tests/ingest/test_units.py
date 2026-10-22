"""Currencies, scales, and the yen sign: English, Chinese, and Korean figures, and how a bare ¥ is resolved from the
document. Every sentence is invented."""

from __future__ import annotations

import pytest

from axelrod_ingest.extract import numbers
from axelrod_ingest.units import (
    issuer_country,
    language_of,
    resolve_yen,
    scale_hint,
    scale_value,
    tail_value,
)


def read(text: str, yen: str = "¥") -> list[tuple]:
    return [(round(n.value, 6), n.unit, n.currency, n.scale) for n in numbers(text, yen)]


@pytest.mark.parametrize("text,want", [
    # Chinese: 万 1e4, 亿 1e8, 万亿 1e12, 千 1e3, 百万 1e6, 十亿 1e9
    ("收入约人民币 344,815 百万元", [(344815.0, "", "CNY", 1e6)]),
    ("研发投入约人民币289亿元", [(289.0, "", "CNY", 1e8)]),
    ("规模达3.2万亿元", [(3.2, "", "CNY", 1e12)]),
    ("销量42.6万辆", [(42.6, "", "", 1e4)]),
    ("融资5千万元", [(5.0, "", "CNY", 1e7)]),
    ("规模12十亿元", [(12.0, "", "CNY", 1e9)]),
    ("募资3,000千元", [(3000.0, "", "CNY", 1e3)]),
    ("利润1,234元", [(1234.0, "", "CNY", 1.0)]),
    ("利润 500 美元", [(500.0, "", "$", 1.0)]),
    ("募资 43 亿港元", [(43.0, "", "HKD", 1e8)]),
    ("交易 3000 万日元", [(3000.0, "", "¥", 1e4)]),
    ("同比增长15.3%，利润率提高2.1个百分点", [(15.3, "%", "", 1.0), (2.1, "pp", "", 1.0)]),
    ("净利润1,234亿，同比下降7.13%", [(1234.0, "", "", 1e8), (7.13, "%", "", 1.0)]),   # a figure right after an ideograph
    ("人民幣 12 億元", [(12.0, "", "CNY", 1e8)]),                                     # traditional characters
    # Korean: 천 1e3, 만 1e4, 억 1e8, 조 1e12, and amounts that add smaller scales
    ("매출액 258조원", [(258.0, "", "KRW", 1e12)]),
    ("영업이익 3조 5,000억원", [(3.5, "", "KRW", 1e12)]),
    ("자사주 3억 5천만원", [(3.5, "", "KRW", 1e8)]),
    ("배당 5천만 원", [(5.0, "", "KRW", 1e7)]),
    ("백만원 단위 12 백만원", [(12.0, "", "KRW", 1e6)]),
    ("차량 12만 대", [(12.0, "", "", 1e4)]),
    ("영업이익률 5.2%p 개선", [(5.2, "pp", "", 1.0)]),
    ("제3조에 따라", [(3.0, "", "", 1.0)]),                                         # an article of a law is no trillion
    ("3조치를 취했다", [(3.0, "", "", 1.0)]),                                        # nor the start of a word
    # codes and signs
    ("KRW 400.7bn and ₩1.2tn", [(400.7, "", "KRW", 1e9), (1.2, "", "KRW", 1e12)]),
    ("HK$43bn, HKD 43 billion", [(43.0, "", "HKD", 1e9), (43.0, "", "HKD", 1e9)]),
    ("RMB 1,000 and 11.06 CNY and CN¥5", [(1000.0, "", "CNY", 1.0), (11.06, "", "CNY", 1.0), (5.0, "", "CNY", 1.0)]),
    ("JP¥5bn, 5,000円, 5 JPY", [(5.0, "", "¥", 1e9), (5000.0, "", "¥", 1.0), (5.0, "", "¥", 1.0)]),
    ("1,000원", [(1000.0, "", "KRW", 1.0)]),
    ("a 10 year bond and FY26", [(10.0, "", "", 1.0)]),
])
def test_figures(text, want):
    assert read(text) == want


def test_a_bare_yen_sign_takes_the_currency_the_document_resolves():
    assert read("¥5bn and ¥1,000") == [(5.0, "", "¥", 1e9), (1000.0, "", "¥", 1.0)]
    assert read("¥5bn and ¥1,000", "CNY") == [(5.0, "", "CNY", 1e9), (1000.0, "", "CNY", 1.0)]
    assert read("¥5 亿元 and JP¥3 and 5円", "CNY") == [(5.0, "", "CNY", 1e8), (3.0, "", "¥", 1.0), (5.0, "", "¥", 1.0)]


def test_scale_values_multiply_and_tails_add():
    assert scale_value("百万") == 1e6 and scale_value("万亿") == 1e12 and scale_value("十亿") == 1e9
    assert scale_value("천만") == 1e7 and scale_value("백만") == 1e6 and scale_value("萬") == 1e4
    assert tail_value("") == 0 and tail_value(" 5천만") == 5e7 and tail_value(" 2,345억 7천만") == 2345e8 + 7e7


@pytest.mark.parametrize("label,want", [
    ("Net sales (RMB'000)", 1e3), ("Revenue (RMB million)", 1e6), ("(KRW billions)", 1e9), ("Assets, HK$ million", 1e6),
    ("Revenue, 000s", 1e3), ("Revenue (k)", 1e3), ("(¥ bn)", 1e9), ("(₩ tn)", 1e12),
    ("单位：人民币百万元 营业收入", 1e6), ("营业收入（万元）", 1e4), ("(단위: 억원)", 1e8), ("(단위: 백만원)", 1e6),
    ("Operating profit", None), ("营业收入", None),
])
def test_scale_hint(label, want):
    assert scale_hint(label) == want


def test_language_is_read_from_the_script_of_the_opening_text():
    assert language_of("本集团上半年实现收入约人民币三千亿元，净利润保持稳定。") == "zh"
    assert language_of("매출액은 증가했으며 영업이익도 개선되었습니다. Revenue") == "ko"
    assert language_of("売上高は増加しました。営業利益も改善しました。") == "ja"
    assert language_of("Revenue rose 5% to RMB 344.8bn. 艾克米") == "en"          # an English body with a Chinese name
    assert language_of("") == "en"


def test_a_prc_issuer_is_read_from_the_opening_text_only():
    assert issuer_country("Acme EV Company Limited (A joint stock company incorporated in the People’s Republic of China)") == "CN"
    assert issuer_country("listed on the Shenzhen Stock Exchange") == "CN" and issuer_country("PRC") == "CN"
    assert issuer_country("本公司是中华人民共和国境内企业") == "CN"
    assert issuer_country("Toyota Motor Corporation. " + "x" * 6000 + " PRC") is None
    assert issuer_country("Acme Korea Company") is None


def test_yen_is_resolved_from_the_documents_own_currency_words_first():
    y = resolve_yen("营业收入 ¥ 344,815 元 人民币")
    assert (y.code, y.basis, y.currency) == ("CNY", "explicit", "CNY")
    assert y.meta() == {"code": "CNY", "basis": "explicit", "signs": 1, "cny_words": 2, "jpy_words": 0, "language": "zh",
                        "issuer_country": ""}
    y = resolve_yen("売上高 ¥ 500 円 JPY")
    assert (y.code, y.basis, y.currency) == ("JPY", "explicit", "¥")


def test_a_currency_with_three_times_the_words_of_the_other_settles_a_mixed_text():
    mostly_rmb = "Revenue ¥5bn. " + "RMB 1bn. " * 6 + "JPY 2bn."
    assert (resolve_yen(mostly_rmb).code, resolve_yen(mostly_rmb).basis) == ("CNY", "dominant")
    mostly_jpy = "Revenue ¥5bn. " + "JPY 1bn. " * 6 + "RMB 2bn."
    assert (resolve_yen(mostly_jpy).code, resolve_yen(mostly_jpy).basis) == ("JPY", "dominant")
    assert resolve_yen(mostly_rmb, issuer="JP").basis == "dominant"             # the words outweigh a stated issuer


def test_yen_falls_back_to_the_issuer_then_the_language_then_the_yen():
    both = "Revenue ¥ 5bn; RMB 3bn; JPY 2bn"
    assert resolve_yen(both, issuer="CN").code == "CNY" and resolve_yen(both, issuer="CN").basis == "issuer"
    assert resolve_yen(both, language="zh").basis == "language" and resolve_yen(both, language="zh").code == "CNY"
    assert (resolve_yen(both).code, resolve_yen(both).basis) == ("JPY", "default")
    assert (resolve_yen(both, language="ja").code, resolve_yen(both, language="ja").basis) == ("JPY", "language")
    assert resolve_yen("Revenue ¥5bn").basis == "default"
    # a PRC issuer named in the text decides when the currency words are mixed
    text = "Company (incorporated in the PRC). Revenue ¥ 5bn; RMB 3bn; JPY 2bn"
    assert (resolve_yen(text).code, resolve_yen(text).basis) == ("CNY", "issuer")
    # a Chinese text with mixed words, and no issuer named
    zh = "营业收入为¥5亿元，另有日元3亿円，人民币2亿元，这是本季度的整体情况，说明业务保持稳定增长"
    assert (resolve_yen(zh).code, resolve_yen(zh).basis) == ("CNY", "language")
