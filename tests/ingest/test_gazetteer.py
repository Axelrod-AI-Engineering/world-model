"""Recognition: the world model's names found in text, by fixed rules, the same way every time."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from axelrod_wm.ingest.gazetteer import Gazetteer, _case_sensitive, norm, tokens


def found(gz: Gazetteer, text: str, context: str | None = None) -> list[tuple]:
    return [(m.kind, m.entity_id, m.subentity_id, m.surface) for m in gz.find(text, context)]


def fake_graph(entities: dict, values: dict):
    """A graph with only what the gazetteer reads: entities (name, short, aliases) and values (name, aliases)."""
    ents = {eid: NS(name=e[0], short=e[1], aliases=list(e[2])) for eid, e in entities.items()}
    subs = {sid: NS(name=v[0], aliases=list(v[1]), entity_id=sid.split(".")[0]) for sid, v in values.items()}
    return NS(entities=ents, subentities=subs)


# -- tokens and forms --------------------------------------------------------------------------------------------------
def test_tokens_keep_joined_words_and_drop_possessive_s():
    assert [t for t, _a, _b in tokens("Acmebank's USD/JPY S&P 1.25% Acme Re’s s 's")] == [
        "Acmebank", "USD/JPY", "S&P", "1.25", "%", "Acme", "Re", "s"]
    assert [t for t, _a, _b in tokens("s rose")] == ["s", "rose"]          # a leading s is a word


@pytest.mark.parametrize("word,form", [("Yields", "yield"), ("rates", "rate"), ("bps", "bps"), ("gas", "gas"),
                                       ("Glass", "glass"), ("status", "status"), ("basis", "basis"),
                                       ("JGBs", "jgb"), ("10Ys", "10ys")])
def test_norm_lowercases_and_drops_plural_s(word, form):
    assert norm(word) == form


@pytest.mark.parametrize("surface,sensitive", [("BoJ", True), ("ECB", True), ("KC", True), ("HBK", True),
                                               ("PBoC", True), ("Fed", False), ("Delta", False), ("brent", False),
                                               ("USD/JPY", False), ("FOMCX1", False)])
def test_case_sensitive_surfaces_are_short_and_mostly_capitals(surface, sensitive):
    assert _case_sensitive(surface) is sensitive


# -- matching against Acme's world -------------------------------------------------------------------------------------
def test_names_and_aliases_match_in_any_case_when_not_capitals(gz):
    assert found(gz, "Bank of Japan, bank of japan, BANK OF JAPAN.") == [("entity", "boj", None, "Bank of Japan"),
                                                                          ("entity", "boj", None, "bank of japan"),
                                                                          ("entity", "boj", None, "BANK OF JAPAN")]


def test_capital_surfaces_match_only_in_their_case(gz):
    assert found(gz, "BOJ and BoJ and Boj and boj.") == [("entity", "boj", None, "BOJ"), ("entity", "boj", None, "BoJ")]
    assert found(gz, "KC shares fell. ms. Smith said so.") == [("entity", "keystone_capital", None, "KC")]


def test_one_letter_surfaces_never_match(gz):
    assert "C" in gz.entities["delta_bank"].aliases
    assert found(gz, "C rose. Delta rose.") == [("entity", "delta_bank", None, "Delta")]


def test_possessives_and_plurals(gz):
    assert found(gz, "Acme Bank's net interest income rose.") == [
        ("value", "acme_bank", "acme_bank.net_interest_income", "Acme Bank's net interest income")]
    assert found(gz, "Acme Bank’s NII rose.") == [("entity", "acme_bank", None, "Acme Bank"),
                                                    ("value", "acme_bank", "acme_bank.net_interest_income", "NII")]
    assert found(gz, "UST 2Y yields jumped.") == [("value", "us_treasuries", "us_treasuries.yield_2y", "UST 2Y yields")]


def test_longest_match_wins(gz):
    assert found(gz, "Acme Re Holdings said Acme Re adjusted net income rose.") == [
        ("entity", "acme_re", None, "Acme Re Holdings"),
        ("value", "acme_re", "acme_re.operating_profit", "Acme Re adjusted net income")]
    assert found(gz, "JGB 10Y yield")[0] == ("value", "jgbs", "jgbs.yield_10y", "JGB 10Y yield")


def test_a_span_naming_an_entity_and_a_value_is_the_value(gz):
    # "USD/JPY" is the dollar_yen entity's name and its value's name: the value wins
    assert found(gz, "USD/JPY fell.") == [("value", "dollar_yen", "dollar_yen.usd_jpy", "USD/JPY")]


def test_value_phrase_resolves_to_the_entity_before_it(gz):
    assert found(gz, "Bund yields rose.") == [("entity", "bunds", None, "Bund"),
                                              ("value", "bunds", "bunds.yield_10y", "yields")]
    assert found(gz, "Acme Bank said net interest income rose.")[-1] == (
        "value", "acme_bank", "acme_bank.net_interest_income", "net interest income")


def test_value_phrase_prefers_the_nearest_entity_before(gz):
    got = found(gz, "Delta and Acme Bank said net interest income rose.")
    assert got[-1] == ("value", "acme_bank", "acme_bank.net_interest_income", "net interest income")


def test_value_phrase_resolves_to_the_entity_after_it_when_none_before(gz):
    assert found(gz, "The 10Y yield on Bunds rose.") == [("value", "bunds", "bunds.yield_10y", "10Y yield"),
                                                         ("entity", "bunds", None, "Bunds")]


def test_value_phrase_resolves_to_the_context_entity_when_the_sentence_names_none(gz):
    assert found(gz, "Net interest income rose.", "northwind_bank") == [
        ("value", "northwind_bank", "northwind_bank.net_interest_income", "Net interest income")]


def test_value_phrase_stays_unresolved_without_an_owner(gz):
    assert found(gz, "Net interest income rose.") == []
    assert found(gz, "Net interest income rose.", "boj") == []          # the BoJ has no such value
    assert found(gz, "Oil said net interest income rose.") == [("entity", "oil", None, "Oil")]


def test_head_word_resolves_only_for_an_entity_with_one_value_of_that_head(gz):
    # JGBs have two yields (10Y and 30Y), so "JGB yields" names the entity only; Bunds have one
    assert found(gz, "JGB yields rose.") == [("entity", "jgbs", None, "JGB")]
    assert gz.slots["yield"] == {"bunds": "bunds.yield_10y", "cgbs": "cgbs.yield_10y"}
    assert found(gz, "Bund yields fell; CGB yields too.") == [
        ("entity", "bunds", None, "Bund"), ("value", "bunds", "bunds.yield_10y", "yields"),
        ("entity", "cgbs", None, "CGB"), ("value", "cgbs", "cgbs.yield_10y", "yields")]


def test_slot_phrases_drop_the_entity_words_and_parentheticals(gz):
    assert gz.slots["fund rate"] == {"federal_reserve": "federal_reserve.policy_rate"}      # "Fed funds rate (midpoint)"
    assert set(gz.slots["equity index"]) == {"china_capital_markets", "europe_capital_markets", "japan_capital_markets",
                                             "us_capital_markets"}     # Oct 18: the US level (Acme Bank construction)
    assert gz.slots["10y yield"]["bunds"] == "bunds.yield_10y"                               # "Bund 10Y yield"
    assert not any("(" in k or "midpoint" in k for k in gz.slots)


def test_matches_carry_character_spans(gz):
    text = "Later, the BoJ raised its policy rate."
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
    assert "yield" not in gz.slots
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
    assert set(gz.slots["nii"]) == {"emerald_bank", "delta_bank", "acme_bank", "northwind_bank"}     # NII is several banks'
    assert v(gz, "NII rose.") == []                                                          # whose? not said
    assert v(gz, "Northwind Bank NII rose.") == [("northwind_bank.net_interest_income", "Northwind Bank NII", "name")]
    assert v(gz, "Delta said NII rose.") == [("delta_bank.net_interest_income", "NII", "sentence")]
    # a one-word lower-case alias of a company's value names nothing ("markets" for Acme Bank's markets revenue)
    assert "market" not in gz.slots and v(gz, "Acme Bank said markets rallied.") == []


def test_a_loose_value_alias_is_dropped_in_another_region(gz):
    assert v(gz, "Core inflation rose.") == [("us_economy.core_cpi", "Core inflation", "name")]
    assert v(gz, "Core inflation rose.", region="JP") == []
    assert v(gz, "In Japan, core inflation rose.") == []                               # the sentence names Japan


def test_head_words_need_their_name_right_before(gz):
    assert v(gz, "Acme Machinery's profit rose.") == [("acme_machinery.operating_profit", "profit", "sentence")]
    assert v(gz, "Acme Machinery said profit rose.") == []
    assert v(gz, "The Fed raised rates.") == [("federal_reserve.policy_rate", "rates", "sentence")]
    assert v(gz, "Net income rose.", subject="acme_machinery") == []


def test_head_words_on_key_data_lines_name_the_subject(gz):
    assert v(gz, "Price (31 Jul 2026) ¥6,994", subject="acme_machinery") == [("acme_machinery.share_price", "Price", "subject")]
    assert v(gz, "Shr price, close (Oct 7, 2026) ¥2,901", subject="acme_motors") == [
        ("acme_motors.share_price", "price", "subject")]
    long = "As of yesterday the stock's closing price was ¥6,994, up on the day after the results came in strong."
    assert v(gz, long, subject="acme_machinery") == [("acme_machinery.share_price", "price", "subject")]
    assert v(gz, "Price Index rebased to 100", subject="acme_machinery") == []
    assert v(gz, "The long sentence about a price that goes on and on, much longer than a key-data line could be.",
             subject="acme_machinery") == []


def test_currency_codes_beside_figures_are_not_the_currency(gz):
    assert v(gz, "Price 240 JPY", subject="acme_telecom") == [("acme_telecom.share_price", "Price", "subject")]
    assert v(gz, "The JPY weakened.") == [("dollar_yen.usd_jpy", "JPY", "name")]


def test_an_agency_before_hike_or_cut_stands_for_its_policy_rate(gz):
    assert v(gz, "Another ECB hike is priced.") == [("ecb.policy_rate", "ECB", "name")]
    assert v(gz, "The ECB said little.") == []


def test_market_values_by_region(gz):
    assert v(gz, "In the US, 2Y yields rose.") == [("us_treasuries.yield_2y", "2Y yields", "region")]
    assert v(gz, "10-year yields rose.", region="US") == [("us_treasuries.yield_10y", "10-year yields", "document")]
    assert v(gz, "10-year yields rose.") == []
    assert v(gz, "Policy rates rose.", region="EU") == [("ecb.policy_rate", "Policy rates", "document")]
    # an economy's growth by the document's region too, a company's value never
    assert v(gz, "Real GDP growth rose.", region="US") == [("us_economy.gdp_growth", "Real GDP growth", "document")]
    assert v(gz, "NII rose.", region="US") == []


def test_context_and_subject(gz):
    assert v(gz, "Net interest income rose.", "northwind_bank", subject="northwind_bank")[0][2] == "context"
    # in a report on one company, a peer named in the previous sentence does not take its figures
    assert v(gz, "Net interest income rose.", "delta_bank", subject="northwind_bank") == [
        ("northwind_bank.net_interest_income", "Net interest income", "subject")]
    assert v(gz, "Net interest income rose.", subject="northwind_bank")[0][2] == "subject"
    # ... nor when the sentence names another company, the model's or a ticker in the possessive
    assert v(gz, "Delta and net interest income rose.", subject="northwind_bank")[0][0] == "delta_bank.net_interest_income"
    assert v(gz, "BAMI's net interest income rose.", subject="northwind_bank") == []


def test_profile(gz):
    assert gz.profile("Acme Machinery note", "Acme Machinery raised guidance.") == ("acme_machinery", "JP")
    # the title names one company, the opening text names it not but other companies: no subject
    assert gz.profile("ACME preview", "Keystone Capital and Delta reported.") == (None, "US")
    assert gz.profile("601939 CN", "China's banks: data.") == ("harbor_bank", "CN")
    # several in the title (the publisher among them): the one the opening text names most
    assert gz.profile("Keystone Capital on Acme Motors", "Acme Motors rose. Acme Motors fell. Acme Motors guided.") == ("acme_motors", "JP")
    # none in the title: a company named at least three times, twice as often as any other
    assert gz.profile("note", "Delta. Delta. Delta. Acme Bank.") == ("delta_bank", "US")
    assert gz.profile("note", "Delta. Delta. Acme Bank. Acme Bank.") == (None, "US")
    assert gz.profile("note", "Delta. Delta. Delta. Acme Bank. Acme Bank.")[0] is None
    # a sector report lists many tickers
    assert gz.profile("ACME preview", "ACME, BAC, USB, PNC, FITB & CFG. Acme Bank leads.")[0] is None
    # ... though a list of measures is no list of tickers
    assert gz.profile("model.xlsx", "Delta Bank (C US). Delta: NII, NIR and EPS, DPS, TBVPS & PPNR. Delta. (XYZ)") == (
        "delta_bank", "US")
    assert gz.profile("note", "Nothing named.") == (None, None)
    assert gz.profile("note", "The Fed and the ECB and the BoJ.") == (None, None)       # no majority region


def test_policy_actions_named_without_their_rate(gz):
    assert v(gz, "Our economists revised their Fed call and now see two hikes this year.") == [
        ("federal_reserve.policy_rate", "hikes", "sentence")]
    # a "rate hike" says whose by the region the sentence names; the document's region is not enough
    assert v(gz, "We added two more rate hikes to our estimates.", region="US") == []
    assert v(gz, "Rate hike speculation is present in the Eurozone.", region="CN") == [
        ("ecb.policy_rate", "Rate hike", "region")]
    assert v(gz, "The Fed would temper any further rate rises.") == [
        ("federal_reserve.policy_rate", "rate rises", "sentence")]
    assert v(gz, "We added two more hikes.", region="US") == []          # a bare "hike": whose?
    assert v(gz, "We added two more rate hikes.") == []
    # another's hike: a price's, another instrument's, an unmodelled bank's
    assert v(gz, "The Fed noted price hikes.") == []
    assert v(gz, "The PBoC made a PSL rate cut.") == []
    assert v(gz, "Markets price a BoE rate hike.", region="EU") == []
    # the agency's own name before it already stands for the rate
    assert v(gz, "Another ECB hike is priced.") == [("ecb.policy_rate", "ECB", "name")]
    assert v(gz, "The Fed rate hike came.") == [("federal_reserve.policy_rate", "Fed rate", "name")]


def test_other_companies_and_publishers(gz):
    # a ticker heading a table row is another company's row
    assert v(gz, "WFC 1.88 1.84 with 1% higher NII", subject="acme_bank") == []
    assert v(gz, "Net interest income rose.", "acme_bank") == [("acme_bank.net_interest_income", "Net interest income",
                                                                "context")]
    assert v(gz, "BAC's net interest income rose.", "acme_bank") == []
    # the broker that publishes a note is not its subject
    assert gz.profile("Keystone Capital Research - Acme Motors note", "Keystone Capital & Co. Acme Motors. Keystone Capital Research.") \
        == ("acme_motors", "JP")


def test_a_table_rows_names_belong_to_their_cells(gz):
    assert v(gz, "CET1 ratio (%) | 13.1 | ACME P&L from FY27", subject="northwind_bank") == [
        ("northwind_bank.cet1_ratio", "CET1 ratio", "subject")]
    assert v(gz, "NII | 13.1 | as Delta reported") == []                    # another cell names Delta
    assert v(gz, "Northwind Bank CET1 ratio | 13.1")[0][0] == "northwind_bank.cet1_ratio"


def test_a_reporting_ticker_is_another_company(gz):
    assert v(gz, "Note: BAC guided to higher net interest income.", "acme_bank") == []
    assert v(gz, "NII guided higher, and net interest income rose.", "acme_bank")[0][0] == "acme_bank.net_interest_income"
    assert v(gz, "BAC guided to NII up 6%; Acme Bank guided to more.") == []
    assert v(gz, "Acme Motors said NII was flat at Acme Bank.") == []
    assert v(gz, "Acme Bank guided to NII of $105bn; PNC guided to NII up 15%.") == [
        ("acme_bank.net_interest_income", "NII", "sentence")]
