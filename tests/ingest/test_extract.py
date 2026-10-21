"""Extraction: sentences that name the model's values into import signals, by fixed rules, against Acme's world."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace as NS

import pytest

from axelrod_wm.ingest.extract import (
    LLM_CONFIDENCE,
    UNDIRECTED_SD,
    ChunkClaims,
    Found,
    Num,
    Reading,
    Rules,
    _unit_kind,
    category_of,
    claims_of_chunk,
    find_date,
    item_of,
    numbers,
    stance_of,
)
from axelrod_wm.intake.bundle import ImportItem

D = datetime(2026, 10, 5, tzinfo=UTC)


def sigs(rules: Rules, text: str) -> list[dict]:
    claims, _ = claims_of_chunk(rules, 0, text, None)
    out = [f.signal() for f in claims.found]
    for s in out:
        assert s["quote"] in text
        del s["quote"]
    return out


def one(rules: Rules, text: str) -> dict:
    got = sigs(rules, text)
    assert len(got) == 1, got
    return got[0]


# -- numbers ------------------------------------------------------------------------------------------------------------
def n(text: str) -> list[tuple]:
    return [(x.value, x.unit, x.currency, x.scale, x.negative, text[x.start:x.end].strip()) for x in numbers(text)]


@pytest.mark.parametrize("text,want", [
    ("25bp", [(25.0, "bp", "", 1.0, False, "25bp")]),
    ("+25 bps", [(25.0, "bp", "", 1.0, False, "+25 bps")]),
    ("10 basis points", [(10.0, "bp", "", 1.0, False, "10 basis points")]),
    ("1.25%", [(1.25, "%", "", 1.0, False, "1.25%")]),
    ("4 per cent and 5 percent and 6 pct", [(4.0, "%", "", 1.0, False, "4 per cent"),
                                            (5.0, "%", "", 1.0, False, "5 percent"),
                                            (6.0, "%", "", 1.0, False, "6 pct")]),
    ("3 percentage points, 2 pct pts, 1 ppt, 0.5pp", [(3.0, "pp", "", 1.0, False, "3 percentage points"),
                                                     (2.0, "pp", "", 1.0, False, "2 pct pts"),
                                                     (1.0, "pp", "", 1.0, False, "1 ppt"),
                                                     (0.5, "pp", "", 1.0, False, "0.5pp")]),
    ("$95bn", [(95.0, "", "$", 1e9, False, "$95bn")]),
    ("€1.2 billion", [(1.2, "", "€", 1e9, False, "€1.2 billion")]),
    ("¥3.5 trillion and £2tn", [(3.5, "", "¥", 1e12, False, "¥3.5 trillion"),
                                          (2.0, "", "£", 1e12, False, "£2tn")]),
    ("$5m and $5 million and $5mn", [(5.0, "", "$", 1e6, False, "$5m"), (5.0, "", "$", 1e6, False, "$5 million"),
                                     (5.0, "", "$", 1e6, False, "$5mn")]),
    ("5 m away", [(5.0, "", "", 1.0, False, "5 m")]),                       # a lone m is a scale only with a currency
    ("5k", [(5.0, "", "", 1e3, False, "5k")]),
    ("1,250.5 and 12,000", [(1250.5, "", "", 1.0, False, "1,250.5"), (12000.0, "", "", 1.0, False, "12,000")]),
    ("1.5x", [(1.5, "x", "", 1.0, False, "1.5x")]),
    ("-0.5% and −0.5% and –0.5%", [(0.5, "%", "", 1.0, True, "-0.5%"), (0.5, "%", "", 1.0, True, "−0.5%"),
                                              (0.5, "%", "", 1.0, True, "–0.5%")]),
    ("no numbers here", []),
])
def test_numbers(text, want):
    assert n(text) == want


def test_a_hyphenated_pair_reads_its_second_number_as_negative():
    # "7-2 vote": the hyphen is read as a minus sign; no rule uses a bare unitless number as a size, and a
    # negative level would have to be plausible for the value, so this does not become a claim
    assert [(x.value, x.negative) for x in numbers("a 7-2 vote")] == [(7.0, False), (2.0, True)]


def test_unit_kind():
    assert _unit_kind("pct") == _unit_kind("pct y/y") == _unit_kind("%") == _unit_kind("bps pct") == "rate"
    assert _unit_kind("$bn/yr") == _unit_kind("index") == _unit_kind("¥ per $") == "level"


# -- dates --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,filename,want", [
    ("Published 2026-10-05.", "", D),
    ("October 5, 2026 note", "", D),
    ("Oct. 5 2026", "", D),
    ("5 Oct 2026", "", D),
    ("5 October, 2026", "", D),
    ("Sept. 9, 2026", "", datetime(2026, 9, 9, tzinfo=UTC)),
    ("2026-02-30 is not a date; 2026-10-05 is", "", D),
    ("Oct 5, 2026, then 2026-01-01", "", D),                                 # the first date in the text
    ("31 Feb 2026", "note_2026-10-05.pdf", D),                               # invalid text date: the file name
    ("", "note_2026-10-05.pdf", D),
    ("", "note_20261005.pdf", D),
    ("", "2026_10_05 desk.txt", D),
    ("", "2026-13-01.pdf", None),
    ("", "v12026100512.pdf", None),                                           # digits run on: no date
    ("nothing dated", "notes.pdf", None),
    ("x" * 3000 + " 2026-01-01", "", None),                                   # only the opening text is read
])
def test_find_date(text, filename, want):
    assert find_date(text, filename) == want


# -- levels (observe) ---------------------------------------------------------------------------------------------------
def test_rate_level_in_percent(rules):
    assert one(rules, "The ECB held rates at 2.25% in 2026.") == {
        "type": "observe", "value_of": "ecb.policy_rate", "value": 2.25, "note": "rule: level"}


def test_a_level_and_a_move_in_one_clause_are_both_claimed(rules):
    got = sigs(rules, "The BoJ raised its policy rate by 25bp to 1.25%.")
    assert [(s["type"], s.get("value"), s.get("delta")) for s in got] == [("observe", 1.25, None), ("move", None, 0.25)]


def test_rate_level_in_basis_points(rules):
    assert one(rules, "The BoJ policy rate stands at 125bp.")["value"] == 1.25


def test_negative_rate_level(rules):
    for text in ("US real GDP growth was -0.5%.", "US real GDP growth was −0.5%."):
        assert one(rules, text) == {"type": "observe", "value_of": "us_economy.gdp_growth", "value": -0.5,
                                    "note": "rule: level"}


def test_implausible_levels_are_rejected(rules):
    assert sigs(rules, "The ECB deposit rate was 25%.") == []           # far outside the posterior's band
    assert sigs(rules, "Brent crude reached 2026.") == []               # a year is not an oil price
    assert sigs(rules, "Brent crude, see page at 3.") == []
    assert sigs(rules, "USD/JPY at 1,250.") == []


def test_rate_level_needs_a_percent_or_bp(rules):
    assert sigs(rules, "The ECB deposit rate was 2.25.") == []
    assert sigs(rules, "The ECB deposit rate was 2 pp.") == []


def test_price_level_with_matching_or_no_currency(rules):
    assert one(rules, "Brent crude hit $95.")["value"] == 95.0
    assert one(rules, "Brent crude hit 95.")["value"] == 95.0
    assert sigs(rules, "Brent crude hit €95.") == []


def test_fx_level_in_the_units_own_currency(rules):
    # USD/JPY is in "¥ per $": a yen figure is a level, a dollar figure is not
    assert one(rules, "USD/JPY fell to ¥152.")["type"] == "observe"
    assert one(rules, "USD/JPY fell to 152.")["value"] == 152.0
    assert one(rules, "USD/JPY fell to $152.")["mode"] == "standardized"


@pytest.mark.parametrize("text", ["Acme Motors operating profit reached ¥3.5 trillion.",
                                  "Acme Motors operating profit reached ¥3,500 billion."])
def test_scaled_levels_convert_to_the_values_unit(rules, text):
    assert one(rules, text) == {"type": "observe", "value_of": "acme_motors.operating_profit", "value": 3.5,
                                "note": "rule: level"}


def test_scaled_levels_convert_to_bn(rules):
    assert one(rules, "Acme Bank net interest income was $95 billion.")["value"] == 95.0
    assert one(rules, "Acme Bank net interest income was $95,000 million.")["value"] == 95.0


def test_level_rejects_non_level_units(rules):
    for text in ("Brent crude at 3%.", "Brent crude at 30bp.", "Brent crude at 1.5x."):
        assert sigs(rules, text) == []


# -- moves -------------------------------------------------------------------------------------------------------------
def test_move_by_basis_points(rules):
    assert one(rules, "The BoJ raised its policy rate by 25bp.") == {
        "type": "move", "value_of": "boj.policy_rate", "delta": 0.25, "mode": "absolute",
        "note": "rule: direction + size"}


def test_relative_move_for_a_lognormal_value(rules):
    assert one(rules, "Acme Bank's net interest income rose 4%.") == {
        "type": "move", "value_of": "acme_bank.net_interest_income", "delta": 0.04, "mode": "relative",
        "note": "rule: direction + size"}
    assert one(rules, "Brent crude fell by about 3%.")["delta"] == -0.03


def test_rate_moves_in_points(rules):
    assert one(rules, "US core CPI rose 0.3 percentage points.")["delta"] == 0.3
    s = one(rules, "The ECB deposit rate rose by 0.25%.")
    assert (s["delta"], s["mode"]) == (0.25, "absolute")
    assert one(rules, "Bund yields rose 10bp.") == {"type": "move", "value_of": "bunds.yield_10y", "delta": 0.1,
                                                     "mode": "absolute", "note": "rule: direction + size"}


def test_size_before_the_value(rules):
    assert one(rules, "A 25bp cut in the ECB deposit rate.") == {
        "type": "move", "value_of": "ecb.policy_rate", "delta": -0.25, "mode": "absolute",
        "note": "rule: size + direction before"}


@pytest.mark.parametrize("text,direction", [
    ("Delta net interest income fell 95%.", -1),          # a relative move over 90%
    ("The Fed funds rate rose 6pp.", 1),                  # an absolute move over 5 points
    ("Brent crude rose 3pp.", 1),                         # points are for rates
    ("Brent crude rose 30bp.", 1),                        # basis points are for rates
    ("Brent crude rose by 5.", 1),                        # no unit: no size
    ("Brent crude rose 0%.", 1),                          # no change is not a size
    ("A 30bp rise in Brent crude.", 1),                   # a size before that does not fit
    ("Brent crude rose then fell.", 1),
    ("Brent crude fell then rose.", -1),
    ("Brent crude decreased.", -1),
])
def test_bare_or_unfit_sizes_become_a_standardized_move(rules, text, direction):
    s = one(rules, text)
    assert (s["type"], s["delta"], s["mode"], s["note"]) == ("move", direction * UNDIRECTED_SD, "standardized",
                                                             "rule: direction without size")


@pytest.mark.parametrize("text", ["Brent crude was mentioned.", "Brent crude in the crisis.",
                                  "Brent crude data release today.", "Brent crude, again.", "Brent crude risk."])
def test_no_direction_word_no_move(rules, text):
    # direction words match at a word's start only ("crisis", "release", "again", and "risk" carry none)
    assert sigs(rules, text) == []


def test_inverted_surface_flips_the_direction(rules):
    assert one(rules, "The yen strengthened 2%.") == {"type": "move", "value_of": "dollar_yen.usd_jpy",
                                                      "delta": -0.02, "mode": "relative",
                                                      "note": "rule: direction + size"}
    assert one(rules, "The yen weakened.")["delta"] == UNDIRECTED_SD


def test_inverted_surface_never_states_a_level(rules):
    assert sigs(rules, "The yen was at 150.") == []
    assert one(rules, "The yen strengthened to 150.")["mode"] == "standardized"


def test_without_inverted_patterns_the_yen_is_usd_jpy(graph, gz):
    assert one(Rules(graph, gz), "The yen strengthened 2%.")["delta"] == 0.02


def test_one_claim_per_value_per_sentence(rules):
    # the first mention claims for the value (its clause runs over the second): a level and a move, no more
    got = sigs(rules, "Brent crude rose to 95 and Brent crude rose 3%.")
    assert [(s["type"], s["value_of"]) for s in got] == [("observe", "oil.brent"), ("move", "oil.brent")]
    # a later mention gets its chance when the first made no claim
    got = sigs(rules, "The Fed funds rate rose 6pp.")
    assert [(s["value_of"], s["mode"]) for s in got] == [("federal_reserve.policy_rate", "standardized")]
    assert sigs(rules, "Brent crude was quoted; later Brent crude rose 3%.")[0]["delta"] == 0.03


def test_each_value_reads_its_own_clause(rules):
    got = sigs(rules, "Acme Bank net interest income was $95 billion and Delta net interest income rose 3%.")
    assert [(s["value_of"], s.get("value"), s.get("delta")) for s in got] == [
        ("acme_bank.net_interest_income", 95.0, None), ("delta_bank.net_interest_income", None, 0.03)]


# -- causal claims ------------------------------------------------------------------------------------------------------
def test_causal_verb_on_a_known_link_supports_it(rules):
    assert one(rules, "Higher Brent crude lifts Japan core CPI.") == {
        "type": "support", "source": "oil.brent", "target": "japan_economy.core_cpi", "strength": 0.5,
        "note": "rule: causal 'lifts' on a known link"}


def test_causal_verb_against_the_links_sign_contradicts_it(rules):
    s = one(rules, "The Fed rate weighs on Acme Bank net interest income.")
    assert (s["type"], s["source"], s["target"]) == ("contradict", "federal_reserve.policy_rate",
                                                      "acme_bank.net_interest_income")


def test_a_down_verb_supports_a_negative_link(rules):
    s = one(rules, "The JGB 10Y yield weighs on Acme Telecom operating income.")
    assert (s["type"], s["source"], s["target"]) == ("support", "jgbs.yield_10y", "acme_telecom.operating_profit")


def test_lower_source_flips_the_sign(rules):
    # Bunds -> European equities is negative: "lower yields lift" agrees, "lower yields weigh on" does not
    assert one(rules, "Lower Bund yields lift European stocks.")["type"] == "support"
    assert one(rules, "Lower Bund yields weigh on European stocks.")["type"] == "contradict"


def test_the_first_causal_verb_decides_and_names_the_claim(rules):
    s = one(rules, "The Fed weighs on and lifts Acme Bank net interest income.")
    assert (s["type"], s["note"]) == ("contradict", "rule: causal 'weighs on' on a known link")
    s = one(rules, "The Fed rate lifts but weighs on Acme Bank net interest income.")
    assert (s["type"], s["note"]) == ("support", "rule: causal 'lifts' on a known link")


def test_entity_mentions_resolve_through_existing_links(rules):
    s = one(rules, "Oil lifts Japan core CPI.")
    assert (s["type"], s["source"], s["target"]) == ("support", "oil.brent", "japan_economy.core_cpi")
    s = one(rules, "Bunds lift Acme Re.")
    assert (s["type"], s["source"], s["target"]) == ("support", "bunds.yield_10y", "acme_re.international_profit")


def test_ambiguous_or_unlinked_entity_pairs_are_skipped(rules):
    assert sigs(rules, "Oil lifts the United States economy.") == []         # two links: CPI and growth
    assert sigs(rules, "Oil lifts Acme Motors.") == []                            # no link
    assert sigs(rules, "Oil lifts Acme Machinery operating profit.") == []          # an entity: no new link
    assert sigs(rules, "JGBs lift Acme Re.") == []                      # many links: reinvestment, marks, life


def test_two_values_with_no_link_propose_one(rules):
    assert one(rules, "Brent crude lifts Acme Machinery operating profit.") == {
        "type": "link", "source": "oil.brent", "target": "acme_machinery.operating_profit", "label": "lifts",
        "effect": 0.3, "note": "rule: causal 'lifts', no link yet"}
    s = one(rules, "Brent crude weighs on and lifts Acme Machinery operating profit.")
    assert (s["label"], s["effect"]) == ("weighs on", -0.3)


def test_a_long_gap_is_not_a_causal_claim(rules):
    assert sigs(rules, "Brent crude, which as everyone knows has been a topic of very long debate among the "
                       "analysts here, lifts Acme Machinery operating profit.") == []


def test_no_self_links_and_no_duplicate_claims(rules):
    # "ARHD profit" is the same value as "Acme Re Japan P&C profit": no link from it to itself, one support
    got = sigs(rules, "The JGB 30Y yield lifts Acme Re Japan P&C profit and lifts ARHD profit.")
    assert [(s["type"], s["source"], s["target"]) for s in got] == [
        ("support", "jgbs.yield_30y", "acme_re.japan_pc_profit")]


def test_a_causal_clause_makes_no_bare_moves(rules):
    got = sigs(rules, "Higher Brent crude lifts Japan core CPI.")
    assert [s["type"] for s in got] == ["support"]


# -- chunks into claims ---------------------------------------------------------------------------------------------------
def test_claims_of_chunk_carries_context_and_mention_offsets(rules):
    text = "Acme Bank reported results. Net interest income rose 4%."
    claims, ctx = claims_of_chunk(rules, 3, text, None)
    assert ctx.recent == [("acme_bank", 0)] and claims.ord == 3 and claims.entities == ["acme_bank"]
    assert [(text[m.start:m.end], m.subentity_id) for m in claims.mentions] == [
        ("Acme Bank", None), ("Net interest income", "acme_bank.net_interest_income")]
    assert claims.sentence_spans == [(0, 27), (28, 56)]
    assert [f.signal()["delta"] for f in claims.found] == [0.04]
    # context flows into the next chunk, and stays while chunks name nothing, for a few sentences
    claims, ctx = claims_of_chunk(rules, 4, "Nothing here.", Reading(recent=[("northwind_bank", 0)]))
    assert ctx.recent == [("northwind_bank", 1)] and claims.found == [] and claims.entities == []
    claims, _ = claims_of_chunk(rules, 5, "Net interest income rose 2%.", ctx)
    assert claims.found[0].value_of == "northwind_bank.net_interest_income"
    claims, _ = claims_of_chunk(rules, 6, "One. Two. Three. Net interest income rose 2%.", Reading(recent=[("northwind_bank", 0)]))
    assert claims.found == []                                   # three sentences on, the context has expired
    # the most recent owner among the entities named lately: a central bank named last does not hide the bank
    text = "Acme Bank reported. NII rose on higher short-term rates set by the Fed. Net interest income rose 2%."
    claims, _ = claims_of_chunk(rules, 7, text, None)
    assert [f.value_of for f in claims.found][-1] == "acme_bank.net_interest_income"


def test_found_signal_shapes():
    assert Found("observe", value_of="a.b", value=1.23456789, quote="q", rule="r").signal() == {
        "type": "observe", "value_of": "a.b", "value": 1.234568, "quote": "q", "note": "rule: r"}
    assert Found("contradict", source="a.b", target="c.d", quote="q", rule="r").signal() == {
        "type": "contradict", "source": "a.b", "target": "c.d", "strength": 0.5, "quote": "q", "note": "rule: r"}


# -- items --------------------------------------------------------------------------------------------------------------
def test_category_of(graph):
    assert category_of(graph, [Found("move", value_of="boj.policy_rate")]) == "rates"
    assert category_of(graph, [Found("support", source="oil.brent", target="japan_economy.core_cpi")]) == "macro"
    assert category_of(graph, [Found("move", value_of="harbor_bank.npl_ratio")]) == "other"
    assert category_of(graph, [Found("move", value_of="no.such"), Found("move", value_of="oil.brent")]) == "commodities"
    assert category_of(graph, []) == "other"
    assert category_of(graph, [Found("move", value_of="no.such")]) == "other"


@pytest.mark.parametrize("dirs,stance", [([1, 1, -1], "up"), ([-1, 0], "down"), ([1, -1], "mixed"), ([0, 0], ""),
                                         ([], "")])
def test_stance_of(dirs, stance):
    assert stance_of([Found("move", direction=d) for d in dirs]) == stance


def _item(graph, claims, extra=None):
    return item_of(graph, claims, doc_prefix="Dabc", published_at=D, source="", source_type="broker_research",
                   kind="analyst", title="Desk note", extra=extra)


def test_item_of_a_chunk_with_rule_signals(graph, rules):
    text = "Acme Bank's net interest income rose 4%. Acme Re said the BoJ raised its policy rate by 25bp."
    claims, _ = claims_of_chunk(rules, 7, text, None)
    item = _item(graph, claims)
    assert item["id"] == "Dabc-0007" and item["headline"] == "Acme Bank's net interest income rose 4%."
    assert item["summary"] == text and item["source"] == "Desk note" and item["kind"] == "analyst"
    assert item["entities"] == ["acme_bank", "acme_re", "boj"]
    assert item["tickers"] == ["8766 AR", "ACME", "ARHD"]           # companies' ticker-like aliases; not the BoJ's
    assert item["category"] == "earnings" and item["stance"] == "up"
    assert item["relevance"] == 0.6 and item["confidence"] == 0.8 and item["tags"] == ["extracted"]
    assert item["published_at"] == D.isoformat()
    parsed = ImportItem.model_validate(item)
    for s in parsed.signals:
        assert s.quote in f"{parsed.headline}\n{parsed.summary}"


def test_item_of_nothing_is_none(graph, rules):
    claims, _ = claims_of_chunk(rules, 0, "Acme Bank reported.", None)
    assert _item(graph, claims) is None and _item(graph, claims, extra=[]) is None


def test_item_headline_is_truncated(graph, rules):
    text = "Brent crude rose 3% " + "and kept going " * 20 + "today."
    claims, _ = claims_of_chunk(rules, 0, text, None)
    head = _item(graph, claims)["headline"]
    assert len(head) == 198 and head.endswith("…") and text.startswith(head[:-1])


def test_item_of_extra_signals_only(graph, rules):
    claims, _ = claims_of_chunk(rules, 0, "Acme Bank and Delta reported.", None)
    extra = [{"type": "support", "source": "us_capital_markets.deal_activity", "target": "acme_bank.ib_fees",
              "strength": 0.5, "quote": "Acme Bank and Delta reported.", "note": "llm:m"}]
    item = _item(graph, claims, extra)
    assert item["signals"] == extra and item["confidence"] == LLM_CONFIDENCE and item["tags"] == ["extracted", "llm"]
    assert item["category"] == "earnings" and item["stance"] == "" and item["relevance"] == 0.5
    assert item["tickers"] == ["ACME"]                                     # Delta's "C" is one letter


@pytest.mark.parametrize("extra,category", [
    ([{"type": "move", "value_of": "boj.policy_rate", "delta": 0.1}], "rates"),
    ([{"type": "move", "value_of": "no.such", "delta": 0.1}], "other"),
    ([{"type": "link", "source": "a", "target": "", "label": "x", "effect": 0.1}], "other"),
])
def test_item_category_from_the_first_extra_signal(graph, extra, category):
    claims = ChunkClaims(0, "")
    item = _item(graph, claims, extra)
    assert item["category"] == category and item["headline"] == "" and item["summary"] == ""


def test_item_extra_signals_follow_rule_signals(graph, rules):
    claims, _ = claims_of_chunk(rules, 0, "Brent crude rose 3%.", None)
    extra = [{"type": "move", "value_of": "boj.policy_rate", "delta": 0.1}]
    item = _item(graph, claims, extra)
    assert [s["type"] for s in item["signals"]] == ["move", "move"] and item["signals"][1] == extra[0]
    assert item["category"] == "commodities" and item["relevance"] == 0.6


def test_tickers_only_from_companies():
    g = NS(entities={"bank": NS(kind="agency", aliases=["BOJ"]), "co": NS(kind="company",
                                                                          aliases=["ACME", "1234 JP", "Acme Inc"])},
           subentities={})
    claims = ChunkClaims(0, "x", found=[Found("move", value_of="co.x", delta=0.1)], entities=["bank", "co"])
    assert _item(g, claims)["tickers"] == ["1234 JP", "ACME"]


def test_num_is_a_value_record():
    assert Num(1.0, "%", "", 1.0, 0, 2, False) == Num(1.0, "%", "", 1.0, 0, 2, False)
