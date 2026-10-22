"""Entity resolution for fuzzy targets (§7.5)."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from axelrod_wm.engine.registry import register, registry

if TYPE_CHECKING:
    from axelrod_wm.model.graph import CausalGraph

_word = re.compile(r"[a-z0-9]+")


def words(text: str) -> set[str]:
    return set(_word.findall(text.lower()))


def text_similarity(mention: str | None, strings: list[str]) -> float:
    """Best of SequenceMatcher ratio + 0.3 * word-set Jaccard over the strings, capped at 1."""
    if not mention:
        return 0.0
    m = mention.lower().strip()
    mw = words(m)
    best = 0.0
    for s in strings:
        if not s:
            continue
        sl = s.lower().strip()
        ratio = SequenceMatcher(None, m, sl).ratio()
        sw = words(sl)
        jac = len(mw & sw) / len(mw | sw) if (mw or sw) else 0.0
        best = max(best, min(1.0, ratio + 0.3 * jac))
    return best


def entity_strings(entity_id: str, graph: CausalGraph, extra_subs: list[Any] | None = None) -> list[str]:
    ent = graph.entities.get(entity_id)
    if ent is None:
        return []
    out = [ent.name, *ent.aliases]
    for sid in ent.subentity_ids:
        sub = graph.subentities.get(sid)
        if sub is not None:
            out.extend([sub.name, *sub.aliases])
    for sub in extra_subs or []:
        if getattr(sub, "entity_id", None) == entity_id:
            out.extend([sub.name, *getattr(sub, "aliases", [])])
    return out


def constraint_fraction(entity_id: str, constraints: dict[str, str], graph: CausalGraph,
                        extra_subs: list[Any] | None = None) -> float:
    if not constraints:
        return 0.0
    ent = graph.entities.get(entity_id)
    if ent is None:
        return 0.0
    feats = [dict(ent.features)]
    for sid in ent.subentity_ids:
        sub = graph.subentities.get(sid)
        if sub is not None:
            feats.append(dict(sub.features))
    for sub in extra_subs or []:
        if getattr(sub, "entity_id", None) == entity_id:
            feats.append(dict(getattr(sub, "features", {})))
    met = sum(1 for k, v in constraints.items() if any(f.get(k) == v for f in feats))
    return met / len(constraints)


class EntityResolver(ABC):
    @abstractmethod
    def resolve(self, mention: str | None, constraints: dict[str, str],
                candidate_ids: list[str], graph: CausalGraph) -> list[tuple[str, float]]: ...


registry("entity_resolver", EntityResolver)


@register("entity_resolver", "alias_fuzzy")
class AliasFuzzyResolver(EntityResolver):
    """Score = best SequenceMatcher ratio between the mention and the names and aliases of the
    entity and its subentities, + 0.3 x the Jaccard overlap of their word sets, + 0.2 x the
    fraction of constraints matched by the entity's or its subentities' features, capped at 1."""

    def __init__(self, config: Any = None) -> None:
        self.config = config
        self.extra_subs: list[Any] = []     # subentities created earlier in the same event

    def score(self, entity_id: str, mention: str | None, constraints: dict[str, str], graph: CausalGraph) -> float:
        sim = 0.0
        if mention:
            m = mention.lower().strip()
            mw = words(m)
            for s in entity_strings(entity_id, graph, self.extra_subs):
                sl = s.lower().strip()
                ratio = SequenceMatcher(None, m, sl).ratio()
                sw = words(sl)
                jac = len(mw & sw) / len(mw | sw) if (mw or sw) else 0.0
                sim = max(sim, ratio + 0.3 * jac)
        return min(1.0, sim + 0.2 * constraint_fraction(entity_id, constraints, graph, self.extra_subs))

    def resolve(self, mention: str | None, constraints: dict[str, str],
                candidate_ids: list[str], graph: CausalGraph) -> list[tuple[str, float]]:
        scored = [(eid, self.score(eid, mention, constraints, graph)) for eid in candidate_ids if eid in graph.entities]
        return sorted(scored, key=lambda x: (-x[1], x[0]))
