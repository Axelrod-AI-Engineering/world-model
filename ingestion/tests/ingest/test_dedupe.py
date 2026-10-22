"""Duplicates across language and basis: the same figures in an English filing, a Chinese filing, and a summary are one
disclosure with one primary, every copy kept. Every figure and sentence is invented."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import pytest

from axelrod_ingest.dedupe import (
    DedupeConfig,
    Fingerprint,
    choose_primary,
    containment,
    figure_key,
    figures_of,
    fingerprint,
    groups_of,
    link_duplicates,
)
from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.pipeline import Ingestor
from tests.ingest.multilingual import world

T = "acme"
NOW = datetime(2026, 10, 22, tzinfo=UTC)
FIGURES = [f"{100000 + k * 37:,}" for k in range(80)]


@pytest.mark.parametrize("token,key", [("(777,102.50", "7771025"), ("777102500", "7771025"), ("777,102", "777102"),
                                       ("-1,234,567.00", "1234567"), ("0.0042", "42"), ("1,000", "1"), ("+12,345.6", "123456")])
def test_figure_key_is_the_significant_digits(token, key):
    assert figure_key(token) == key


def test_only_figures_of_five_significant_digits_count():
    got = figures_of("Revenue 777,102 and 777102.00; in 2026 up 21.04% to 3,500; page 12; ratio 0.1234567; again 777,102")
    assert got == Counter({"777102": 3, "1234567": 1}) and figures_of("") == Counter()


def test_a_figure_in_another_scale_or_language_is_the_same_figure():
    en = figures_of("Revenue was RMB 777,102 million.")
    zh = figures_of("营业收入为人民币777,102百万元。")
    units = figures_of("revenue 777,102,000,000.00")
    assert en == zh == units == Counter({"777102": 1})


def fp(figures: list[str], *, period: str = "2025-12-31", lang: str = "en", ifrs: bool = True, published: str = "",
       chars: int = 1000) -> Fingerprint:
    return Fingerprint(period, Counter(figures), "d", lang == "en", ifrs, chars, published)


def test_a_fingerprint_is_the_period_and_the_sorted_multiset():
    a = fingerprint("Revenue 123,456 and 654,321 and 123,456", period_end="2025-12-31", language="en", published="p")
    b = fingerprint("654,321 and 123,456, 123,456", period_end="2025-12-31", language="zh")
    assert a.digest == b.digest and a.figures == Counter({"123456": 2, "654321": 1}) and a.english and not b.english
    assert fingerprint("123,456 654,321 123,456", period_end="2026-06-30").digest != a.digest
    assert fingerprint("123,456 654,321", period_end="2025-12-31").digest != a.digest        # one fewer repeat
    assert not a.ifrs and fingerprint("Prepared under IFRS. 123,456").ifrs and fingerprint("国际财务报告准则").ifrs
    assert a.distinct == frozenset({"123456", "654321"}) and a.chars == len("Revenue 123,456 and 654,321 and 123,456")


def test_containment_is_the_share_of_the_smaller_set_found_in_the_larger():
    full, summary = fp(FIGURES), fp(FIGURES[:45])
    assert containment(summary, full) == (1.0, 45) == containment(full, summary)
    assert containment(fp([]), full) == (0.0, 0)


def test_translations_and_summaries_form_one_group_with_the_english_ifrs_copy_primary():
    prints = {"en": fp(FIGURES, lang="en", ifrs=True), "zh": fp(FIGURES[:75], lang="zh", ifrs=False),
              "sum": fp(FIGURES[:45], lang="zh", ifrs=False), "other": fp([f"{900000 + k}" for k in range(80)])}
    (g,) = groups_of(prints)
    assert g.members == ("en", "sum", "zh") and g.primary == "en" and g.rule == "english_ifrs>completeness"
    assert g.containment == {"sum": 1.0, "zh": 1.0} and g.id.startswith("so-") and len(g.id) == 19
    assert groups_of({"a": prints["en"]}) == []


def test_a_different_period_a_low_overlap_or_few_shared_figures_are_not_one_disclosure():
    base = fp(FIGURES)
    assert groups_of({"a": base, "b": fp(FIGURES, period="2026-06-30")}) == []
    assert groups_of({"a": base, "b": fp(FIGURES[:50] + [f"{800000 + k}" for k in range(50)])}) == []      # 50 of 100: 0.5
    assert groups_of({"a": fp(FIGURES[:30]), "b": fp(FIGURES[:30])}) == []                                  # only 30 shared
    assert len(groups_of({"a": fp(FIGURES[:30]), "b": fp(FIGURES[:30])}, DedupeConfig(min_shared=20))) == 1
    assert len(groups_of({"a": base, "b": fp(FIGURES[:50] + [f"{800000 + k}" for k in range(10)])})) == 1   # 50 of 60


def test_a_document_with_no_period_is_matched_only_when_asked():
    a, b = fp(FIGURES, period=""), fp(FIGURES, period="")
    assert groups_of({"a": a, "b": b}) == []
    assert len(groups_of({"a": a, "b": b}, DedupeConfig(require_period=False))) == 1


def test_a_chain_of_copies_is_one_group():
    ring = {"a": fp(FIGURES[:50]), "b": fp(FIGURES[:70]), "c": fp(FIGURES[20:80])}
    assert containment(ring["a"], ring["c"])[0] < 0.8                                   # a and c share too little ...
    (g,) = groups_of(ring)
    assert g.members == ("a", "b", "c")                                                 # ... but b joins them


def test_the_primary_follows_the_rules_in_order_then_the_id():
    prints = {"b": fp(FIGURES[:60], lang="zh", ifrs=False, chars=500, published="2026-03-01"),
              "a": fp(FIGURES[:70], lang="zh", ifrs=True, chars=900, published="2026-04-01"),
              "c": fp(FIGURES[:50], lang="en", ifrs=False, chars=100, published="2026-02-01"),
              "d": fp(FIGURES[:40], lang="en", ifrs=True, chars=300, published="")}
    pick = lambda *rules: choose_primary(prints, rules)                                 # noqa: E731
    assert pick("english_ifrs") == "d" and pick("english", "completeness") == "c" and pick("ifrs", "completeness") == "a"
    assert pick("completeness") == "a" and pick("length") == "a" and pick("latest") == "a"
    assert pick("earliest") == "c"                                                      # a missing date is the last of all
    assert pick("latest", "completeness") == "a" and pick("english_ifrs", "latest") == "d"
    tie = {"y": fp(FIGURES[:40]), "x": fp(FIGURES[:40])}
    assert choose_primary(tie, ("completeness",)) == "x"                                # the smaller id, whatever the order
    assert choose_primary(dict(reversed(tie.items())), ("english_ifrs", "completeness")) == "x"
    assert choose_primary({"u": fp([], published=""), "v": fp([], published="2026-01-01")}, ("earliest",)) == "v"
    assert choose_primary({"u": fp([], published=""), "v": fp([], published="2026-01-01")}, ("latest",)) == "v"


def test_the_rule_is_configurable():
    prints = {"en": fp(FIGURES, lang="en"), "zh": fp(FIGURES, lang="zh", ifrs=False, chars=5000)}
    (g,) = groups_of(prints, DedupeConfig(primary=("length",)))
    assert g.primary == "zh" and g.rule == "length"


# -- the lake -----------------------------------------------------------------------------------------------------------------------
def report(period_line: str, figures: list[str], extra: str = "") -> bytes:
    return (period_line + "\n\n" + "\n".join(f"Item {k}: {f}" for k, f in enumerate(figures)) + "\n" + extra).encode()


def ingest_set(lake):
    ing = Ingestor(lake, HashingEmbedder(), clock=lambda: NOW)
    g = world()
    docs = {
        "en": ing.ingest_file(T, report("Consolidated results for the year ended 31 December 2025 under IFRS.", FIGURES), "en.txt", g),
        "zh": ing.ingest_file(T, report("截至2025年12月31日止年度的合并业绩。", FIGURES[:70]), "zh.txt", g),
        "sum": ing.ingest_file(T, report("2025年年度报告摘要", FIGURES[:45]), "sum.txt", g),
        "next": ing.ingest_file(T, report("Results for the year ended 31 December 2026.", FIGURES), "next.txt", g),
        "other": ing.ingest_file(T, report("For the year ended 31 December 2025, other group.", [f"{900000 + k}" for k in range(60)]),
                                 "other.txt", g),
        "gone": ing.ingest_file(T, b"", "gone.txt", g),
    }
    return {k: v.document.id for k, v in docs.items()}


def test_link_duplicates_records_one_disclosure_in_every_copys_metadata(lake):
    ids = ingest_set(lake)
    (g,) = link_duplicates(lake, T)
    assert g.members == tuple(sorted([ids["en"], ids["zh"], ids["sum"]])) and g.primary == ids["en"]
    for k in ("en", "zh", "sum"):
        so = lake.get_document(T, ids[k]).meta["shared_origin"]
        assert so["group"] == g.id and so["primary"] == ids["en"] and so["members"] == list(g.members)
        assert so["role"] == ("primary" if k == "en" else "duplicate") and so["rule"] == "english_ifrs>completeness"
        assert so["figures"] > 0
    assert lake.get_document(T, ids["zh"]).meta["shared_origin"]["containment"] == 1.0
    assert lake.get_document(T, ids["en"]).meta["shared_origin"]["containment"] == 1.0
    for k in ("next", "other", "gone"):
        assert "shared_origin" not in lake.get_document(T, ids[k]).meta
    assert all(lake.get_text(T, ids[k]) for k in ("en", "zh", "sum"))                  # every copy is kept, with its bundle
    assert all(lake.list_bundles(T, doc_id=ids[k]) for k in ("en", "zh", "sum"))


def test_linking_twice_changes_nothing_and_relinking_follows_the_lake(lake, monkeypatch):
    ids = ingest_set(lake)
    first = link_duplicates(lake, T)
    updates = []
    real = lake.update_document
    monkeypatch.setattr(lake, "update_document", lambda *a, **k: updates.append(a) or real(*a, **k))
    assert link_duplicates(lake, T) == first and updates == []
    lake.delete_document(T, ids["zh"])
    (g,) = link_duplicates(lake, T)
    assert g.members == tuple(sorted([ids["en"], ids["sum"]])) and len(updates) == 2
    lake.delete_document(T, ids["sum"])
    assert link_duplicates(lake, T) == [] and "shared_origin" not in lake.get_document(T, ids["en"]).meta


def test_linking_pages_through_a_large_lake(lake, monkeypatch):
    import axelrod_ingest.dedupe as dedupe
    monkeypatch.setattr(dedupe, "PAGE", 2)
    ids = ingest_set(lake)
    assert len(link_duplicates(lake, T)) == 1 and len(ids) == 6


def test_linking_is_per_tenant(lake):
    ingest_set(lake)
    assert link_duplicates(lake, "someone-else") == []
