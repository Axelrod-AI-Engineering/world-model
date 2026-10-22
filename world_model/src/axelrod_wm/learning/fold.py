"""The fold: working-memory learning's update step (§8.6.2).

For each observed subentity, a joint Kalman update of its level and the effects of its incoming
interactions, applied on the processing day. Inputs: the parsed event and its analysis. Output: a
FoldResult (what moved, the unexplained moves, the decisions observed). Writes working memory only;
the decisions it observes are recorded in entity memories by long-term learning (learning/long_term.py).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.dynamics.daily import (
    MAX_TIME_STATES,
    in_channel_index,
    interaction_time_state,
    pair_key,
    predict_state,
    refit_effect,
    subentity_time_state,
    time_state_due,
)
from axelrod_wm.dynamics.regressors import clip_of
from axelrod_wm.engine.interfaces import Analysis
from axelrod_wm.engine.registry import register, registry
from axelrod_wm.memory.entity_memory import DecisionObservation
from axelrod_wm.memory.working import DeviationPoint, point_key
from axelrod_wm.model.distributions import Beta, from_link, from_link_moments, to_link
from axelrod_wm.model.evidence import Evidence
from axelrod_wm.shared.process import ParsedEvent
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.repo.mutator import MutationTxn

MAX_EVIDENCE = 50


class FoldResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_subentities: list[str]
    updated_interactions: list[str]
    innovations: dict[str, float]          # standardized, today
    decisions: list[DecisionObservation]
    day: int = 0                           # the processing day
    effect_changes: dict[str, float] = {}  # interaction id -> |change in effect mean|
    existence_changes: dict[str, float] = {}


class Folder(ABC):
    @abstractmethod
    def fold(self, parsed: ParsedEvent, analysis: Analysis, wm: WorkingMemory,
             ctx: ProcessContext, txn: MutationTxn) -> FoldResult: ...


registry("folder", Folder)


def _norm_pdf(x: float, mu: float, var: float) -> float:
    var = max(var, 1e-12)
    return math.exp(-0.5 * (x - mu) ** 2 / var) / math.sqrt(2 * math.pi * var)


def native_scale(sub: Any) -> float:
    """One standardized unit in native units, at the anchor."""
    link = sub.posterior.link
    return abs(float(from_link(sub.anchor + sub.scale, link)) - float(from_link(sub.anchor, link)))


def last_observed_z(wm: WorkingMemory, sid: str, before_day: int, max_days: int = 400) -> float | None:
    dev = wm.deviations
    stop = max(before_day - max_days, dev.first_kept_day)
    for d in range(before_day - 1, stop - 1, -1):
        p = dev.point(sid, d)
        if p is not None and p.observed:
            return p.z
    return None


@register("folder", "kalman_edge")
class KalmanEdgeFolder(Folder):
    """The update step of the daily model (§8.6.2): a joint Kalman update of each observed
    subentity's level and in-channel effects, applied on the processing day."""

    def __init__(self, config: Any = None) -> None:
        self.config = config

    def fold(self, parsed: ParsedEvent, analysis: Analysis, wm: WorkingMemory,
             ctx: ProcessContext, txn: MutationTxn) -> FoldResult:
        cfg = ctx.config
        L = cfg.learning
        graph = wm.graph
        dev = wm.deviations
        day = int(parsed.processing_day)
        clip = clip_of(ctx)
        min_reg = float(L.min_regressor)
        rate = float(L.existence_learning_rate)
        routine = parsed.is_routine()
        upd_subs: list[str] = []
        upd_ints: list[str] = []
        innovations: dict[str, float] = {}
        decisions: list[DecisionObservation] = []
        effect_changes: dict[str, float] = {}
        existence_changes: dict[str, float] = {}
        items: list[tuple[str, float, float, datetime, bool]] = []
        for sid, value, noise, at in parsed.observations:
            sub = graph.subentities[sid]
            y = (float(to_link(value, sub.posterior.link)) - sub.anchor) / sub.scale
            items.append((sid, y, float(noise), at, False))
        for sid, size, r_sd, at in parsed.change_observations:
            items.append((sid, size, float(r_sd), at, True))
        index = in_channel_index(graph) if items else {}
        for sid, y_raw, noise, at, is_change in items:
            sub = graph.subentities[sid]
            pkey = point_key(sid, day)
            pred = predict_state(sub, index.get(sid, []), wm, day, clip)
            point = dev.points.get(pkey)
            if point is None:                    # a subentity created today, after the predict step
                point = DeviationPoint(z=pred.z, var=pred.var, level=float(sub.level_mean))
                txn.add("wm.deviations.points", point, key=pkey)
            z_now = point.z
            # 1. joint update of [level, effects of channels with |m phi| >= min_regressor]
            k_all = len(pred.names)
            sel = [0] + [i for i in range(1, k_all) if abs(pred.H[i]) >= min_reg]
            offset = pred.additive + sum(float(pred.theta[i] * pred.H[i]) for i in range(1, k_all) if i not in sel)
            names = [pred.names[i] for i in sel]
            used = [pred.channels[i - 1] for i in sel[1:]]
            theta = pred.theta[sel]
            P = pred.P[np.ix_(sel, sel)]
            H = pred.H[sel]
            k = len(sel)
            y = z_now + y_raw if is_change else y_raw
            R = noise * noise
            y_adj = y - offset
            prior_mean = float(H @ theta)
            PH = P @ H
            S = float(H @ PH) + R
            K = PH / S
            resid = y_adj - prior_mean
            e = resid / math.sqrt(S)
            theta_post = theta + K * resid
            P_post = P - np.outer(K, PH)
            P_post = 0.5 * (P_post + P_post.T)
            filtered = float(H @ theta_post) + offset
            var_z = max(float(H @ P_post @ H), 1e-12)
            # DECISION: a reported change (change_value) is its own cause, not an unexplained move, so its
            # innovation is recorded as 0 for the frontier.
            e_rec = 0.0 if is_change else e
            # 2-3. today's point and the subentity's posterior
            before = sub.posterior.summary()
            posterior = from_link_moments(sub.posterior.family, sub.anchor + sub.scale * filtered,
                                          (sub.scale ** 2) * var_z)
            # DECISION: the plan keeps only the diagonal; we also keep the target's off-diagonal state
            # covariances (Subentity.state_cov). Discarding the level-effect covariance biased effect
            # estimates and made them overconfident in tests. Diagonals stay where the plan stores them.
            cov = dict(sub.state_cov)
            for a in range(k):
                for b in range(a + 1, k):
                    cov[pair_key(names[a], names[b])] = float(P_post[a, b])
            txn.update("wm.graph.subentities", sid, level_mean=float(theta_post[0]),
                       level_var=float(max(P_post[0, 0], 1e-9)), posterior=posterior,
                       state_cov=dict(sorted(cov.items())))
            txn.update("wm.deviations.points", pkey, z=filtered, var=var_z, level=float(theta_post[0]),
                       innovation=e_rec, observed=True)
            if not routine:
                txn.append_to("wm.graph.subentities", sid, "history",
                              subentity_time_state(graph.subentities[sid], dev.points[pkey], at, ctx.now, day,
                                                   parsed.event_id, y),
                              keep_last=MAX_TIME_STATES)
            innovations[sid] = e_rec
            if sid not in upd_subs:
                upd_subs.append(sid)
            ctx.tracer.emit(Phase.FOLD, "fold.posterior", refs=[sid], subentity_id=sid, before=before,
                            after=posterior.summary(), z=round(filtered, 4), innovation=round(e, 4), day=day)
            L1 = _norm_pdf(y_adj, prior_mean, S)
            for j, ch in enumerate(used, start=1):
                inter = graph.interactions[ch.inter.id]
                h = float(H[j])
                mu_prior, var_prior = float(theta[j]), float(P[j, j])
                mu_post, var_post = float(theta_post[j]), float(max(P_post[j, j], 1e-9))
                # 4. existence
                # DECISION: with the kept off-diagonal covariances, "without its contribution" means the
                # other states conditioned on beta_c = 0 (mean shifted by P_oc / P_cc * -mu_c, covariance
                # P_oo - P_oc P_co / P_cc). With a diagonal P this is exactly the plan's L0; without the
                # conditioning, an edge whose regressor is confounded with the level looked like evidence.
                p_ex = inter.existence.mean()
                keep = [m for m in range(k) if m != j]
                Hk = H[keep]
                Poc = P[keep, j]
                Pcc = max(float(P[j, j]), 1e-12)
                mean0 = float(Hk @ (theta[keep] - Poc * (mu_prior / Pcc)))
                S0 = float(Hk @ (P[np.ix_(keep, keep)] - np.outer(Poc, Poc) / Pcc) @ Hk) + R
                L0 = _norm_pdf(y_adj, mean0, max(S0, 1e-9))
                r = p_ex * L1 / max(p_ex * L1 + (1 - p_ex) * L0, 1e-300)
                wgt = rate * min(1.0, abs(h))
                existence = Beta(alpha=inter.existence.alpha + wgt * r, beta=inter.existence.beta + wgt * (1 - r))
                dyn = ch.dyn
                # an accounting, identity or stock-flow link is an identity, not an estimate: its weight and existence
                # stay as built (Oct 17: statistics flipped the sign of "vehicle sales -> profit")
                if not inter.fixed:
                    txn.update("wm.graph.interactions", inter.id,
                               **{f"{ch.side}.effect": refit_effect(dyn.effect, mu_post, var_post),
                                  "existence": existence})
                    inter = graph.interactions[inter.id]
                # 5. time states and evidence
                if not routine or time_state_due(inter.time_states, wm, day):
                    txn.append_to("wm.graph.interactions", inter.id, "time_states",
                                  interaction_time_state(inter, at, ctx.now, parsed.event_id, phi=h),
                                  keep_last=MAX_TIME_STATES)
                moved = abs(mu_post - mu_prior)
                effect_changes[inter.id] = effect_changes.get(inter.id, 0.0) + moved
                existence_changes[inter.id] = existence_changes.get(inter.id, 0.0) + abs(existence.mean() - p_ex)
                sd_prior = math.sqrt(max(var_prior, 1e-12))
                if moved > 0.1 * sd_prior:
                    self._evidence(inter, moved / sd_prior, parsed, ctx, txn)
                if inter.id not in upd_ints:
                    upd_ints.append(inter.id)
                ctx.tracer.emit(Phase.FOLD, "fold.edge", refs=[inter.id], interaction_id=inter.id, channel=ch.key,
                                effect_before=round(mu_prior, 4), effect_after=round(mu_post, 4),
                                existence_before=round(p_ex, 4), existence_after=round(existence.mean(), 4))
                # 6. day accumulators
                # DECISION: keyed by channel id (the interaction id for a forward channel), so the two
                # directions of a bidirectional edge keep separate implied effects.
                # DECISION: each term is weighted by R / S0, where S0 (computed above for the existence
                # update) is the predictive variance without this channel's own effect: y_partial is y
                # minus the prior level and the other channels, so when those are uncertain (a decision
                # variable between meetings, a target observed monthly) its implied effect is mostly
                # noise. With the weight, an analog's pseudo-observation (§8.4.4) has the precision the
                # data actually carried, rather than the observation noise alone.
                others = sum(float(theta[m] * H[m]) for m in range(1, k) if m != j)
                y_partial = y_adj - float(theta[0]) - others
                wq = R / max(S0, R, 1e-12)
                acc = wm.fold_accumulators.get(ch.key, (0.0, 0.0))
                txn.put("wm.fold_accumulators", ch.key, (acc[0] + wq * h * y_partial, acc[1] + wq * h * h))
            # 7. decisions
            if sid in wm.decision_variables:
                obs = self._decision(sid, filtered, y_raw if is_change else None, at, day, wm, index, ctx, txn)
                decisions.append(obs)
        return FoldResult(updated_subentities=upd_subs, updated_interactions=upd_ints, innovations=innovations,
                          decisions=decisions, day=day, effect_changes=effect_changes,
                          existence_changes=existence_changes)

    def _decision(self, sid: str, filtered: float, change_size: float | None, at: datetime, day: int,
                  wm: WorkingMemory, index: dict, ctx: ProcessContext, txn: MutationTxn) -> DecisionObservation:
        """The decision as observed: its size in native units and the context it was made in. Long-term
        learning appends it to the entity's memory and counts it in the decision profile."""
        graph = wm.graph
        sub = graph.subentities[sid]
        link = sub.posterior.link
        base = last_observed_z(wm, sid, day)
        if base is None:
            base = filtered - (change_size or 0.0)
        if change_size is not None:
            after = base + change_size
        else:
            after = filtered
        change = float(from_link(sub.anchor + sub.scale * after, link) - from_link(sub.anchor + sub.scale * base, link))
        context = {}
        for ch in index.get(sid, []):
            context[ch.source] = round(float(wm.deviations.z(ch.source, day)), 6)
        return DecisionObservation(subentity_id=sid, at=at, change=change, context=context)

    def _evidence(self, inter: Any, size: float, parsed: ParsedEvent, ctx: ProcessContext, txn: MutationTxn) -> None:
        from axelrod_wm.shared.parse import source_type_for

        ev = Evidence(id=txn.new_id("EV"), source_type=source_type_for(parsed.produced_by),
                      excerpt=ctx.notes.get("headline") or parsed.event_id, observed_at=parsed.occurred_at or ctx.now,
                      strength=min(1.0, size), market_event_id=parsed.market_event_id)
        over = len(inter.evidence) + 1 - MAX_EVIDENCE
        txn.append_to("wm.graph.interactions", inter.id, "evidence", ev, keep_last=MAX_EVIDENCE)
        if over > 0:
            txn.update("wm.graph.interactions", inter.id, evidence_dropped=inter.evidence_dropped + over)
