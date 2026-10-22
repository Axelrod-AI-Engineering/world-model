"""The LLM step: off by default, temperature 0, answers validated against the passage and the model, and replayed
from the cache so a re-run is byte-identical without a second call."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import httpx
import pytest

from axelrod_ingest import llm
from axelrod_ingest.llm import (
    PROMPT_VERSION,
    SYSTEM,
    Anthropic,
    OpenAI,
    _parse,
    _prompt,
    propose,
    provider_from_env,
    validate,
)

TEXT = "Acme Re said overseas profit should benefit. Acme Bank was quiet."


# -- configuration ------------------------------------------------------------------------------------------------------
def test_provider_from_env():
    assert provider_from_env({}) is None
    assert provider_from_env({"WORLD_MODEL_LLM_PROVIDER": "anthropic"}) is None             # no key: off
    assert provider_from_env({"WORLD_MODEL_LLM_PROVIDER": "openai", "ANTHROPIC_API_KEY": "k"}) is None
    assert provider_from_env({"WORLD_MODEL_LLM_PROVIDER": "none", "OPENAI_API_KEY": "k"}) is None
    a = provider_from_env({"WORLD_MODEL_LLM_PROVIDER": " Anthropic ", "ANTHROPIC_API_KEY": "ka"})
    assert isinstance(a, Anthropic) and a.api_key == "ka" and a.model == "claude-haiku-5-5" and a.name == "anthropic"
    o = provider_from_env({"WORLD_MODEL_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "ko", "WORLD_MODEL_LLM_MODEL": " "})
    assert isinstance(o, OpenAI) and o.model == "gpt-5.6-luna" and o.name == "openai"
    assert provider_from_env({"WORLD_MODEL_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "k",
                              "WORLD_MODEL_LLM_MODEL": "claude-x"}).model == "claude-x"
    assert provider_from_env({"WORLD_MODEL_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "k",
                              "WORLD_MODEL_LLM_MODEL": "gpt-x"}).model == "gpt-x"


def test_provider_from_env_reads_the_environment_by_default(monkeypatch):
    assert provider_from_env() is None                            # the test environment has no provider
    monkeypatch.setenv("WORLD_MODEL_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    assert isinstance(provider_from_env(), OpenAI)


# -- providers over HTTP (mocked) -----------------------------------------------------------------------------------------
class FakeHTTP:
    def __init__(self, body: dict, status: int = 200) -> None:
        self.body, self.status, self.calls = body, status, []

    def __call__(self, url, *, timeout, headers, json):
        self.calls.append({"url": url, "timeout": timeout, "headers": headers, "json": json})
        return httpx.Response(self.status, json=self.body, request=httpx.Request("POST", url))


def test_anthropic_complete(monkeypatch):
    fake = FakeHTTP({"content": [{"type": "text", "text": '{"signals":'}, {"type": "tool_use", "id": "x"},
                                 {"type": "text", "text": " []}"}, {"type": "text"}]})
    monkeypatch.setattr(httpx, "post", fake)
    assert Anthropic("key", model="m").complete("sys", "user") == '{"signals": []}'
    (call,) = fake.calls
    assert call["url"] == "https://api.anthropic.com/v1/messages" and call["timeout"] == llm.TIMEOUT
    assert call["headers"] == {"x-api-key": "key", "anthropic-version": "2023-06-01", "content-type": "application/json"}
    assert call["json"] == {"model": "m", "max_tokens": 2048, "temperature": 0, "system": "sys",
                            "messages": [{"role": "user", "content": "user"}]}


def test_anthropic_complete_without_content(monkeypatch):
    monkeypatch.setattr(httpx, "post", FakeHTTP({}))
    assert Anthropic("key").complete("s", "u") == ""


def test_openai_complete(monkeypatch):
    fake = FakeHTTP({"choices": [{"message": {"content": '{"signals": []}'}}]})
    monkeypatch.setattr(httpx, "post", fake)
    assert OpenAI("key").complete("sys", "user") == '{"signals": []}'
    (call,) = fake.calls
    assert call["url"] == "https://api.openai.com/v1/chat/completions"
    assert call["headers"] == {"authorization": "Bearer key"}
    assert call["json"] == {"model": "gpt-5.6-luna", "temperature": 0, "response_format": {"type": "json_object"},
                            "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "user"}]}


@pytest.mark.parametrize("provider", [Anthropic("k"), OpenAI("k")])
def test_http_errors_raise(monkeypatch, provider):
    monkeypatch.setattr(httpx, "post", FakeHTTP({"error": "nope"}, status=429))
    with pytest.raises(httpx.HTTPStatusError):
        provider.complete("s", "u")


# -- the prompt -----------------------------------------------------------------------------------------------------------
def test_prompt_lists_the_named_entities_values_and_their_links(graph):
    p = _prompt(TEXT, graph, ["acme_re", "central_bank"])
    lines = p.split("\n")
    assert lines[0] == "Values you may name (id: name, unit):"
    assert "- central_bank.policy_rate: Policy rate, pct" in lines
    assert "- acme_re.international_profit: Acme Re international business profit, $bn/yr" in lines
    k = lines.index("Links the model already holds (source -> target, label):")
    links = lines[k + 1:lines.index("")]
    # every link touching a named entity, in link-id order (m08 before m10 before m20 before m23)
    assert links.index("- central_bank.policy_rate -> gov_bonds.yield_2y: anchors") < links.index(
        "- central_bank.policy_rate -> dollar.index: strengthens") < links.index(
        "- gov_bonds.yield_10y -> acme_re.domestic_pc_profit: lifts reinvestment income") < links.index(
        "- dollar.index -> acme_re.international_profit: lifts translated profit")
    assert "- central_bank.policy_rate -> acme_bank.net_interest_income: widens margins" in links
    assert not any("crude_oil.price -> economy.headline_inflation" in ln for ln in links)
    assert lines[-2:] == ["Passage:", TEXT]
    assert _prompt(TEXT, graph, ["central_bank", "acme_re"]) == p


def test_prompt_without_links_or_with_missing_values():
    g = NS(entities={"e": NS(subentity_ids=["e.a", "e.gone"])}, subentities={"e.a": NS(name="A", unit="pct")},
           active_interactions=lambda: [])
    assert _prompt("t", g, ["e"]) == "Values you may name (id: name, unit):\n- e.a: A, pct\n\nPassage:\nt"


# -- parsing and validating answers --------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,want", [
    ("", []),
    ("no json here", []),
    ("} backwards {", []),
    ("{not json}", []),
    ("[1, 2]", []),
    ('Sure: {"answer": 1} done', []),
    ('{"signals": "none"}', []),
    ('{"signals": [{"type": "move"}, 3, "x", null, {"type": "observe"}]}', [{"type": "move"}, {"type": "observe"}]),
    ('Here you go:\n```json\n{"signals": [{"type": "link"}]}\n```', [{"type": "link"}]),
])
def test_parse(raw, want):
    assert _parse(raw) == want


def test_validate_keeps_only_well_formed_known_quoted_signals(graph):
    q = "Acme Re said overseas profit should benefit."
    good_link = {"type": "link", "source": "gov_bonds.yield_10y", "target": "acme_re.operating_profit",
                 "label": "lifts", "effect": 0.2, "quote": q}
    good_support = {"type": "support", "source": "dollar.index", "target": "acme_re.international_profit",
                    "quote": q}
    good_move = {"type": "move", "value_of": "acme_re.international_profit", "delta": 0.05, "mode": "relative",
                 "quote": q, "note": "translation"}
    good_observe = {"type": "observe", "value_of": "central_bank.policy_rate", "value": 4.0, "quote": "Acme Bank was quiet."}
    bad = [
        {"type": "move", "value_of": "no.such", "delta": 0.1, "quote": q},                      # unknown id
        {"type": "link", "source": "central_bank.policy_rate", "target": "nope", "label": "x", "effect": 0.1, "quote": q},
        {"type": "move", "value_of": "central_bank.policy_rate", "delta": 0.1, "quote": "not in the passage"},
        {"type": "move", "value_of": "central_bank.policy_rate", "delta": 0.1},                           # no quote
        {"type": "move", "value_of": "central_bank.policy_rate", "delta": "big", "quote": q},              # malformed
        {"type": "guess", "quote": q},                                                            # unknown type
        {"type": "move", "value_of": "central_bank.policy_rate", "delta": 0.1, "quote": q, "extra": 1},    # extra field
        {"type": "contradict", "source": "central_bank.policy_rate", "target": "acme_re.international_profit",
         "quote": q},                                                                             # no such link
    ]
    got = validate([bad[0], good_link, *bad[1:], good_support, good_move, good_observe], TEXT, graph)
    assert [s["type"] for s in got] == ["link", "support", "move", "observe"]
    assert got[0] == {**good_link, "delay_days": 7.0, "lag_days": 30.0, "duration_days": None, "note": ""}
    assert got[1] == {**good_support, "strength": 0.5, "note": ""}
    assert got[2] == good_move and got[3] == {**good_observe, "note": ""}


# -- propose: off, cached, replayed ----------------------------------------------------------------------------------------
class FakeProvider:
    def __init__(self, answer: str, name: str = "fake", model: str = "fake-1") -> None:
        self.name, self.model, self.answer, self.calls = name, model, answer, []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.answer


ANSWER = json.dumps({"signals": [
    {"type": "support", "source": "dollar.index", "target": "acme_re.international_profit",
     "quote": "Acme Re said overseas profit should benefit.", "note": "translation"},
    {"type": "move", "value_of": "acme_re.international_profit", "delta": 0.05, "mode": "relative",
     "quote": "Acme Re said overseas profit should benefit."},
    {"type": "move", "value_of": "made.up", "delta": 0.05, "quote": "Acme Bank was quiet."}]})


def test_propose_is_off_without_a_provider(graph, lake):
    assert propose(TEXT, graph, ["acme_re"], provider=None, store=lake, gazetteer_digest="g") == []


def test_propose_calls_once_then_replays_from_the_cache(graph, lake):
    p = FakeProvider(ANSWER)
    first = propose(TEXT, graph, ["acme_re"], provider=p, store=lake, gazetteer_digest="g")
    assert len(p.calls) == 1 and p.calls[0] == (SYSTEM, _prompt(TEXT, graph, ["acme_re"]))
    assert [s["note"] for s in first] == ["llm:fake-1; translation", "llm:fake-1"]
    p.answer = '{"signals": []}'                            # a different answer now would not be asked for
    again = propose(TEXT, graph, ["acme_re"], provider=p, store=lake, gazetteer_digest="g")
    assert len(p.calls) == 1
    assert json.dumps(again, sort_keys=True) == json.dumps(first, sort_keys=True)


def test_cache_key_covers_provider_model_text_and_gazetteer(graph, lake):
    p = FakeProvider(ANSWER)
    propose(TEXT, graph, ["acme_re"], provider=p, store=lake, gazetteer_digest="g")
    propose(TEXT, graph, ["acme_re"], provider=p, store=lake, gazetteer_digest="g2")
    propose(TEXT + " More.", graph, ["acme_re"], provider=p, store=lake, gazetteer_digest="g")
    propose(TEXT, graph, ["acme_re", "acme_bank"], provider=p, store=lake, gazetteer_digest="g")
    assert len(p.calls) == 4
    other = FakeProvider(ANSWER, model="fake-2")
    got = propose(TEXT, graph, ["acme_re"], provider=other, store=lake, gazetteer_digest="g")
    assert len(other.calls) == 1 and got[1]["note"] == "llm:fake-2"
    from axelrod_ingest.lake.store import digest

    key = digest({"v": PROMPT_VERSION, "provider": "fake", "model": "fake-1",
                  "user": _prompt(TEXT, graph, ["acme_re"]), "gz": "g"})
    assert lake.cache_get(key) == {"raw": ANSWER}


def test_cached_answers_are_revalidated(graph, lake):
    # the cache holds the raw answer: signals naming values the model no longer has are dropped on replay
    p = FakeProvider(ANSWER)
    got = propose(TEXT, graph, ["acme_re"], provider=p, store=lake, gazetteer_digest="g")
    assert all(s.get("value_of") != "made.up" for s in got) and len(got) == 2
