"""The open node (Oct 9): every node of working memory and of long-term memory carries an empty terminal node, the
probability mass the graph does not account for yet. It is drawn as an empty node attached to the node it belongs to,
so the missing mass is visible, and it gives every node the same reserve to reason with later.

- a value (subentity): the share of its recent movement that its incoming interactions do not explain. The daily state
  is [level, in-channel effects]; the local level is the model's own name for "a cause not in the graph", so over the
  activity window the open share is sum(level part^2) / sum(movement^2), shrunk toward 1 by `prior_sd2` (a value with
  no data, or no incoming interactions, is wholly open);
- an entity: the mean of its values' open shares;
- a superentity (an instance in working memory): the same share over its members' values, counting only the
  interactions the superentity holds as explained;
- a kind (an object or interaction generalization in long-term memory): the Chinese-restaurant-process probability
  that the next item classified here is of a kind not seen yet, alpha / (support + alpha) (Aldous, 1985);
- a superentity pattern in long-term memory: the same reserve beside its rivals, alpha / (its support + its rivals'
  support + alpha);
- a hedge's fuzzy end already carries one: its Dirichlet "__open__" share.

DECISION: the channel multipliers (moderators) are left out of the explained part; they scale a channel's regressor by
a few percent and would need each day's moderator values, which the activity window does not keep.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory


def _window(wm: WorkingMemory, cfg: Any) -> range:
    today = int(wm.last_processed_day)
    width = max(1, int(cfg.abduction.window_days))
    return range(max(int(wm.deviations.first_kept_day), today - width + 1), today + 1)


def _sums(wm: WorkingMemory, sid: str, chans: list[Any], days: range) -> tuple[float, float]:
    """(sum of the level part squared, sum of the movement squared) over `days`, explained by `chans`."""
    from axelrod_wm.dynamics.daily import channel_phi_today

    dev = wm.deviations
    open_ss = total_ss = 0.0
    for d in days:
        p = dev.point(sid, d)
        if p is None:
            continue
        explained = sum(float(ch.dyn.effect.mean()) * channel_phi_today(wm, ch.key, d) for ch in chans)
        z = float(p.z)
        open_ss += (z - explained) ** 2
        total_ss += z * z
    return open_ss, total_ss


def _share(open_ss: float, total_ss: float, prior: float) -> float:
    return float(min(1.0, max(0.0, (open_ss + prior) / (total_ss + prior))))


def subentity_open(wm: WorkingMemory, cfg: Any, index: dict[str, list[Any]] | None = None) -> dict[str, float]:
    """Each value's open share."""
    from axelrod_wm.dynamics.daily import in_channel_index

    index = index if index is not None else in_channel_index(wm.graph)
    days = _window(wm, cfg)
    prior = float(cfg.open_world.prior_sd2)
    return {sid: round(_share(*_sums(wm, sid, index.get(sid, []), days), prior), 4)
            for sid in sorted(wm.graph.subentities)}


def entity_open(wm: WorkingMemory, subs: dict[str, float]) -> dict[str, float]:
    """Each entity's open share: the mean over its values."""
    out: dict[str, float] = {}
    for eid, e in wm.graph.entities.items():
        xs = [subs[s] for s in e.subentity_ids if s in subs]
        out[eid] = round(sum(xs) / len(xs), 4) if xs else 1.0
    return out


def instance_open(wm: WorkingMemory, cfg: Any, index: dict[str, list[Any]] | None = None) -> dict[str, float]:
    """Each superentity instance's open share: its members' movement not explained by its own interactions."""
    from axelrod_wm.dynamics.daily import in_channel_index

    g = wm.graph
    index = index if index is not None else in_channel_index(g)
    days = _window(wm, cfg)
    prior = float(cfg.open_world.prior_sd2)
    out: dict[str, float] = {}
    for iid, inst in g.instances.items():
        held = set(inst.interaction_ids)
        open_ss = total_ss = 0.0
        sids = [s for m in sorted(g.members(iid)) if m in g.entities for s in g.entities[m].subentity_ids]
        for sid in sids:
            chans = [ch for ch in index.get(sid, []) if ch.inter.id in held]
            o, t = _sums(wm, sid, chans, days)
            open_ss += o
            total_ss += t
        out[iid] = round(_share(open_ss, total_ss, prior * max(1, len(sids))), 4)
    return out


def kind_open(support: float, cfg: Any) -> float:
    """A kind's reserve for a kind not seen yet: alpha / (support + alpha)."""
    a = float(cfg.open_world.concentration)
    return round(a / (max(0.0, float(support)) + a), 4)


def pattern_open(ltm: LongTermMemory, cfg: Any) -> dict[str, float]:
    """Each superentity pattern's reserve beside its rivals: alpha / (support + rivals' support + alpha)."""
    pats = ltm.object_generalizations.patterns
    a = float(cfg.open_world.concentration)
    out: dict[str, float] = {}
    for pid, p in pats.items():
        rivals = sum(float(pats[r].support) for r in sorted(p.rival_ids) if r in pats)
        out[pid] = round(a / (max(0.0, float(p.support)) + rivals + a), 4)
    return out
