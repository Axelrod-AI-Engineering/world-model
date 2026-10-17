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
    assert [t for t, _a, _b in tokens("JPMorgan's USD/JPY S&P 1.25% Tokio Marine’s s 's")] == [
        "JPMorgan", "USD/JPY", "S&P", "1.25", "%", "Tokio", "Marine", "s"]
    assert [t for t, _a, _b in tokens("s rose")] == ["s", "rose"]          # a leading s is a word


@pytest.mark.parametrize("word,form", [("Yields", "yield"), ("rates", "rate"), ("bps", "bps"), ("gas", "gas"),
                                       ("Glass", "glass"), ("status", "status"), ("basis", "basis"),
                                       ("JGBs", "jgb"), ("10Ys", "10ys")])
def test_norm_lowercases_and_drops_plural_s(word, form):
    assert norm(word) == form


@pytest.mark.parametrize("surface,sensitive", [("BoJ", True), ("ECB", True), ("MS", True), ("CCB", True),
                                               ("PBoC", True), ("Fed", False), ("Citi", False), ("brent", False),
                                               ("USD/JPY", False), ("FOMCX1", False)])
def test_case_sensitive_surfaces_are_short_and_mostly_capitals(surface, sensitive):
    assert _case_sensitive(surface) is sensitive


# -- matching against Sally's world -------------------------------------------------------------------------------------
def test_names_and_aliases_match_in_any_case_when_not_capitals(gz):
    assert found(gz, "Bank of Japan, bank of japan, BANK OF JAPAN.") == [("entity", "boj", None, "Bank of Japan"),
                                                                          ("entity", "boj", None, "bank of japan"),
                                                                          ("entity", "boj", None, "BANK OF JAPAN")]


def test_capital_surfaces_match_only_in_their_case(gz):
    assert found(gz, "BOJ and BoJ and Boj and boj.") == [("entity", "boj", None, "BOJ"), ("entity", "boj", None, "BoJ")]
    assert found(gz, "MS shares fell. ms. Smith said so.") == [("entity", "morgan_stanley", None, "MS")]


def test_one_letter_surfaces_never_match(gz):
    assert "C" in gz.entities["citigroup"].aliases
    assert found(gz, "C rose. Citi rose.") == [("entity", "citigroup", None, "Citi")]


def test_possessives_and_plurals(gz):
    assert found(gz, "JPMorgan's net interest income rose.") == [
        ("value", "jpmorgan", "jpmorgan.net_interest_income", "JPMorgan's net interest income")]
    assert found(gz, "JPMorgan’s NII rose.") == [("entity", "jpmorgan", None, "JPMorgan"),
                                                    ("value", "jpmorgan", "jpmorgan.net_interest_income", "NII")]
    assert found(gz, "UST 2Y yields jumped.") == [("value", "us_treasuries", "us_treasuries.yield_2y", "UST 2Y yields")]


def test_longest_match_wins(gz):
    assert found(gz, "Tokio Marine Holdings said Tokio Marine adjusted net income rose.") == [
        ("entity", "tokio_marine", None, "Tokio Marine Holdings"),
        ("value", "tokio_marine", "tokio_marine.operating_profit", "Tokio Marine adjusted net income")]
    assert found(gz, "JGB 10Y yield")[0] == ("value", "jgbs", "jgbs.yield_10y", "JGB 10Y yield")


def test_a_span_naming_an_entity_and_a_value_is_the_value(gz):
    # "USD/JPY" is the dollar_yen entity's name and its value's name: the value wins
    assert found(gz, "USD/JPY fell.") == [("value", "dollar_yen", "dollar_yen.usd_jpy", "USD/JPY")]


def test_value_phrase_resolves_to_the_entity_before_it(gz):
    assert found(gz, "Bund yields rose.") == [("entity", "bunds", None, "Bund"),
                                              ("value", "bunds", "bunds.yield_10y", "yields")]
    assert found(gz, "JPMorgan said net interest income rose.")[-1] == (
        "value", "jpmorgan", "jpmorgan.net_interest_income", "net interest income")


def test_value_phrase_prefers_the_nearest_entity_before(gz):
    got = found(gz, "Citi and JPMorgan said net interest income rose.")
    assert got[-1] == ("value", "jpmorgan", "jpmorgan.net_interest_income", "net interest income")


def test_value_phrase_resolves_to_the_entity_after_it_when_none_before(gz):
    assert found(gz, "The 10Y yield on Bunds rose.") == [("value", "bunds", "bunds.yield_10y", "10Y yield"),
                                                         ("entity", "bunds", None, "Bunds")]


def test_value_phrase_resolves_to_the_context_entity_when_the_sentence_names_none(gz):
    assert found(gz, "Net interest income rose.", "unicredit") == [
        ("value", "unicredit", "unicredit.net_interest_income", "Net interest income")]


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
    assert set(gz.slots["equity index"]) == {"china_capital_markets", "europe_capital_markets", "japan_capital_markets"}
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
    assert found(gz, "Central bank said the rate rose.") == [("entity", "cb", None, "Central bank"),
                                                             ("value", "cb", "cb.policy_rate", "rate")]
