"""Recall relevant superentities and analogs (§8.4.3)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from axelrod_wm.core.superentity import SuperentityPattern, SuperentityStatus
from axelrod_wm.engine.interfaces import (
    AttentionPolicy,
    Recaller,
    RecallResult,
    ScoredEpisode,
    ScoredSuperentity,
)
from axelrod_wm.engine.registry import register
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.shared import ParsedEvent
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


@register("attention", "softmax_top_k")
class SoftmaxTopK(AttentionPolicy):
    """Keep the top k by score, softmax(score / temperature) over them, drop weights below
    min_attention. # DECISION: the softmax runs over the kept top k, so attention is relative
    among the candidates that survive (otherwise hundreds of episodes dilute every weight)."""

    def __init__(self, config: Any = None, temperature: float | None = None, min_attention: float | None = None) -> None:
        att = getattr(config, "attention", None)
        self.temperature = float(temperature if temperature is not None else getattr(att, "temperature", 0.5))
        self.min_attention = float(min_attention if min_attention is not None else getattr(att, "min_attention", 0.02))

    def select(self, scores: dict[str, float], top_k: int) -> dict[str, float]:
        if not scores or top_k <= 0:
            return {}
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
        mx = max(s for _, s in ranked)
        ex = [(k, math.exp((s - mx) / max(self.temperature, 1e-9))) for k, s in ranked]
        tot = sum(v for _, v in ex)
        out = {k: v / tot for k, v in ex}
        kept = {k: v for k, v in out.items() if v >= self.min_attention}
        tot = sum(kept.values())
        return {k: v / tot for k, v in sorted(kept.items(), key=lambda kv: (-kv[1], kv[0]))} if tot > 0 else {}


def pattern_signature(p: SuperentityPattern, ltm: LongTermMemory) -> set[str]:
    out: set[str] = set()
    for r in p.roles:
        if r.generalization_id in ltm.object_taxonomy.nodes:
            out.update(ltm.object_taxonomy.path_to_root(r.generalization_id))
    for rel in p.relations:
        gid = rel.interaction_generalization_id
        if gid and gid in ltm.interaction_taxonomy.nodes:
            out.update(ltm.interaction_taxonomy.path_to_root(gid))
    return out


def can_fill(entity_gen: str | None, pattern: SuperentityPattern, ltm: LongTermMemory) -> bool:
    if not entity_gen or entity_gen not in ltm.object_taxonomy.nodes:
        return False
    path = set(ltm.object_taxonomy.path_to_root(entity_gen))
    return any(r.generalization_id in path for r in pattern.roles)


def near_instance(pattern_id: str, wm: WorkingMemory, entity_ids: set[str]) -> str | None:
    """The instance of the pattern with the largest overlap with the given entities."""
    best = (0, None)
    for iid in sorted(wm.graph.instances):
        inst = wm.graph.instances[iid]
        if inst.pattern_id == pattern_id:
            n = len(wm.graph.members(iid) & entity_ids)
            if n > best[0]:
                best = (n, iid)
    return best[1]


def any_instance(pattern_id: str, wm: WorkingMemory) -> str | None:
    for iid in sorted(wm.graph.instances):
        if wm.graph.instances[iid].pattern_id == pattern_id:
            return iid
    return None


@register("recaller", "overlap_attention")
class OverlapAttentionRecaller(Recaller):
    def __init__(self, config: Any = None, attention: AttentionPolicy | None = None) -> None:
        self.config = config
        self.attention = attention or SoftmaxTopK(config)

    def _episode_scores(self, parsed: ParsedEvent, sig: set[str], ltm: LongTermMemory,
                        ctx: ProcessContext) -> tuple[dict[str, float], dict[str, list[str]]]:
        scores: dict[str, float] = {}
        shared: dict[str, list[str]] = {}
        tags = set(parsed.tags)
        for eid, ep in sorted(ltm.episodes.episodes.items()):
            age = max((ctx.now - ep.end).total_seconds() / 86400.0, 0.0)
            recency = 0.5 ** (age / 365.0)
            tag_score = len(tags & set(ep.tags)) / max(1, len(tags))
            etype = 1.0 if parsed.event_type and parsed.event_type in ep.event_types else 0.0
            keys = ltm.explanations.index_keys_of(ep.explanation_ids)
            expl = jaccard(sig, keys)
            j = jaccard(sig, set(ep.key_signature))
            scores[eid] = recency * (0.4 * j + 0.3 * tag_score + 0.3 * etype) * (1.0 + 0.5 * expl)
            shared[eid] = sorted(sig & set(ep.key_signature))
        return scores, shared

    def _pattern_scores(self, parsed: ParsedEvent, sig: set[str], wm: WorkingMemory, ltm: LongTermMemory,
                        ctx: ProcessContext) -> dict[str, float]:
        admitted = ltm.patterns.admitted()
        if not admitted:
            return {}
        max_support = max(max(p.support for p in admitted), 1e-9)
        touched = set(parsed.touched_entity_ids)
        dist = wm.graph.hop_distances(list(parsed.touched_subentity_ids)) if parsed.touched_subentity_ids else {}
        scores: dict[str, float] = {}
        for p in admitted:
            psig = pattern_signature(p, ltm)
            fill = any(can_fill(wm.graph.entities[e].generalization_id, p, ltm)
                       for e in touched if e in wm.graph.entities)
            if fill:
                prox = 1.0
            else:
                prox = 0.0
                for iid in sorted(wm.graph.instances):
                    inst = wm.graph.instances[iid]
                    if inst.pattern_id != p.id:
                        continue
                    hops = [dist[s] for s in wm.graph.member_subentities(iid) if s in dist]
                    if hops:
                        prox = max(prox, math.exp(-min(hops)))
            sup = math.log1p(max(p.support, 0.0)) / math.log1p(max_support) if max_support > 0 else 0.0
            scores[p.id] = 0.5 * jaccard(sig, psig) + 0.3 * prox + 0.2 * sup
        return scores

    def recall(self, parsed: ParsedEvent, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext) -> RecallResult:
        cfg = ctx.config
        sig = {k for k in parsed.signature if not k.startswith(("tag:", "etype:"))}
        p_scores = self._pattern_scores(parsed, sig, wm, ltm, ctx)
        e_scores, shared = self._episode_scores(parsed, sig, ltm, ctx)
        p_att = self.attention.select(p_scores, int(cfg.attention.top_k_superentities))
        e_att = self.attention.select(e_scores, int(cfg.attention.top_k_analogs))
        touched = set(parsed.touched_entity_ids)
        sups = [ScoredSuperentity(pattern_id=pid, instance_id=near_instance(pid, wm, touched) or any_instance(pid, wm),
                                  score=p_scores[pid], attention=a) for pid, a in p_att.items()]
        have = {s.pattern_id for s in sups}
        analogs = [ScoredEpisode(episode_id=eid, score=e_scores[eid], attention=a, shared_generalizations=shared[eid])
                   for eid, a in e_att.items()]
        for an in analogs:
            ep = ltm.episodes.episodes[an.episode_id]
            for pid in sorted(ep.active_pattern_ids):
                p = ltm.patterns.patterns.get(pid)
                if p is None or p.status != SuperentityStatus.ADMITTED or pid in have:
                    continue
                have.add(pid)
                sups.append(ScoredSuperentity(pattern_id=pid, instance_id=near_instance(pid, wm, touched) or any_instance(pid, wm),
                                              score=p_scores.get(pid, 0.0), attention=an.attention,
                                              via_episode=an.episode_id))
        result = RecallResult(superentities=sups, analogs=analogs)
        ctx.tracer.emit(Phase.RECALL, "recall.result", refs=[s.pattern_id for s in sups] + [a.episode_id for a in analogs],
                        event_id=parsed.event_id,
                        patterns=[{"id": s.pattern_id, "instance": s.instance_id, "attention": round(s.attention, 4)}
                                  for s in sups],
                        episodes=[{"id": a.episode_id, "attention": round(a.attention, 4),
                                   "tags": list(ltm.episodes.episodes[a.episode_id].tags)} for a in analogs])
        return result


@register("recaller", "recency")
class RecencyRecaller(OverlapAttentionRecaller):
    """Baseline: episodes by recency alone and patterns by support alone."""

    def _episode_scores(self, parsed, sig, ltm, ctx):  # type: ignore[override]
        scores, shared = {}, {}
        for eid, ep in sorted(ltm.episodes.episodes.items()):
            age = max((ctx.now - ep.end).total_seconds() / 86400.0, 0.0)
            scores[eid] = 0.5 ** (age / 365.0)
            shared[eid] = []
        return scores, shared

    def _pattern_scores(self, parsed, sig, wm, ltm, ctx):  # type: ignore[override]
        admitted = ltm.patterns.admitted()
        mx = max([p.support for p in admitted] + [1e-9])
        return {p.id: math.log1p(max(p.support, 0.0)) / math.log1p(mx) for p in admitted}
