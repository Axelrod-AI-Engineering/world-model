"""Translators: the agentic interface from market events to graph update events (§7.4)."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol

import yaml
from pydantic import BaseModel, ConfigDict

from axelrod_wm.clients import EXAMPLES_DIR
from axelrod_wm.engine.registry import register, registry
from axelrod_wm.events.graph_update import GraphUpdateEvent
from axelrod_wm.events.market import MarketEvent
from axelrod_wm.intake.resolver import AliasFuzzyResolver
from axelrod_wm.model.evidence import Evidence, SourceType
from axelrod_wm.model.taxonomy import TaxonomyKind

if TYPE_CHECKING:
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.model.entity import Subentity
    from axelrod_wm.model.superentity import SuperentityPattern
    from axelrod_wm.model.taxonomy import AttributeVocabulary


class TranslationContext:
    """Read-only view of the model for translators. An LLM translator gets the same content as text."""

    def __init__(self, wm: WorkingMemory, ltm: LongTermMemory, vocab: AttributeVocabulary, now: datetime,
                 recent: Callable[[int], list[GraphUpdateEvent]] | None = None,
                 emit: Callable[..., None] | None = None) -> None:
        self.wm = wm
        self.ltm = ltm
        self.vocab = vocab
        self.now = now
        self._recent = recent
        self.emit = emit or (lambda *a, **k: None)
        self._resolver = AliasFuzzyResolver()

    def search_entities(self, text: str, limit: int = 5) -> list[tuple[str, float]]:
        return self._resolver.resolve(text, {}, sorted(self.wm.graph.entities), self.wm.graph)[:limit]

    def subentities_of(self, entity_id: str) -> list[Subentity]:
        ent = self.wm.graph.entities.get(entity_id)
        return [self.wm.graph.subentities[s] for s in (ent.subentity_ids if ent else []) if s in self.wm.graph.subentities]

    def attribute_vocabulary(self) -> AttributeVocabulary:
        return self.vocab

    def taxonomy_outline(self, kind: TaxonomyKind, depth: int = 2) -> list[tuple[str, str, int]]:
        """(generalization id, name, depth) rows."""
        tax = self.ltm.taxonomy(kind)
        rows: list[tuple[str, str, int]] = []

        def walk(gid: str, d: int) -> None:
            rows.append((gid, tax.nodes[gid].name, d))
            if d < depth:
                for c in tax.nodes[gid].child_ids:
                    walk(c, d + 1)

        if tax.root_id in tax.nodes:
            walk(tax.root_id, 0)
        return rows

    def admitted_patterns(self) -> list[SuperentityPattern]:
        return self.ltm.object_generalizations.admitted()

    def recent_events(self, n: int = 20) -> list[GraphUpdateEvent]:
        return self._recent(n) if self._recent else []


class TranslationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_event_id: str
    events: list[GraphUpdateEvent]
    rationale: str = ""
    spans: list[tuple[int, int, int]] = []    # (start, end, op index) in headline + body, for highlighting


class MarketEventTranslator(ABC):
    @abstractmethod
    def translate(self, event: MarketEvent, ctx: TranslationContext) -> TranslationResult: ...


registry("translator", MarketEventTranslator)


def fill_event(data: dict, market: MarketEvent | None, produced_by: str, index: int = 0) -> dict:
    """Fixtures may leave out id, recorded_at, and produced_by; the loader fills them (§7.2)."""
    out = dict(data)
    if market is not None:
        out.setdefault("id", f"GUE-{market.id}" + (f"-{index + 1}" if index else ""))
        out.setdefault("recorded_at", market.published_at.isoformat())
        out.setdefault("occurred_at", market.occurred_at.isoformat())
        out.setdefault("market_event_id", market.id)
        if "mentions" not in out and market.mentions:
            out["mentions"] = list(market.mentions)
        if "tags" not in out and market.tags:
            out["tags"] = list(market.tags)
    out.setdefault("produced_by", produced_by)
    out.setdefault("kind", "real")
    return out


@register("translator", "hand_drawn")
class HandDrawnTranslator(MarketEventTranslator):
    """Loads translations/<market_event_id>.json, which holds a TranslationResult. If the file is
    missing, it returns no events and emits translate.missing."""

    def __init__(self, config: Any = None, directory: str | Path | None = None) -> None:
        self.config = config
        self.directory = Path(directory) if directory is not None else None

    def translate(self, event: MarketEvent, ctx: TranslationContext) -> TranslationResult:
        path = self.directory / f"{event.id}.json" if self.directory is not None else None
        if path is None or not path.exists():
            ctx.emit("translate.missing", market_event_id=event.id)
            return TranslationResult(market_event_id=event.id, events=[], rationale="no hand-drawn translation")
        raw = json.loads(path.read_text())
        events = [fill_event(e, event, "hand_drawn", i) for i, e in enumerate(raw.get("events", []))]
        return TranslationResult.model_validate({**raw, "market_event_id": raw.get("market_event_id", event.id),
                                                 "events": events})


def decision_move(sub: Subentity, value: float) -> float | None:
    """For a released decision: the difference from the current posterior mean in native units, or
    None for a hold.
    # DECISION: a release "differs" from the posterior mean when the gap is more than half a
    # standardized unit (the threshold DecisionProfile uses to tell a move from a hold); smaller gaps
    # are the model's own drift between meetings, and the release is an observation."""
    from axelrod_wm.model.distributions import from_link

    mean = float(sub.posterior.mean())
    unit = abs(float(from_link(sub.anchor + sub.scale, sub.posterior.link)) - float(from_link(sub.anchor, sub.posterior.link)))
    gap = float(value) - mean
    return gap if abs(gap) > 0.5 * unit else None


