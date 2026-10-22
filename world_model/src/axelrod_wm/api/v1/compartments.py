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
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import yaml

from axelrod_wm.clients import scenario_dirs
from axelrod_wm.engine.focus import FocusSpec, focus_result


@dataclass(frozen=True)
class Compartment:
    id: str
    title: str
    spec: FocusSpec


def discover(unified: str) -> dict[str, Compartment]:
    """Every scenario focused on the unified scenario, by id."""
    out = {}
    for path in (p for d in scenario_dirs() for p in sorted(d.glob("*/scenario.yaml"))):
        raw = yaml.safe_load(path.read_text()) or {}
        focus = raw.get("focus")
        if focus and focus.get("base") == unified:
            sid = raw.get("id") or path.parent.name
            out.setdefault(sid, Compartment(id=sid, title=str(raw.get("title") or sid),
                                            spec=FocusSpec.model_validate(focus)))
    return out


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
    """The working memory with its graph narrowed to the compartment (a shallow copy: nothing is changed)."""
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

    graph = g.model_copy(update={
        "entities": ents, "subentities": subs, "interactions": links,
        "instances": {k: v for k, v in g.instances.items() if k not in dropped and whole(v)
                      and all(e in ents for e in v.bindings.values())},
        "super_interactions": {},
        "entity_link_labels": {k: v for k, v in g.entity_link_labels.items() if all(p in ents for p in k.split("->"))},
        "paths": owned(g.paths), "compositions": owned(g.compositions), "identities": owned(g.identities),
        "stock_flows": owned(g.stock_flows), "matrices": owned(g.matrices),
    })
    return wm.model_copy(update={"graph": graph})
