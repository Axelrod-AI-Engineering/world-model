"""Recognition: the world model's names found in text, by fixed rules, the same way every time."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from axelrod_ingest.gazetteer import Gazetteer, _case_sensitive, norm, tokens


def found(gz: Gazetteer, text: str, context: str | None = None) -> list[tuple]:
    return [(m.kind, m.entity_id, m.subentity_id, m.surface) for m in gz.find(text, context)]


def fake_graph(entities: dict, values: dict):
    """A graph with only what the gazetteer reads: entities (name, short, aliases, then optionally features and kind) and
    values (name, aliases, then optionally the attribute kind)."""
    ents = {eid: NS(name=e[0], short=e[1], aliases=list(e[2]), features=e[3] if len(e) > 3 else {},
                    kind=e[4] if len(e) > 4 else "") for eid, e in entities.items()}
    subs = {sid: NS(name=v[0], aliases=list(v[1]), entity_id=sid.split(".")[0], attribute_kind=v[2] if len(v) > 2 else None)
            for sid, v in values.items()}
    return NS(entities=ents, subentities=subs)


def regional():
    """Two regions, HM and FR, each with a central bank, a bond market, an economy, and a company: the cases that need
    a text to say which region it is about (the acme world has one region)."""
    ents, vals = {}, {}
    for r, word in (("hm", "Home"), ("fr", "Far")):
        reg = {"region": r.upper()}
        ents[f"{r}_cb"] = (f"{word} central bank", None, [f"{r[0].upper()}CB"], {**reg, "function": "monetary_policy"}, "agency")
        vals[f"{r}_cb.policy_rate"] = (f"{word} policy rate", ["policy rates"], "policy_rate")
        ents[f"{r}_bonds"] = (f"{word} bonds", None, [], reg, "market")
        vals[f"{r}_bonds.yield_2y"] = (f"{word} bonds 2Y yield", ["2Y yields"], "bond_yield")
        vals[f"{r}_bonds.yield_10y"] = (f"{word} bonds 10Y yield", ["10-year yields"], "bond_yield")
        ents[f"{r}_economy"] = (f"{word} economy", None, [word], reg, "macro_factor")
        vals[f"{r}_economy.gdp_growth"] = (f"{word} real GDP growth", ["Real GDP growth"], "growth_rate")
        ents[f"{r}_co"] = (f"{word}co", None, [f"{r[0].upper()}OCO"], reg, "company")
        vals[f"{r}_co.net_interest_income"] = (f"{word}co NII", ["NII"], "revenue_flow")
    vals["hm_economy.core_inflation"] = ("Home core inflation", ["core inflation", "Home CPI"], "inflation_rate")
    vals["fr_economy.core_inflation"] = ("Far core inflation", ["Far CPI"], "inflation_rate")
    return fake_graph(ents, vals)


@pytest.fixture(scope="module")
def rg():
    return Gazetteer(regional())



# -- tokens and forms --------------------------------------------------------------------------------------------------
def test_tokens_keep_joined_words_and_drop_possessive_s():
    assert [t for t, _a, _b in tokens("Acmebank's DXY S&P 1.25% Acme Re’s s 's")] == [
        "Acmebank", "DXY", "S&P", "1.25", "%", "Acme", "Re", "s"]
    assert [t for t, _a, _b in tokens("s rose")] == ["s", "rose"]          # a leading s is a word


@pytest.mark.parametrize("word,form", [("Yields", "yield"), ("rates", "rate"), ("bps", "bps"), ("gas", "gas"),
                                       ("Glass", "glass"), ("status", "status"), ("basis", "basis"),
                                       ("Spreads", "spread"), ("10Ys", "10ys")])
def test_norm_lowercases_and_drops_plural_s(word, form):
    assert norm(word) == form


@pytest.mark.parametrize("surface,sensitive", [("DXY", True), ("VIX", True), ("ACBK", True), ("DLTB", True),
                                               ("RDGE", True), ("Delta", False), ("crude", False),
                                               ("Dollar index", False), ("FOMCX1", False)])
def test_case_sensitive_surfaces_are_short_and_mostly_capitals(surface, sensitive):
    assert _case_sensitive(surface) is sensitive


# -- matching against Acme's world -------------------------------------------------------------------------------------
def test_names_and_aliases_match_in_any_case_when_not_capitals(gz):
    assert found(gz, "Government bonds, government bonds, GOVERNMENT BONDS.") == [
        ("entity", "gov_bonds", None, "Government bonds"), ("entity", "gov_bonds", None, "government bonds"),
        ("entity", "gov_bonds", None, "GOVERNMENT BONDS")]


def test_capital_surfaces_match_only_in_their_case(gz):
    assert found(gz, "DXY and Dxy and dxy.") == [("value", "dollar", "dollar.index", "DXY")]
    assert found(gz, "RDGE shares fell. rdge said so.") == [("entity", "ridge_energy", None, "RDGE")]


def test_one_letter_surfaces_never_match():
    gz = Gazetteer(fake_graph({"delta": ("Delta Bank", "Delta", ["D", "DLTB"])}, {}))
    assert found(gz, "D rose. Delta rose.") == [("entity", "delta", None, "Delta")]


def test_possessives_and_plurals(gz):
    assert found(gz, "Acme Bank's net interest income rose.") == [
        ("value", "acme_bank", "acme_bank.net_interest_income", "Acme Bank's net interest income")]
    assert found(gz, "Acme Bank’s NII rose.") == [("entity", "acme_bank", None, "Acme Bank"),
                                                    ("value", "acme_bank", "acme_bank.net_interest_income", "NII")]
    assert found(gz, "Two-year yields jumped.") == [("value", "gov_bonds", "gov_bonds.yield_2y", "Two-year yields")]


def test_longest_match_wins(gz):
    assert found(gz, "Acme Re Holdings said Acme Re adjusted net income rose.") == [
        ("entity", "acme_re", None, "Acme Re Holdings"),
        ("value", "acme_re", "acme_re.operating_profit", "Acme Re adjusted net income")]
    assert found(gz, "Government bonds 10Y yield")[0] == ("entity", "gov_bonds", None, "Government bonds")
    assert found(gz, "Government bonds 10Y yield") == [("entity", "gov_bonds", None, "Government bonds"),
                                                       ("value", "gov_bonds", "gov_bonds.yield_10y", "10Y yield")]


def test_a_span_naming_an_entity_and_a_value_is_the_value(gz):
    # "the dollar" is the dollar entity's alias and its index's alias: the value wins
    assert found(gz, "The dollar fell.") == [("value", "dollar", "dollar.index", "The dollar")]


def test_value_phrase_resolves_to_the_entity_before_it(gz):
    assert found(gz, "Ridge Energy said oil production rose.") == [
        ("entity", "ridge_energy", None, "Ridge Energy"), ("value", "ridge_energy", "ridge_energy.oil_output", "oil production")]
    assert found(gz, "Acme Bank said net interest income rose.")[-1] == (
        "value", "acme_bank", "acme_bank.net_interest_income", "net interest income")


def test_value_phrase_prefers_the_nearest_entity_before(gz):
    got = found(gz, "Delta and Acme Bank said net interest income rose.")
    assert got[-1] == ("value", "acme_bank", "acme_bank.net_interest_income", "net interest income")


def test_value_phrase_resolves_to_the_entity_after_it_when_none_before(gz):
    assert found(gz, "The fuel cost at Blue Freight rose.") == [
        ("value", "blue_freight", "blue_freight.fuel_cost", "fuel cost"), ("entity", "blue_freight", None, "Blue Freight")]


def test_value_phrase_resolves_to_the_context_entity_when_the_sentence_names_none(gz):
    assert found(gz, "Net interest income rose.", "delta_bank") == [
        ("value", "delta_bank", "delta_bank.net_interest_income", "Net interest income")]


def test_value_phrase_stays_unresolved_without_an_owner(gz):
    assert found(gz, "Net interest income rose.") == []
    assert found(gz, "Net interest income rose.", "shipping") == []          # shipping has no such value
    assert found(gz, "Oil said net interest income rose.") == [("entity", "crude_oil", None, "Oil")]


def test_head_word_resolves_only_for_an_entity_with_one_value_of_that_head(gz):
    # government bonds have two yields (2Y and 10Y), so "government bond yields" names the entity only
    assert found(gz, "Government bond yields rose.") == [("entity", "gov_bonds", None, "Government bond")]
    assert "gov_bonds" not in gz.slots.get("yield", {})
    # credit markets have one spread, so "spread" is its alias
    assert found(gz, "Credit markets said the spread widened.")[-1] == (
        "value", "credit_markets", "credit_markets.credit_spread", "spread")
    # two owners with one value of the head each: the head is a slot of both
    g = fake_graph({"a": ("Alpha", None, []), "b": ("Beta", None, [])},
                   {"a.y10": ("Alpha 10Y yield", []), "b.y10": ("Beta 10Y yield", [])})
    assert Gazetteer(g).slots["yield"] == {"a": "a.y10", "b": "b.y10"}


def test_slot_phrases_drop_the_entity_words_and_parentheticals(gz):
    assert gz.slots["yield 10y"]["gov_bonds"] == "gov_bonds.yield_10y"                       # the value's id, in words
    assert gz.slots["equity index"]["capital_markets"] == "capital_markets.equity_index"
    assert not any("(" in k for k in gz.slots)
    g = fake_graph({"cb": ("Central bank", None, [])}, {"cb.policy_rate": ("Central bank rate (midpoint)", [])})
    assert Gazetteer(g).slots["rate"] == {"cb": "cb.policy_rate"} and not any("midpoint" in k for k in Gazetteer(g).slots)


def test_matches_carry_character_spans(gz):
    text = "Later, the central bank raised its policy rate."
    for m in gz.find(text):
        assert text[m.start:m.end] == m.surface


def test_digest_is_stable_and_follows_the_graph(graph, gz):
    assert Gazetteer(graph).digest == gz.digest
    assert len(gz.digest) == 16
    a = fake_graph({"bank": ("Bank", None, ["BK"])}, {"bank.rate": ("Bank rate", [])})
    b = fake_graph({"bank": ("Bank", None, ["BK"])}, {"bank.rate": ("Bank rate", [])})
    c = fake_graph({"bank": ("Bank", None, ["BK", "The Bank"])}, {"bank.rate": ("Bank rate", [])})
    assert Gazetteer(a).digest == Gazetteer(b).digest != Gazetteer(c).digest


# -- edge cases on a small graph --------------------------------------------------------------------------------------
def test_short_names_unmatchable_names_and_orphan_values():
    g = fake_graph({"acme": ("Acme Corp", "Acme", ["—", "A", "AC"]), "solo": ("Solo", None, [])},
                   {"acme.rate": ("Acme rate", ["the rate"]), "ghost.level": ("Ghost level", []),
                    "acme.__": ("(note)", [])})
    gz = Gazetteer(g)
    assert found(gz, "Acme and AC said A rose; Acme Corp too.") == [
        ("entity", "acme", None, "Acme"), ("entity", "acme", None, "AC"), ("entity", "acme", None, "Acme Corp")]
    # a value whose entity is not in the graph is still named by its own name, never by a slot
    assert found(gz, "Ghost level fell.") == [("value", "ghost", "ghost.level", "Ghost level")]
    assert "level" in gz.slots and gz.slots["level"] == {"ghost": "ghost.level"}
    assert "" not in gz.slots                    # a phrase with no words ("__", "(note)") adds no slot


def test_a_head_shared_by_two_values_of_every_owner_adds_no_head_slot():
    g = fake_graph({"bonds": ("Bonds", None, [])},
                   {"bonds.y2": ("Bonds 2Y yield", []), "bonds.y10": ("Bonds 10Y yield", [])})
    gz = Gazetteer(g)
    assert "gov_bonds" not in gz.slots.get("yield", {})
    assert found(gz, "Bonds yields rose.") == [("entity", "bonds", None, "Bonds")]
    assert found(gz, "Bonds 2Y yield rose.") == [("value", "bonds", "bonds.y2", "Bonds 2Y yield")]


def test_a_head_that_is_already_a_slot_phrase_keeps_its_owners_and_adds_unique_ones():
    g = fake_graph({"fx": ("FX", None, []), "cb": ("Central bank", None, [])},
                   {"fx.rate": ("FX rate", []), "cb.policy_rate": ("Central bank policy rate", [])})
    gz = Gazetteer(g)
    assert gz.slots["rate"] == {"fx": "fx.rate", "cb": "cb.policy_rate"}
    assert found(gz, "Central bank rate rose.") == [("entity", "cb", None, "Central bank"),
                                                    ("value", "cb", "cb.policy_rate", "rate")]
    # a bare word names a value only right after its entity's name (or its verb: "the central bank raised rates")
    assert found(gz, "Central bank raised rates.")[-1] == ("value", "cb", "cb.policy_rate", "rates")
    assert found(gz, "Central bank said the rate rose.") == [("entity", "cb", None, "Central bank")]


# -- shared and generic phrases, the document's subject and region (Oct 17) ------------------------------------------------
def v(gz: Gazetteer, text: str, context: str | None = None, **kw) -> list[tuple]:
    return [(m.subentity_id, m.surface, m.via) for m in gz.find(text, context, **kw) if m.subentity_id]


def test_shared_and_company_aliases_are_slots(gz):
    assert {"delta_bank", "acme_bank"} <= set(gz.slots["nii"])                                 # NII is several banks'
    assert v(gz, "NII rose.") == []                                                          # whose? not said
    assert v(gz, "Delta NII rose.") == [("delta_bank.net_interest_income", "Delta NII", "name")]
    assert v(gz, "Delta said NII rose.") == [("delta_bank.net_interest_income", "NII", "sentence")]
    # a one-word lower-case alias of a company's value names nothing ("markets" for Acme Bank's markets revenue)
    assert "market" not in gz.slots and v(gz, "Acme Bank said markets rallied.") == []


def test_a_loose_value_alias_is_dropped_in_another_region(rg):
    assert v(rg, "Core inflation rose.") == [("hm_economy.core_inflation", "Core inflation", "name")]
    assert v(rg, "Core inflation rose.", region="FR") == []
    assert v(rg, "Far economy data: core inflation rose.") == []                        # the sentence names Far


def test_head_words_need_their_name_right_before(gz):
    assert v(gz, "Ridge Energy's profit rose.") == [("ridge_energy.operating_profit", "profit", "sentence")]
    assert v(gz, "Ridge Energy said profit rose.") == []
    assert v(gz, "The central bank raised rates.") == [("central_bank.policy_rate", "rates", "sentence")]
    assert v(gz, "Net income rose.", subject="ridge_energy") == []


def test_head_words_on_key_data_lines_name_the_subject(gz):
    assert v(gz, "Price (31 Jul 2026) $48.20", subject="ridge_energy") == [("ridge_energy.share_price", "Price", "subject")]
    assert v(gz, "Shr price, close (Oct 7, 2026) $2,901", subject="acme_motors") == [
        ("acme_motors.share_price", "price", "subject")]
    long = "As of yesterday the stock's closing price was $48.20, up on the day after the results came in strong."
    assert v(gz, long, subject="ridge_energy") == [("ridge_energy.share_price", "price", "subject")]
    assert v(gz, "Price Index rebased to 100", subject="ridge_energy") == []
    assert v(gz, "The long sentence about a price that goes on and on, much longer than a key-data line could be.",
             subject="ridge_energy") == []


def test_currency_codes_beside_figures_are_not_the_currency():
    gz = Gazetteer(fake_graph({"fx": ("Euro", None, ["EUR"]), "co": ("Co", None, [], {}, "company")},
                              {"fx.rate": ("Euro rate", ["EUR"]), "co.share_price": ("Co share price", [])}))
    assert v(gz, "Price 240 EUR", subject="co") == [("co.share_price", "Price", "subject")]
    assert v(gz, "The EUR weakened.") == [("fx.rate", "EUR", "name")]


def test_an_agency_before_hike_or_cut_stands_for_its_policy_rate(gz):
    assert v(gz, "Another central bank hike is priced.") == [("central_bank.policy_rate", "central bank", "name")]
    assert v(gz, "The central bank said little.") == []


def test_market_values_by_region(rg):
    assert v(rg, "In Home, 2Y yields rose.") == [("hm_bonds.yield_2y", "2Y yields", "region")]
    assert v(rg, "10-year yields rose.", region="HM") == [("hm_bonds.yield_10y", "10-year yields", "document")]
    assert v(rg, "10-year yields rose.") == []
    assert v(rg, "Policy rates rose.", region="FR") == [("fr_cb.policy_rate", "Policy rates", "document")]
    # an economy's growth by the document's region too, a company's value never
    assert v(rg, "Real GDP growth rose.", region="HM") == [("hm_economy.gdp_growth", "Real GDP growth", "document")]
    assert v(rg, "NII rose.", region="HM") == []


def test_context_and_subject(gz):
    assert v(gz, "Net interest income rose.", "acme_bank", subject="acme_bank")[0][2] == "context"
    # in a report on one company, a peer named in the previous sentence does not take its figures
    assert v(gz, "Net interest income rose.", "delta_bank", subject="acme_bank") == [
        ("acme_bank.net_interest_income", "Net interest income", "subject")]
    assert v(gz, "Net interest income rose.", subject="acme_bank")[0][2] == "subject"
    # ... nor when the sentence names another company, the model's or a ticker in the possessive
    assert v(gz, "Delta and net interest income rose.", subject="acme_bank")[0][0] == "delta_bank.net_interest_income"
    assert v(gz, "BAMI's net interest income rose.", subject="acme_bank") == []


def test_profile(gz, rg):
    assert gz.profile("Ridge Energy note", "Ridge Energy raised guidance.") == ("ridge_energy", "US")
    # the title names one company, the opening text names it not but other companies: no subject
    assert gz.profile("ACBK preview", "Ridge Energy and Delta reported.") == (None, "US")
    # several in the title (the publisher among them): the one the opening text names most
    assert gz.profile("Blue Freight on Acme Motors", "Acme Motors rose. Acme Motors fell. Acme Motors guided.") == (
        "acme_motors", "US")
    # none in the title: a company named at least three times, twice as often as any other
    assert gz.profile("note", "Delta. Delta. Delta. Acme Bank.") == ("delta_bank", "US")
    assert gz.profile("note", "Delta. Delta. Acme Bank. Acme Bank.") == (None, "US")
    assert gz.profile("note", "Delta. Delta. Delta. Acme Bank. Acme Bank.")[0] is None
    # a sector report lists many tickers
    assert gz.profile("ACBK preview", "ACBK, BAC, USB, PNC, FITB & CFG. Acme Bank leads.")[0] is None
    # ... though a list of measures is no list of tickers
    assert gz.profile("model.xlsx", "Delta Bank (DLTB US). Delta: NII, NIR and EPS, DPS, TBVPS & PPNR. Delta. (XYZ)") == (
        "delta_bank", "US")
    assert gz.profile("note", "Nothing named.") == (None, None)
    assert rg.profile("note", "The Home central bank and the Far central bank.") == (None, None)   # no majority region
    assert rg.profile("note", "Homeco. Home economy. Far bonds.") == (None, "HM")


def test_policy_actions_named_without_their_rate(gz, rg):
    assert v(gz, "Our economists revised their central bank call and now see two hikes this year.") == [
        ("central_bank.policy_rate", "hikes", "sentence")]
    # a "rate hike" says whose by the region the sentence names; the document's region is not enough
    assert v(rg, "We added two more rate hikes to our estimates.", region="HM") == []
    assert v(rg, "Rate hike speculation is present in Far.", region="HM") == [("fr_cb.policy_rate", "Rate hike", "region")]
    assert v(gz, "The central bank would temper any further rate rises.") == [
        ("central_bank.policy_rate", "rate rises", "sentence")]
    assert v(gz, "We added two more hikes.", region="US") == []          # a bare "hike": whose?
    assert v(gz, "We added two more rate hikes.") == []
    # another's hike: a price's, another instrument's, an unmodelled bank's
    assert v(gz, "The central bank noted price hikes.") == []
    assert v(gz, "The central bank made a PSL rate cut.") == []
    assert v(gz, "Markets price a BoE rate hike.", region="US") == []
    # the agency's own name before it already stands for the rate
    assert v(gz, "Another central bank hike is priced.") == [("central_bank.policy_rate", "central bank", "name")]
    assert v(gz, "The central bank rate hike came.") == [("central_bank.policy_rate", "The central bank", "name"),
                                                          ("central_bank.policy_rate", "rate", "sentence")]


def test_other_companies_and_publishers(gz):
    # a ticker heading a table row is another company's row
    assert v(gz, "WFC 1.88 1.84 with 1% higher NII", subject="acme_bank") == []
    assert v(gz, "Net interest income rose.", "acme_bank") == [("acme_bank.net_interest_income", "Net interest income",
                                                                "context")]
    assert v(gz, "BAC's net interest income rose.", "acme_bank") == []
    # the broker that publishes a note is not its subject
    assert gz.profile("Blue Freight Research - Acme Motors note", "Blue Freight & Co. Acme Motors. Blue Freight Research.") \
        == ("acme_motors", "US")


def test_a_table_rows_names_belong_to_their_cells(gz):
    assert v(gz, "CET1 ratio (%) | 13.1 | ACBK P&L from FY27", subject="delta_bank") == [
        ("delta_bank.cet1_ratio", "CET1 ratio", "subject")]
    assert v(gz, "NII | 13.1 | as Delta reported") == []                    # another cell names Delta
    assert v(gz, "Delta Bank CET1 ratio | 13.1")[0][0] == "delta_bank.cet1_ratio"


def test_a_reporting_ticker_is_another_company(gz):
    assert v(gz, "Note: BAC guided to higher net interest income.", "acme_bank") == []
    assert v(gz, "NII guided higher, and net interest income rose.", "acme_bank")[0][0] == "acme_bank.net_interest_income"
    assert v(gz, "BAC guided to NII up 6%; Acme Bank guided to more.") == []
    assert v(gz, "Acme Motors said NII was flat at Acme Bank.") == []
    assert v(gz, "Acme Bank guided to NII of $105bn; PNC guided to NII up 15%.") == [
        ("acme_bank.net_interest_income", "NII", "sentence")]
