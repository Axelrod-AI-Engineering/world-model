"""The unified world model and its compartments (Oct 19; world_model/docs/archive/architecture-plan.md §4, D-20): `/v1/erid`.

**erid** is the unified world model: the whole graph, served beside the per-client `/v1/world-models/{id}`. It is the
main engine's world: a deployment runs its fullest scenario there (`sally_demo` today), so nothing new is loaded.

A **compartment** is a client's view of it, defined the way a focused world is (engine/focus.py): the covered
companies in scope, every player upstream of their values, and one link downstream. Each scenario whose
`focus.base` is the unified scenario is a compartment, named by the scenario id (`sally_focus`). A compartment
narrows the live graph, so what the unified model learns through review reaches every compartment it belongs to.

Who reads what:

- **The whole graph** is for internal staff only: a principal of an internal organization (`WORLD_MODEL_INTERNAL_ORGS`,
  comma-separated; default: the organization that owns the main engine's world model).
- **A compartment** is read by an internal organization, or by the organization it is assigned to
  (`WORLD_MODEL_COMPARTMENTS`: `compartment=org` entries). To anyone else it does not exist (404).
- Scopes are the per-world-model ones (`world_model:read`).
- **A login** whose scenario is a focus over the main engine's scenario is a compartment too (Oct 25): it is served by
  `api/viewstate.py`, a view onto the main engine that reads, forecasts, and asks theses on `narrow` and `narrow_ltm`
  below. Its compartment is owned by its organization, so `discover` and `/v1/erid` list it like any other.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from axelrod_wm.clients import find_scenario, scenario_dirs
from axelrod_wm.engine.focus import FocusSpec, focus_result


@dataclass(frozen=True)
class Compartment:
    id: str
    title: str
    spec: FocusSpec


def _read(path: Path, unified: str) -> Compartment | None:
    """The compartment a scenario.yaml defines on the unified scenario, or None (not a focus, or on another base)."""
    raw = yaml.safe_load(path.read_text()) or {}
    focus = raw.get("focus")
    if not focus or focus.get("base") != unified:
        return None
    sid = raw.get("id") or path.parent.name
    return Compartment(id=sid, title=str(raw.get("title") or sid), spec=FocusSpec.model_validate(focus))


def discover(unified: str) -> dict[str, Compartment]:
    """Every scenario focused on the unified scenario, by id."""
    out = {}
    for path in (p for d in scenario_dirs() for p in sorted(d.glob("*/scenario.yaml"))):
        comp = _read(path, unified)
        if comp is not None:
            out.setdefault(comp.id, comp)
    return out


def compartment_of(scenario: str, unified: str) -> Compartment | None:
    """The compartment a login's scenario is: a focus whose base is the unified (main engine's) scenario; None when the
    scenario is anything else, or is not on the client roots."""
    folder = find_scenario(scenario)
    return None if folder is None else _read(folder / "scenario.yaml", unified)


def _entries(var: str) -> dict[str, str]:
    out = {}
    for entry in (e.strip() for e in os.environ.get(var, "").split(",")):
        if not entry:
            continue
        name, sep, org = (x.strip() for x in entry.partition("="))
        if not sep or not name or not org:
            raise RuntimeError(f"{var} entries are compartment=org")
        out[name] = org
    return out


def internal_orgs(default: str) -> frozenset[str]:
    raw = [x.strip() for x in os.environ.get("WORLD_MODEL_INTERNAL_ORGS", "").split(",") if x.strip()]
    return frozenset(raw or [default])


def owners() -> dict[str, str]:
    """WORLD_MODEL_COMPARTMENTS: the organization each compartment is assigned to."""
    return _entries("WORLD_MODEL_COMPARTMENTS")


def _refs(x: Any) -> list[str]:
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        return [s for v in x.values() for s in _refs(v)]
    if isinstance(x, list | tuple | set):
        return [s for v in x for s in _refs(v)]
    return []


def narrow(wm: Any, comp: Compartment) -> Any:
    """The working memory narrowed to the compartment (a shallow copy: nothing is changed).

    The graph keeps the compartment's entities, values, links, and what is whole inside it. What else the memory holds
    is cut to match: hypotheses, pending refinements and reviewer judgments that name anything removed are dropped; the
    link channels, activity, and fold sums keep only the compartment's links; the forecast layer, the day's episode
    buffer, and the queues start empty (a compartment's forecasts are its own: api/viewstate.py)."""
    from axelrod_wm.memory.working import ForecastLayer
    from axelrod_wm.model.interaction import base_interaction_id

    fr = focus_result(comp.spec)
    g = wm.graph
    dropped = set(fr.dropped_ids())
    ents = {k: v for k, v in g.entities.items() if k in fr.entities}
    subs = {k: v for k, v in g.subentities.items() if v.entity_id in ents and fr.keeps_value(k)}
    links = {k: i for k, i in g.interactions.items() if k not in dropped and i.source_id in subs
             and i.target_id in subs}

    def whole(obj: Any) -> bool:
        """Every attribute and relationship the object names is in the compartment."""
        names = _refs(obj.model_dump())
        return all(n in subs for n in names if n in g.subentities) and \
            all(n in links for n in names if n in g.interactions)

    def owned(d: dict) -> dict:
        return {k: v for k, v in d.items() if v.entity_id in ents and whole(v)}

    def mine(channel: str) -> bool:
        return base_interaction_id(channel) in links

    def clean(d: dict) -> dict:
        return {k: v for k, v in d.items() if not fr.leaks(v.model_dump(mode="json"))}

    graph = g.model_copy(update={
        "entities": ents, "subentities": subs, "interactions": links,
        "instances": {k: v for k, v in g.instances.items() if k not in dropped and whole(v)
                      and all(e in ents for e in v.bindings.values())},
        "super_interactions": {},
        "entity_link_labels": {k: v for k, v in g.entity_link_labels.items() if all(p in ents for p in k.split("->"))},
        "paths": owned(g.paths), "compositions": owned(g.compositions), "identities": owned(g.identities),
        "stock_flows": owned(g.stock_flows), "matrices": owned(g.matrices),
    })
    return wm.model_copy(update={
        "graph": graph,
        "hypotheses": clean({k: h for k, h in wm.hypotheses.items() if all(e in ents for e in h.subject_entity_ids)}),
        "pending_refinements": clean(wm.pending_refinements),
        "ripple_judgments": {k: r for k, r in wm.ripple_judgments.items() if r.subentity_id in subs},
        "forecast_layer": ForecastLayer(),
        "channels": {k: c for k, c in wm.channels.items() if mine(k)},
        "channel_phi": {k: v for k, v in wm.channel_phi.items() if mine(k.rsplit("|", 1)[0])},
        "activity_log": {k: a for k, a in wm.activity_log.items() if mine(a.channel_id)},
        "fold_accumulators": {k: v for k, v in wm.fold_accumulators.items() if mine(k)},
        "episode_buffer": [], "source_cursors": {}, "late_queue": {}, "missing_relation_log": {},
        "pending_episode_tags": [],
    })


def narrow_ltm(ltm: Any, comp: Compartment, wm: Any) -> Any:
    """The long-term memory narrowed to the compartment, given its narrowed working memory `wm` (a shallow copy).

    Taxonomies list only the compartment's entities, superentities, and links; superentity patterns keep only those
    that name nothing removed; entity memories and frontier entries keep only the compartment's values. Prior episodes
    and stored explanations are dropped: they name what the whole model saw, and a compartment makes its own."""
    from axelrod_wm.memory.frontier import CorrelationFrontier
    from axelrod_wm.memory.long_term import PriorStates

    fr = focus_result(comp.spec)
    g = wm.graph
    patterns = {k: p for k, p in ltm.object_generalizations.patterns.items() if not fr.leaks(p.model_dump(mode="json"))}

    def taxonomy(tax: Any, keep: set[str]) -> Any:
        nodes = {k: n.model_copy(update={"instance_ids": [i for i in n.instance_ids if i in keep]})
                 for k, n in tax.nodes.items()}
        return tax.model_copy(update={"nodes": nodes})

    def memory(m: Any) -> Any:
        """An entity's memory restricted to the compartment's values (a profile's buckets name the values they read)."""
        def inside(sid: str) -> bool:
            return sid in g.subentities

        entries = [e.model_copy(update={"subentity_summaries": {k: v for k, v in e.subentity_summaries.items() if inside(k)},
                                        "z": {k: v for k, v in e.z.items() if inside(k)}}) for e in m.entries]
        decisions = [d.model_copy(update={"context": {k: v for k, v in d.context.items() if inside(k)}})
                     for d in m.decisions if inside(d.subentity_id)]
        profiles = {k: v.model_copy(update={"by_context": {b: n for b, n in v.by_context.items()
                                                           if inside(re.split("[<>]", b)[0])}})
                    for k, v in m.profiles.items() if inside(k)}
        return m.model_copy(update={"entries": entries, "decisions": decisions, "profiles": profiles})

    og, ig = ltm.object_generalizations, ltm.interaction_generalizations
    return ltm.model_copy(update={
        "object_generalizations": og.model_copy(update={
            "taxonomy": taxonomy(og.taxonomy, set(g.entities) | set(patterns)), "patterns": patterns,
            "super_interaction_labels": {k: v for k, v in og.super_interaction_labels.items()
                                         if all(p in patterns for p in k.split("->"))}}),
        "interaction_generalizations": ig.model_copy(update={"taxonomy": taxonomy(ig.taxonomy, set(g.interactions))}),
        "entity_memories": {k: memory(m) for k, m in ltm.entity_memories.items() if k in g.entities},
        "correlation_frontier": CorrelationFrontier(entries={
            k: c for k, c in ltm.correlation_frontier.entries.items()
            if c.earlier_id in g.subentities and c.later_id in g.subentities}),
        "prior_states": PriorStates(),
    })
