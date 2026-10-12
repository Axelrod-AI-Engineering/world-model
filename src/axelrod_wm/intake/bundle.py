"""Import bundles (Oct 11): research a collection agent has already read and categorized, ready to fold in.

A bundle is what an upstream agent hands the world model after scraping and sorting sources: dated items, each with
its source, a summary in the agent's words, the entities it is about, a category, and **signals**: the specific
claims the item makes about the model, each tied to the phrase that makes it. The world model does not trust them:
every item becomes a market event on its own date, the `structured` translator turns its signals into a proposed
graph update, and a person reviews it like any other.

Signals name the model's own ids. A signal whose ends are not in the graph is dropped (and reported), so a bundle
written for a richer model still imports into a smaller one.

    {"format": "axelrod.import/v1", "title": ..., "collected_by": ..., "collected_at": ..., "items": [
       {"id": "EM-001", "published_at": "2026-09-11T06:00:00Z", "source": "...", "source_type": "broker_research",
        "kind": "analyst", "headline": "...", "summary": "...", "entities": ["boj"], "tickers": ["8766 JP"],
        "category": "rates", "stance": "hawkish", "relevance": 0.9, "confidence": 0.8,
        "signals": [{"type": "observe", "value_of": "boj.policy_rate", "value": 1.25, "quote": "..."}]}]}
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from axelrod_wm.engine.registry import register
from axelrod_wm.events.graph_update import GraphUpdateEvent
from axelrod_wm.events.market import MarketEvent, MarketEventChannel, MarketEventKind
from axelrod_wm.intake.translators import (
    MarketEventTranslator,
    TranslationContext,
    TranslationResult,
    fill_event,
)

FORMAT = "axelrod.import/v1"


class _S(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str = ""                    # the phrase of the summary that makes this claim (highlighted in review)
    note: str = ""                     # the agent's reason, shown beside the change


class Observe(_S):
    """A reported level: a value is now this, in its native unit."""

    type: Literal["observe"]
    value_of: str
    value: float


class Move(_S):
    """A change to a value: relative (0.1 = +10%), absolute (native units), or standardized (sd)."""

    type: Literal["move"]
    value_of: str
    delta: float
    mode: Literal["relative", "absolute", "standardized"] = "absolute"


class Link(_S):
    """A causal link the item states: source drives target, with a sign, a size (target sd per source sd), and
    timing (mean days until it starts, builds, and how long it lasts; no duration is permanent)."""

    type: Literal["link"]
    source: str
    target: str
    label: str
    effect: float
    delay_days: float = 7.0
    lag_days: float = 30.0
    duration_days: float | None = None


class Support(_S):
    """Evidence for (or against) a link already in the model, named by its two ends."""

    type: Literal["support", "contradict"]
    source: str
    target: str
    strength: float = 0.5


Signal = Annotated[Observe | Move | Link | Support, Field(discriminator="type")]


class ImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    published_at: datetime
    occurred_at: datetime | None = None
    source: str
    source_type: Literal["broker_research", "expert_call", "news", "central_bank", "data", "filing",
                         "client_model", "other"] = "news"
    kind: Literal["news", "data", "analyst", "filing"] = "news"
    headline: str
    summary: str = ""
    url: str | None = None
    entities: list[str] = []           # the model's entity ids the agent tagged
    tickers: list[str] = []
    category: str = ""                 # the agent's topic, e.g. "rates", "fx", "earnings"
    stance: str = ""                   # e.g. "hawkish", "positive", "estimates down"
    relevance: float = Field(0.5, ge=0, le=1)     # to the book, as the agent judged it
    confidence: float = Field(0.7, ge=0, le=1)    # in its own reading
    tags: list[str] = []
    signals: list[Signal] = []


class ImportBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["axelrod.import/v1"] = FORMAT
    title: str = "Imported research"
    collected_by: str = "research agent"
    collected_at: datetime | None = None
    description: str = ""
    synthetic: bool = False            # made up for a demo or a test (the review shows a "synthetic" badge)
    items: list[ImportItem]


# ---------------------------------------------------------------------------------------------------
# signals -> operations
# ---------------------------------------------------------------------------------------------------
def _find_link(graph: Any, src: str, dst: str) -> str | None:
    for i in graph.active_interactions():
        if i.source_id == src and i.target_id == dst:
            return i.id
    return None


def signal_ops(sig: Any, graph: Any, at: datetime) -> tuple[list[dict], str | None]:
    """The operations a signal stands for, or ([], why) when its ends are not in the graph."""
    from axelrod_wm.sim.examples.catalog import dyn, link, move, observe, reweight

    subs = graph.subentities
    if isinstance(sig, Observe):
        if sig.value_of not in subs:
            return [], f"no value {sig.value_of}"
        return [observe(sig.value_of, sig.value, at)], None
    if isinstance(sig, Move):
        if sig.value_of not in subs:
            return [], f"no value {sig.value_of}"
        return [move(sig.value_of, sig.delta, at, mode=sig.mode)], None
    if isinstance(sig, Link):
        missing = [x for x in (sig.source, sig.target) if x not in subs]
        if missing:
            return [], f"no value {missing[0]}"
        if _find_link(graph, sig.source, sig.target):
            # the link is already there: the item is evidence for it, not a new link
            return [reweight(_find_link(graph, sig.source, sig.target), True, 0.5)], None
        polarity = 1 if sig.effect >= 0 else -1
        return [link(sig.source, sig.target, sig.label, polarity,
                     dyn(sig.effect, sig.delay_days, sig.lag_days, sig.duration_days))], None
    iid = _find_link(graph, sig.source, sig.target)
    if iid is None:
        return [], f"no link {sig.source} -> {sig.target}"
    return [reweight(iid, sig.type == "support", sig.strength)], None


def item_text(item: ImportItem) -> str:
    """The text a review's highlights index into: the headline and the summary."""
    return f"{item.headline}\n{item.summary}" if item.summary else item.headline


