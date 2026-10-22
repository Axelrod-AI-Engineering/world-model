"""The example catalogs (Oct 8 restructure): what an example is, and the helpers that write their operations.

An **example** is one feature of the framework, shown by one or more sample articles. Its steps run in order; the
last step (or the proposal the steps raise, for features long-term memory proposes on its own) is the **focus**:
it stops at the human review. Examples form one chain: running example n first plays examples 1 to n - 1, and
running an earlier example rewinds to it.

A **library event** is a further article of the same kind ("more like this"). It runs on the current state, after
the example it needs, and goes through the same staged review; it does not move the chain.

Every article is synthetic. Real company and agency names make the graph concrete, and nothing an article says is
a claim about them; storylines that would read as claims use illustrative firms.
"""

from __future__ import annotations

from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict

from axelrod_wm.model.distributions import Beta, Gaussian, prior_from_native
from axelrod_wm.model.interaction import EdgeDynamics
from axelrod_wm.model.temporal import KernelSpec, gamma_from_mean

Memory = Literal["working", "long_term", "review", "inference", "intake"]


_ARTICLE_TEXT: dict[str, str] | None = None


def full_text_of(headline: str) -> str:
    """A sample article's whole text, by headline (articles.json beside this file; synthetic, written for the demos).
    Empty when none was written."""
    global _ARTICLE_TEXT
    if _ARTICLE_TEXT is None:
        import json
        from pathlib import Path

        path = Path(__file__).with_name("articles.json")
        _ARTICLE_TEXT = json.loads(path.read_text()) if path.exists() else {}
    return _ARTICLE_TEXT.get(headline, "")


class Article(BaseModel):
    """A sample article: what a source published, and which phrases ask for which operations."""

    model_config = ConfigDict(extra="forbid")

    headline: str
    body: str = ""
    source: str = "Synthetic newswire"
    kind: Literal["news", "data", "analyst", "filing"] = "news"
    mentions: list[str] = []
    event_type: str | None = None
    quotes: list[tuple[str, list[int]]] = []       # a phrase of the article -> the operations it asks for
    rationale: str = ""                            # why the translation reads it this way


class Step(BaseModel):
    """One article of an example, and the operations it stands for (a builder in the catalog's OPS)."""

    model_config = ConfigDict(extra="forbid")

    article: Article
    ops: str                                       # key into the catalog's builders
    days: int = 1                                  # days after the previous step (or the previous example)