@register("translator", "data_feed")
class DataFeedTranslator(MarketEventTranslator):
    """Maps each key in MarketEvent.data to a concrete observe_value op, except for decision
    variables: a released decision that differs from the current posterior mean becomes a
    change_value (mode absolute, the difference), while a hold stays an observe_value (§7.4)."""

    def __init__(self, config: Any = None, series_map: str | Path | dict | None = None) -> None:
        self.config = config
        if isinstance(series_map, dict):
            self.series_map = dict(series_map)
        else:
            p = Path(series_map) if series_map is not None else EXAMPLES_DIR / "worlds" / "economy" / "series_map.yaml"
            self.series_map = (yaml.safe_load(p.read_text()) or {}).get("series", {}) if p.exists() else {}

    def translate(self, event: MarketEvent, ctx: TranslationContext) -> TranslationResult:
        ops = []
        for key in sorted(event.data):
            sid = key if key in ctx.wm.graph.subentities else self.series_map.get(key)
            if sid is None or sid not in ctx.wm.graph.subentities:
                ctx.emit("translate.missing", market_event_id=event.id, key=key)
                continue
            value = float(event.data[key])
            move = decision_move(ctx.wm.graph.subentities[sid], value) if sid in ctx.wm.decision_variables else None
            if move is not None:
                ops.append({"op": "change_value", "target": {"kind": "concrete", "subentity_id": sid},
                            "delta": move, "mode": "absolute", "persistence": "step",
                            "at": event.occurred_at.isoformat()})
            else:
                ops.append({"op": "observe_value", "target": {"kind": "concrete", "subentity_id": sid},
                            "value": value, "observed_at": event.occurred_at.isoformat()})
        if not ops:
            return TranslationResult(market_event_id=event.id, events=[], rationale="no known series")
        ev = GraphUpdateEvent.model_validate({
            "id": f"GUE-{event.id}", "kind": "real", "event_type": event.event_type or "data_release",
            "occurred_at": event.occurred_at.isoformat(), "recorded_at": event.published_at.isoformat(), "ops": ops,
            "evidence": [Evidence(id=f"EV-{event.id}", source_type=SourceType.DATA, source_ref=event.source,
                                  excerpt=event.headline, observed_at=event.occurred_at, strength=1.0,
                                  market_event_id=event.id).model_dump(mode="json")],
            "market_event_id": event.id, "produced_by": "data_feed", "confidence": 1.0,
            "tags": list(event.tags), "mentions": list(event.mentions)})
        return TranslationResult(market_event_id=event.id, events=[ev], rationale=f"{len(ops)} series")


class TemplateRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subjects: list[dict[str, Any]] = []             # {pattern, subentity, invert?}: invert for a value quoted the other way
    verbs: list[dict[str, Any]] = []
    timeframes: list[dict[str, Any]] = []