def market_event_of(item: ImportItem, event_id: str, synthetic: bool = False) -> MarketEvent:
    kind = MarketEventKind(item.kind)
    channel = MarketEventChannel.DATA_FEED if item.kind == "data" else MarketEventChannel.SCRAPER
    return MarketEvent(id=event_id, kind=kind, channel=channel, source=item.source, headline=item.headline,
                       body=item.summary, published_at=item.published_at,
                       occurred_at=item.occurred_at or item.published_at, mentions=list(item.entities),
                       tags=[*item.tags, *([item.category] if item.category else [])], url=item.url, synthetic=synthetic)


def translate_item(item: ImportItem, event: MarketEvent, graph: Any) -> tuple[TranslationResult, list[str]]:
    """The proposed graph update for one imported item, and the signals it had to drop."""
    ops: list[dict] = []
    owners: list[int] = []             # signal index of each op
    dropped: list[str] = []
    for k, sig in enumerate(item.signals):
        got, why = signal_ops(sig, graph, event.published_at)
        if why:
            dropped.append(f"{sig.type} ({why})")
        ops += got
        owners += [k] * len(got)
    if not ops:
        why = "; ".join(dropped) if dropped else "no signals"
        return TranslationResult(market_event_id=event.id, events=[], rationale=f"nothing to change: {why}"), dropped
    raw = {"kind": "real", "event_type": item.category or None, "confidence": item.confidence, "ops": ops,
           "evidence": [{"id": f"EV-{event.id}", "source_type": "data" if item.kind == "data" else "news",
                         "excerpt": item.headline, "observed_at": event.published_at.isoformat(),
                         "strength": round(0.4 + 0.4 * item.relevance, 2), "market_event_id": event.id}]}
    ev = GraphUpdateEvent.model_validate(fill_event(raw, event, "structured"))
    text = item_text(item)
    spans = []
    for i, k in enumerate(owners):
        q = item.signals[k].quote
        at = text.find(q) if q else -1
        if at >= 0:
            spans.append((at, at + len(q), i))
    notes = [s.note for s in item.signals if s.note]
    rationale = f"{item.source} ({item.source_type.replace('_', ' ')})" + (
        f", categorized as {item.category}" if item.category else "") + (
        f": {' '.join(notes)}" if notes else "")
    return TranslationResult(market_event_id=event.id, events=[ev], rationale=rationale, spans=spans), dropped


@register("translator", "structured")
class StructuredTranslator(MarketEventTranslator):
    """Imported items: the signals the collection agent attached become the proposed update."""

    def __init__(self, config: Any = None, runner: Any = None) -> None:
        self.config = config
        self.runner = runner

    def translate(self, event: MarketEvent, ctx: TranslationContext) -> TranslationResult:
        item = getattr(self.runner, "imported", {}).get(event.id)
        if item is None:
            return TranslationResult(market_event_id=event.id, events=[], rationale="not an imported item")
        result, _ = translate_item(item, event, ctx.wm.graph)
        return result


__all__ = ["FORMAT", "ImportBundle", "ImportItem", "Link", "Move", "Observe", "StructuredTranslator", "Support",
           "item_text", "market_event_of", "signal_ops", "translate_item"]