class Example(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    n: int
    title: str
    memory: Memory                                 # the memory (or stage) the feature belongs to
    stage: str                                     # the flowchart stage it isolates (a phase id)
    feature: str                                   # the feature, in a few words: groups the library's events
    isolates: str
    summary: str
    watch: list[str]
    kind: Literal["event", "edit", "thesis", "manual"] = "event"
    steps: list[Step] = []                         # for an event: the articles, in order; the last is the focus
    focus: Literal["last", "raised"] = "last"      # "raised": the focus is a proposal the steps raise
    raises: str | None = None                      # for focus "raised": the proposal kind to expect
    edit: str | None = None                        # for an edit: a key into the catalog's EDITS
    question: str | None = None                    # for a thesis
    manual: dict | None = None                     # for a manual addition: the form, prefilled (see manual_ops)


class LibraryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    feature: str
    title: str
    after: str                                     # the example it needs (the chain is run up to it first)
    step: Step | None = None
    edit: str | None = None
    question: str | None = None


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    name: str
    examples: list[Example]
    library: list[LibraryEvent] = []
    ops: dict[str, Callable[[Any, Any], list[dict]]] = {}     # builder(controller, at) -> op dicts
    edits: dict[str, Callable[[Any, str], Any]] = {}          # edit(controller, by) -> Proposal

    def example(self, key: str) -> Example:
        for e in self.examples:
            if key in (e.id, str(e.n)):
                return e
        raise KeyError(f"unknown example {key!r}")

    def index(self, key: str) -> int:
        return self.examples.index(self.example(key))

    def event(self, key: str) -> LibraryEvent:
        for e in self.library:
            if e.id == key:
                return e
        raise KeyError(f"unknown library event {key!r}")


# ---------------------------------------------------------------------------------------------------
# operation helpers
# ---------------------------------------------------------------------------------------------------
def prior(family: str, mean: float, scale: float) -> dict:
    return prior_from_native(family, mean, scale).model_dump(mode="json")


def dyn(effect: float, delay: float, lag: float, duration: float | None = None) -> dict:
    kernel = KernelSpec(delay=gamma_from_mean(delay), lag=gamma_from_mean(lag),
                        duration=gamma_from_mean(duration) if duration else None)
    return EdgeDynamics(effect=Gaussian(mu=effect, sigma=0.15), kernel=kernel).model_dump(mode="json")


FIRM = Beta(alpha=9.0, beta=1.0).model_dump(mode="json")      # a link the article states firmly


def concrete(sid: str) -> dict:
    return {"kind": "concrete", "subentity_id": sid}


def entity(eid: str, name: str, kind: str, tags: list[str], features: dict | None = None,
           aliases: list[str] | None = None) -> dict:
    return {"op": "add_entity", "temp_id": f"new:{eid}", "name": name, "kind": kind, "category_tags": tags,
            "features": features or {}, "aliases": aliases or []}


def value(eid: str, slug: str, name: str, attr: str, unit: str, family: str | None = None, mean: float | None = None,
          scale: float | None = None, aliases: list[str] | None = None, new_entity: bool = True,
          features: dict | None = None) -> dict:
    op = {"op": "add_subentity", "entity": f"new:{eid}" if new_entity else eid, "temp_id": f"new:{eid}.{slug}",
          "name": name, "attribute_kind": attr, "unit": unit, "aliases": aliases or [], "features": features or {}}
    if family is not None and mean is not None and scale is not None:
        op.update(prior=prior(family, mean, scale), scale=scale)
    return op


def link(src: str | dict, dst: str | dict, label: str, polarity: int, dynamics: dict | None = None) -> dict:
    op = {"op": "add_interaction", "source": concrete(src) if isinstance(src, str) else src,
          "target": concrete(dst) if isinstance(dst, str) else dst, "label": label, "polarity": polarity}
    if dynamics is not None:
        op.update(dynamics=dynamics, existence=FIRM)
    return op


def move(sid: str, delta: float, at: Any, mode: str = "relative") -> dict:
    return {"op": "change_value", "target": concrete(sid), "delta": delta, "mode": mode, "persistence": "step",
            "at": at.isoformat()}


def observe(sid: str, val: float, at: Any) -> dict:
    return {"op": "observe_value", "target": concrete(sid), "value": val, "observed_at": at.isoformat()}


def reweight(iid: str, supports: bool, strength: float = 0.5) -> dict:
    return {"op": "reweight_interaction", "interaction_id": iid, "supports": supports, "strength": strength}


def find_link(ctl: Any, src: str, dst: str) -> str | None:
    for i in ctl.engine.wm.graph.active_interactions():
        if i.source_id == src and i.target_id == dst:
            return i.id
    return None


__all__ = ["Article", "Catalog", "Example", "LibraryEvent", "Step", "concrete", "dyn", "entity", "find_link", "link",
           "move", "observe", "prior", "reweight", "value"]


# ---------------------------------------------------------------------------------------------------
# a backend user's own additions (Oct 9): the "Add from your own knowledge" form, as data
# ---------------------------------------------------------------------------------------------------
def manual_ops(spec: dict) -> list[dict]:
    """The operations a manual addition stands for. `spec`, as the form fills it:

    - entity (optional): {id, name, kind, tags, aliases, features}: a new entity;
    - values: [{slug, name, attribute_kind, unit, family, typical, spread, entity?}]: new values, on the new entity
      unless `entity` names an existing one; `typical` and `spread` (native units) set the prior;
    - interactions: [{source, target, label, polarity, effect, delay_days, lag_days}]: between existing values (their
      ids) or new ones ("new:<slug>"); `effect` is in standard units per standard unit.

    The reviewer's confidence (spec["confidence"]) goes on the event, not the ops."""
    ops: list[dict] = []
    ent = spec.get("entity") or None
    eid = ent["id"] if ent else None
    if ent:
        ops.append(entity(eid, ent["name"], ent.get("kind", "other"), list(ent.get("tags", [])), ent.get("features") or {},
                          list(ent.get("aliases", []))))
    owner: dict[str, str] = {}
    for v in spec.get("values", []):
        on = v.get("entity") or eid
        new_entity = bool(ent) and on == eid
        owner[v["slug"]] = on
        ops.append(value(on, v["slug"], v["name"], v["attribute_kind"], v.get("unit", "index"), v.get("family"),
                         float(v["typical"]) if v.get("typical") is not None else None,
                         float(v["spread"]) if v.get("spread") is not None else None,
                         aliases=list(v.get("aliases", [])), new_entity=new_entity))

    def ref(x: str) -> str:
        if x.startswith("new:") and x[4:] in owner:
            return f"new:{owner[x[4:]]}.{x[4:]}"
        return x

    for it in spec.get("interactions", []):
        ops.append(link(ref(it["source"]), ref(it["target"]), it.get("label", "affects"), int(it.get("polarity", 1)),
                        dyn(float(it.get("effect", 0.3)), float(it.get("delay_days", 14)), float(it.get("lag_days", 30)))))
    return ops


def manual_event(spec: dict, at: Any, event_id: str) -> Any:
    """A manual addition as a graph update event from a person: no article behind it, their confidence on it."""
    from axelrod_wm.events.graph_update import GraphUpdateEvent

    return GraphUpdateEvent.model_validate({
        "id": event_id, "kind": "real", "event_type": "manual_addition", "occurred_at": at.isoformat(),
        "recorded_at": at.isoformat(), "ops": manual_ops(spec), "produced_by": "human", "confidence": 1.0,
        "user_confidence": float(min(1.0, max(0.0, spec.get("confidence", 1.0)))),
        "mentions": [spec["entity"]["name"]] if spec.get("entity") else [],
        # the person's reason is the evidence: it is stored on what the addition writes, as an article's excerpt is
        "evidence": [{"id": f"EV-{event_id}", "source_type": "human", "excerpt": (spec.get("note") or "")[:500] or None,
                      "observed_at": at.isoformat(), "strength": 1.0}]})
