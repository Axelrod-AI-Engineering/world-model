"""Chinese, Japanese, and Korean text: width, weight, sentence ends, and cuts that split no word or character."""

from __future__ import annotations

import pytest

from axelrod_ingest import cjk
from axelrod_ingest.cjk import cut_at, joined, limit, sentence_cuts, weight, width


def test_full_width_forms_become_ascii_but_sentence_ends_stay():
    assert width("２０２６年，营收１，２３４．５亿元（同比＋７．１％）") == "2026年,营收1,234.5亿元(同比+7.1%)"
    assert width("净利润：人民币１００万元；ＡＥＶ") == "净利润:人民币100万元;AEV"
    assert width("好！真的？") == "好！真的？"                                   # ！ and ？ end sentences with no space
    assert width("￥５００　￡３　￦７００　￠２") == "¥500 £3 ₩700 ¢2"


def test_nfkc_is_not_applied_beyond_the_full_width_block():
    assert width("面积 100m² … ①") == "面积 100m² … ①"                       # NFKC would make these 100m2 ... 1


def test_a_name_drawn_one_character_at_a_time_is_rejoined():
    assert width("艾 克 米 股 份 有 限 公 司\nAEV COMPANY") == "艾克米股份有限公司\nAEV COMPANY"
    assert width("营业收入 净利润") == "营业收入 净利润"                          # two words stay two
    assert width("现 金 流 量 表 营业收入") == "现金流量表 营业收入"
    assert width("公司 艾 克 米 公司") == "公司 艾克米 公司"


def test_weight_counts_cjk_double():
    assert weight("abc") == 3 and weight("净利润") == 6 and weight("AEV 艾克米") == 3 + 1 + 6 and weight("영업이익") == 8
    assert weight("") == 0 and weight("こんにちは") == 10


def test_limit_is_the_largest_end_that_fits():
    assert limit("abcdef", 0, 6, 4) == 4 and limit("abcdef", 0, 6, 10) == 6
    assert limit("净利润增长", 0, 5, 5) == 2                                  # two characters weigh four
    assert limit("净利润", 0, 3, 1) == 1                                      # never empty
    assert limit("ab净利润", 1, 6, 5) == 4                                 # "b净利" weighs five


@pytest.mark.parametrize("text,cut,want", [
    ("营业收入", 2, False),                    # between two ideographs: Chinese has no word edges to respect
    ("AEV", 1, True), ("2026", 2, True),       # inside a Latin word or a number
    ("1,234", 2, True), ("1,234", 3, True),    # around the comma of a number
    ("a, b", 2, False), ("don't", 4, True),    # a comma after a letter is a clause mark; the apostrophe is in the word
    ("영업이익은", 2, True),                    # inside a Hangul word
    ("영업 이익", 3, False),
    ("é", 1, True), ("a‍b", 1, True), ("a‍b", 2, True), ("a️", 1, True),
    ("한", 1, True),           # a jamo vowel completes its syllable
    ("1. 2", 2, False),
])
def test_joined(text, cut, want):
    assert joined(text, cut) is want


def test_cut_at_prefers_line_break_then_space_then_clause_mark_then_a_safe_point():
    t = "aaa bbb\nccc ddd eee"
    assert cut_at(t, 0, 14) == 7                                      # the last line break
    assert cut_at("aaa bbb ccc ddd", 0, 10) == 7                      # the last space
    zh = "净利润同比增长，营收创出新高但费用上升明显"
    assert cut_at(zh, 0, 12) == zh.index("，") + 1                    # after the clause mark
    assert cut_at("营业收入同比增长了很多个百分点以上", 0, 8) == 8     # no mark: the limit itself
    assert cut_at("请看AEVCOMPANYLIMITED公司", 0, 8) == 2             # the limit falls inside a Latin word: back to "请看"
    assert cut_at("x" * 40, 0, 20) == 20                              # one unbroken word: cut at the limit
    assert cut_at("请" + "X" * 40, 0, 20) == 1                         # back to the edge of the unbroken word


def test_sentence_cuts_after_cjk_enders_and_korean_endings():
    t = "第一句。第二句！第三句？「引用。」后文"
    assert [t[:c] for c in sorted(sentence_cuts(t))] == ["第一句。", "第一句。第二句！", "第一句。第二句！第三句？",
                                                         "第一句。第二句！第三句？「引用。」"]
    k = "매출이 증가했다\n영업이익도 늘었다.\n다음 줄은 계속"
    assert [k[:c] for c in sorted(sentence_cuts(k))] == ["매출이 증가했다", "매출이 증가했다\n영업이익도 늘었다."]
    assert sentence_cuts("Rates rose! Yields fell?") == set()          # half-width marks need an ideograph after them
    assert sentence_cuts("好!下") == {2}


def test_the_weight_constant():
    assert cjk.CJK_WEIGHT == 2
