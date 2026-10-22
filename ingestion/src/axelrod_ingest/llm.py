"""The LLM step (Oct 17): proposals for what the rules miss, replayed from a cache so a re-run is identical.

Off unless a provider is configured (WORLD_MODEL_LLM_PROVIDER=anthropic|openai, with ANTHROPIC_API_KEY or
OPENAI_API_KEY, and optionally WORLD_MODEL_LLM_MODEL). Only chunks that name the model's entities but gave the rules
nothing are sent. The prompt lists the model's ids for the entities named; the answer must be JSON signals in the
import schema. Every answer is validated: unknown ids, quotes not in the text, and malformed signals are dropped,
never repaired. Answers are cached by (provider, model, prompt version, chunk text, gazetteer digest), so the same
document against the same model, with the same provider configured, replays byte-identically without a second call. Each signal it adds is
marked (note "llm:<model>"), and like every signal it waits for a person's review.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import TypeAdapter, ValidationError

from axelrod_ingest.contract.bundle import Signal
from axelrod_ingest.lake.store import LakeStore, digest

PROMPT_VERSION = "llm-signals-1"
TIMEOUT = 60.0
SYSTEM = (
    "You read one passage of financial research and list the claims it makes about named values of a causal world "
    "model. Use only the ids given. Output a JSON object {\"signals\": [...]} and nothing else. Each signal is one of: "
    "{\"type\":\"observe\",\"value_of\":id,\"value\":number in the value's unit,\"quote\":exact sentence}; "
    "{\"type\":\"move\",\"value_of\":id,\"delta\":number,\"mode\":\"relative\"|\"absolute\"|\"standardized\",\"quote\":...}; "
    "{\"type\":\"support\"|\"contradict\",\"source\":id,\"target\":id,\"quote\":...} for a listed link; "
    "{\"type\":\"link\",\"source\":id,\"target\":id,\"label\":verb,\"effect\":-1..1,\"quote\":...}. "
    "Quotes must be copied exactly from the passage. If the passage claims nothing about these values, return "
    "{\"signals\": []}.")

_SIGNALS = TypeAdapter(list[Signal])


class Provider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str) -> str: ...


@dataclass
class Anthropic:
    api_key: str
    model: str = "claude-haiku-5-5"
    name: str = "anthropic"
    url: str = "https://api.anthropic.com/v1/messages"

    def complete(self, system: str, user: str) -> str:
        r = httpx.post(self.url, timeout=TIMEOUT, headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                                                          "content-type": "application/json"},
                       json={"model": self.model, "max_tokens": 2048, "temperature": 0, "system": system,
                             "messages": [{"role": "user", "content": user}]})
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")


@dataclass
class OpenAI:
    api_key: str
    model: str = "gpt-5.6-luna"
    name: str = "openai"
    url: str = "https://api.openai.com/v1/chat/completions"

    def complete(self, system: str, user: str) -> str:
        r = httpx.post(self.url, timeout=TIMEOUT, headers={"authorization": f"Bearer {self.api_key}"},
                       json={"model": self.model, "temperature": 0, "response_format": {"type": "json_object"},
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def provider_from_env(env: dict[str, str] | None = None) -> Provider | None:
    """The configured provider, or None (the default: the LLM step is off)."""
    env = dict(os.environ) if env is None else env
    which = env.get("WORLD_MODEL_LLM_PROVIDER", "").strip().lower()
    model = env.get("WORLD_MODEL_LLM_MODEL", "").strip()
    if which == "anthropic" and env.get("ANTHROPIC_API_KEY"):
        return Anthropic(env["ANTHROPIC_API_KEY"], **({"model": model} if model else {}))
    if which == "openai" and env.get("OPENAI_API_KEY"):
        return OpenAI(env["OPENAI_API_KEY"], **({"model": model} if model else {}))
    return None


def _prompt(text: str, graph: Any, entity_ids: list[str]) -> str:
    lines = ["Values you may name (id: name, unit):"]
    for eid in sorted(entity_ids):
        for sid in graph.entities[eid].subentity_ids:
            s = graph.subentities.get(sid)
            if s is not None:
                lines.append(f"- {sid}: {s.name}, {s.unit}")
    links = [i for i in graph.active_interactions()
             if graph.subentities[i.source_id].entity_id in entity_ids or graph.subentities[i.target_id].entity_id in entity_ids]
    if links:
        lines.append("Links the model already holds (source -> target, label):")
        lines += [f"- {i.source_id} -> {i.target_id}: {i.label}" for i in sorted(links, key=lambda x: x.id)]
    lines += ["", "Passage:", text]
    return "\n".join(lines)


def _parse(raw: str) -> list[dict]:
    """The signals in a provider's answer: the first JSON object in it, its "signals" list (or [])."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        obj = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return []
    sigs = obj.get("signals") if isinstance(obj, dict) else None
    return [s for s in sigs if isinstance(s, dict)] if isinstance(sigs, list) else []


def validate(signals: list[dict], text: str, graph: Any) -> list[dict]:
    """The signals that are well formed, name the model's values, and quote the passage exactly."""
    out = []
    for s in signals:
        try:
            sig = _SIGNALS.validate_python([s])[0]
        except ValidationError:
            continue
        ids = [getattr(sig, k) for k in ("value_of", "source", "target") if hasattr(sig, k)]
        if any(i not in graph.subentities for i in ids) or not sig.quote or sig.quote not in text:
            continue
        if sig.type in ("support", "contradict") and not any(
                i.source_id == sig.source and i.target_id == sig.target for i in graph.active_interactions()):
            continue
        out.append(sig.model_dump(mode="json", exclude_defaults=False))
    return out


def propose(text: str, graph: Any, entity_ids: list[str], *, provider: Provider | None, store: LakeStore,
            gazetteer_digest: str) -> list[dict]:
    """Signals for one passage: from the cache when this exact question was asked of this provider and model
    before, else from the provider, cached. With no provider configured, the step is off: nothing."""
    if provider is None:
        return []
    user = _prompt(text, graph, entity_ids)
    pname, pmodel = provider.name, provider.model
    key = digest({"v": PROMPT_VERSION, "provider": pname, "model": pmodel, "user": user, "gz": gazetteer_digest})
    hit = store.cache_get(key)
    if hit is None:
        raw = provider.complete(SYSTEM, user)
        hit = {"raw": raw}
        store.cache_put(key, pname, pmodel, hit)
    sigs = validate(_parse(hit["raw"]), text, graph)
    for s in sigs:
        s["note"] = f"llm:{pmodel}" + (f"; {s['note']}" if s.get("note") else "")
    return sigs