@register("translator", "template")
class TemplateTranslator(MarketEventTranslator):
    """Regex rules from the world's templates.yaml (world_model/examples/worlds/<world>/). Handles typed theses ("what if oil
    doubles") and is a fallback when no fixture exists."""

    def __init__(self, config: Any = None, templates: str | Path | None = None) -> None:
        self.config = config
        p = Path(templates) if templates is not None else EXAMPLES_DIR / "worlds" / "economy" / "templates.yaml"
        self.rules = TemplateRules.model_validate(yaml.safe_load(p.read_text()) or {}) if p.exists() else TemplateRules()

    def parse(self, text: str, now: datetime) -> tuple[list[dict], list[tuple[int, int, int]]]:
        ops: list[dict] = []
        spans: list[tuple[int, int, int]] = []
        low = text.lower()
        days = 0
        for tf in self.rules.timeframes:
            if re.search(tf["pattern"], low):
                days = int(tf["days"])
                break
        for subj in self.rules.subjects:
            for m in re.finditer(r"\b(?:" + subj["pattern"] + r")\b", low):
                rest = low[m.end(): m.end() + 60]
                for verb in self.rules.verbs:
                    vm = re.match(r"\s*(?:" + verb["pattern"] + r")", rest)
                    if vm is None:
                        continue
                    delta = verb.get("delta")
                    num = vm.groupdict().get("num")
                    unit = (vm.groupdict().get("unit") or "").strip()
                    mode = verb.get("mode", "relative")
                    if num is not None:
                        x = float(num)
                        sign = float(verb.get("sign", 1.0))
                        if unit in ("bp", "basis points"):
                            delta, mode = sign * x / 100.0, "absolute"
                        elif unit in ("%", "percent"):
                            delta, mode = sign * x / 100.0, "relative" if verb.get("mode") != "absolute" else "absolute"
                        elif unit in ("sd", "standard deviations"):
                            delta, mode = sign * x, "standardized"
                        else:
                            delta, mode = sign * x, "absolute"
                    if delta is None:
                        continue
                    if subj.get("invert"):
                        # the subject is the value's reciprocal ("the yen" for USD/JPY): a 5% rise in the yen is a
                        # 4.8% fall in dollar-yen; an absolute or standardized move just changes sign
                        delta = 1.0 / (1.0 + float(delta)) - 1.0 if mode == "relative" else -float(delta)
                    at = now + timedelta(days=days)
                    ops.append({"op": "change_value", "target": {"kind": "concrete", "subentity_id": subj["subentity"]},
                                "delta": float(delta), "mode": mode, "persistence": "step", "at": at.isoformat()})
                    spans.append((m.start(), m.end() + vm.end(), len(ops) - 1))
                    break
                if ops and spans[-1][2] == len(ops) - 1 and spans[-1][0] == m.start():
                    break
        return ops, spans

    def translate(self, event: MarketEvent, ctx: TranslationContext) -> TranslationResult:
        text = f"{event.headline} {event.body}".strip()
        ops, spans = self.parse(text, event.occurred_at)
        if not ops:
            ctx.emit("translate.missing", market_event_id=event.id)
            return TranslationResult(market_event_id=event.id, events=[], rationale="no template matched")
        ev = GraphUpdateEvent.model_validate({
            "id": f"GUE-{event.id}", "kind": "real", "event_type": event.event_type,
            "occurred_at": event.occurred_at.isoformat(), "recorded_at": event.published_at.isoformat(), "ops": ops,
            "market_event_id": event.id, "produced_by": "template", "confidence": 0.6,
            "tags": list(event.tags), "mentions": list(event.mentions)})
        return TranslationResult(market_event_id=event.id, events=[ev], rationale="template match", spans=spans)


class LLMClient(Protocol):
    def complete(self, prompt: str, schema: dict) -> str: ...


class LLMNotConfigured(RuntimeError):
    pass


@register("translator", "llm")
class LLMTranslator(MarketEventTranslator):
    """Stub: builds the prompt and calls a provider-agnostic LLMClient. Not a default; it raises a
    clear error if selected without a configured client."""

    def __init__(self, config: Any = None, client: LLMClient | None = None) -> None:
        self.config = config
        self.client = client

    def build_prompt(self, event: MarketEvent, ctx: TranslationContext) -> str:
        schema = TranslationResult.model_json_schema()
        vocab = {k: v.parent for k, v in sorted(ctx.attribute_vocabulary().kinds.items())}
        obj = ctx.taxonomy_outline(TaxonomyKind.OBJECT, 2)
        rel = ctx.taxonomy_outline(TaxonomyKind.INTERACTION, 2)
        patterns = [{"id": p.id, "name": p.name,
                     "relations": [f"{r.source_role}.{r.source_attr} -> {r.target_role}.{r.target_attr} ({r.label})"
                                   for r in p.relations]} for p in ctx.admitted_patterns()]
        entities = [{"id": e.id, "name": e.name, "aliases": e.aliases} for _, e in sorted(ctx.wm.graph.entities.items())]
        return "\n\n".join([
            "Translate the market event into graph update events. Use abstract targets when unsure, and name "
            "an interaction generalization or a pattern relation when you cannot name the exact edge.",
            f"Market event:\n{event.model_dump_json(indent=2)}",
            f"JSON schema of the answer:\n{json.dumps(schema)}",
            f"Attribute vocabulary (kind -> parent):\n{json.dumps(vocab)}",
            f"Object taxonomy (top two levels):\n{json.dumps(obj)}",
            f"Interaction taxonomy (top two levels):\n{json.dumps(rel)}",
            f"Admitted patterns:\n{json.dumps(patterns)}",
            f"Entities:\n{json.dumps(entities)}",
        ])

    def translate(self, event: MarketEvent, ctx: TranslationContext) -> TranslationResult:
        if self.client is None:
            raise LLMNotConfigured("the llm translator needs an LLMClient (complete(prompt, schema) -> str); "
                                   "none is configured")
        prompt = self.build_prompt(event, ctx)
        raw = json.loads(self.client.complete(prompt, TranslationResult.model_json_schema()))
        events = [fill_event(e, event, "llm", i) for i, e in enumerate(raw.get("events", []))]
        return TranslationResult.model_validate({**raw, "market_event_id": event.id, "events": events})
