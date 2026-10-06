"""The learning task: fold a real event into the state on the processing day (§8.6)."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.distributions import Beta, from_link, from_link_moments, to_link
from axelrod_wm.core.evidence import Evidence
from axelrod_wm.core.superentity import SuperentityStatus
from axelrod_wm.core.taxonomy import RunningStats, TaxonomyKind, relation_key
from axelrod_wm.engine.daily import (
    MAX_TIME_STATES,
    in_channel_index,
    interaction_time_state,
    pair_key,
    predict_state,
    refit_effect,
    subentity_time_state,
    time_state_due,
)
from axelrod_wm.engine.interfaces import Analysis, Classification
from axelrod_wm.engine.registry import register, registry
from axelrod_wm.engine.regressors import clip_of
from axelrod_wm.engine.shared import ParsedEvent, SharedResult, build_new_channels
from axelrod_wm.memory.entity_memory import DecisionObservation, DecisionProfile, EntityMemory, action_of
from axelrod_wm.memory.frontier import FrontierResult
from axelrod_wm.memory.working import DeviationPoint, EpisodeEntry, point_key
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import MutationTxn
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.explain_records import Explanation
    from axelrod_wm.events.graph_update import GraphUpdateEvent
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory

MAX_EVIDENCE = 50
OBJECT_NODES = "ltm.object_generalizations.taxonomy.nodes"
INTERACTION_NODES = "ltm.interaction_generalizations.taxonomy.nodes"
PATTERNS = "ltm.object_generalizations.patterns"


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


class GeneralizationUpdater(ABC):
    @abstractmethod
    def update(self, classifications: list[Classification], ltm: LongTermMemory,
               ctx: ProcessContext, txn: MutationTxn) -> None: ...


class KernelUpdater(ABC):
    @abstractmethod
    def update(self, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext,
               txn: MutationTxn) -> list[str]:
        """Run at consolidation. Returns the interaction ids whose kernels changed."""


class LearningResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    shared: SharedResult
    fold: FoldResult
    frontier: FrontierResult
    explanation: Any
    proposal_events: list[dict] = []


registry("folder", Folder)
registry("generalization_updater", GeneralizationUpdater)
registry("kernel_updater", KernelUpdater)


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
        """Append a DecisionObservation to the entity's memory and count it in its profile."""
        from axelrod_wm.engine.voi import context_bucket

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
        obs = DecisionObservation(subentity_id=sid, at=at, change=change, context=context)
        eid = sub.entity_id
        mem = ctx.ltm.entity_memories.get(eid)
        if mem is None:
            txn.add("ltm.entity_memories", EntityMemory(entity_id=eid, decisions=[obs]))
            profiles: dict[str, DecisionProfile] = {}
        else:
            txn.append_to("ltm.entity_memories", eid, "decisions", obs, keep_last=EntityMemory.MAX_DECISIONS)
            profiles = {k: v.model_copy(deep=True) for k, v in mem.profiles.items()}
        # decision observations are folded into the profiles on the day they happen (§8.12)
        prof = profiles.setdefault(sid, DecisionProfile())
        counts = prof.by_context.setdefault(context_bucket(context), [0, 0, 0])
        counts[("raised", "cut", "held").index(action_of(change, native_scale(sub)))] += 1
        txn.update("ltm.entity_memories", eid, profiles=profiles)
        return obs

    def _evidence(self, inter: Any, size: float, parsed: ParsedEvent, ctx: ProcessContext, txn: MutationTxn) -> None:
        from axelrod_wm.engine.parse import source_type_for

        ev = Evidence(id=txn.new_id("EV"), source_type=source_type_for(parsed.produced_by),
                      excerpt=ctx.notes.get("headline") or parsed.event_id, observed_at=parsed.occurred_at or ctx.now,
                      strength=min(1.0, size), market_event_id=parsed.market_event_id)
        over = len(inter.evidence) + 1 - MAX_EVIDENCE
        txn.append_to("wm.graph.interactions", inter.id, "evidence", ev, keep_last=MAX_EVIDENCE)
        if over > 0:
            txn.update("wm.graph.interactions", inter.id, evidence_dropped=inter.evidence_dropped + over)


# ---------------------------------------------------------------------------------------------
# Generalization updates
# ---------------------------------------------------------------------------------------------

def pattern_relation_effects(pattern_id: str, wm: WorkingMemory) -> list[tuple[str, float]]:
    """(relation key, effect mean) for the realized relations of a pattern's bound instances."""
    graph = wm.graph
    out = []
    for iid in sorted(graph.instances):
        inst = graph.instances[iid]
        if inst.pattern_id != pattern_id or inst.transient:
            continue
        for int_id in inst.interaction_ids:
            inter = graph.interactions.get(int_id)
            if inter is None or inter.retired_at is not None:
                continue
            s, t = graph.subentities.get(inter.source_id), graph.subentities.get(inter.target_id)
            if s is None or t is None:
                continue
            out.append((relation_key(s.attribute_kind, t.attribute_kind, inter.polarity()),
                        inter.forward.effect.mean()))
    return out


@register("generalization_updater", "path_stats")
class PathStatsUpdater(GeneralizationUpdater):
    """For every node on each classification path: support += 1, plus attribute, edge, or pattern
    statistics (§8.6.2)."""

    def __init__(self, config: Any = None) -> None:
        self.config = config

    def update(self, classifications: list[Classification], ltm: LongTermMemory,
               ctx: ProcessContext, txn: MutationTxn) -> None:
        if not ctx.learn:
            return
        graph = ctx.wm.graph
        patterns = ltm.object_generalizations.patterns
        pending: dict[tuple[str, str], Any] = {}
        for c in classifications:
            tax = ltm.taxonomy(c.taxonomy)
            coll = OBJECT_NODES if c.taxonomy == TaxonomyKind.OBJECT else INTERACTION_NODES
            for gid in c.path:
                if gid not in tax.nodes:
                    continue
                key = (coll, gid)
                st = pending.get(key)
                if st is None:
                    st = pending[key] = tax.nodes[gid].stats.model_copy(deep=True)
                st.support += 1.0
                if c.taxonomy == TaxonomyKind.OBJECT and c.item_id in graph.entities:
                    for sid in graph.entities[c.item_id].subentity_ids:
                        sub = graph.subentities.get(sid)
                        if sub is None:
                            continue
                        m, _ = sub.posterior.link_moments()
                        st.attribute_level.setdefault(sub.attribute_kind, RunningStats()).push(m)
                        st.attribute_scale.setdefault(sub.attribute_kind, RunningStats()).push(sub.scale)
                elif c.taxonomy == TaxonomyKind.OBJECT and c.item_id in patterns:
                    for rkey, eff in pattern_relation_effects(c.item_id, ctx.wm):
                        st.relation_effects.setdefault(rkey, RunningStats()).push(eff)
                elif c.taxonomy == TaxonomyKind.INTERACTION and c.item_id in graph.interactions:
                    inter = graph.interactions[c.item_id]
                    st.effect.push(inter.forward.effect.mean())
                    d, l, dur = inter.forward.kernel.means()
                    st.delay_days.push(d)
                    st.lag_days.push(l)
                    if dur is None:
                        st.duration_permanent += 1.0
                    else:
                        st.duration_days.push(dur)
                    p = inter.existence.mean()
                    st.existence_alpha += 0.1 * p
                    st.existence_beta += 0.1 * (1 - p)
        self._write(pending, ctx, txn)

    def update_pattern(self, pattern_id: str, ltm: LongTermMemory, ctx: ProcessContext, txn: MutationTxn, *,
                       count_support: bool = True, hits: float = 0.0, misses: float = 0.0) -> None:
        """The path update for a superentity pattern at a counted support increment (support += 1 and
        its realized relations' effects) or a track-record change (hits and misses only).
        # DECISION: a track-record change alone does not add support to the path's nodes."""
        pat = ltm.object_generalizations.patterns.get(pattern_id)
        tax = ltm.object_generalizations.taxonomy
        if pat is None or not pat.generalization_id or pat.generalization_id not in tax.nodes:
            return
        effects = pattern_relation_effects(pattern_id, ctx.wm) if count_support else []
        pending: dict[tuple[str, str], Any] = {}
        for gid in tax.path_from_root(pat.generalization_id):
            st = tax.nodes[gid].stats.model_copy(deep=True)
            if count_support:
                st.support += 1.0
                for rkey, eff in effects:
                    st.relation_effects.setdefault(rkey, RunningStats()).push(eff)
            st.track_hits += hits
            st.track_misses += misses
            pending[(OBJECT_NODES, gid)] = st
        self._write(pending, ctx, txn)

    @staticmethod
    def _write(pending: dict[tuple[str, str], Any], ctx: ProcessContext, txn: MutationTxn) -> None:
        for (coll, gid), st in sorted(pending.items()):
            txn.update(coll, gid, stats=st)
        if pending:
            ctx.tracer.emit(Phase.GENERALIZE, "generalize.updated", refs=[g for _, g in sorted(pending)],
                            supports={g: round(st.support, 3) for (_, g), st in sorted(pending.items())})


def episode_entry(parsed: ParsedEvent, explanation: Explanation | None, at: datetime) -> EpisodeEntry:
    return EpisodeEntry(event_id=parsed.event_id, at=at, event_type=parsed.event_type, tags=list(parsed.tags),
                        signature=set(parsed.signature), routine=parsed.is_routine(),
                        explanation_id=explanation.id if explanation is not None else None,
                        touched_entity_ids=list(parsed.touched_entity_ids))


# ---------------------------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------------------------

class LearningTask:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    @property
    def shared(self) -> Any:
        return self.engine.shared

    def run(self, event: GraphUpdateEvent, now: datetime, processing_day: int | None = None, *,
            headline: str | None = None, proposal_kind: str | None = None) -> LearningResult:
        """Called by the update run's day loop (§7.8), after that day's predict()."""
        eng = self.engine
        comp = eng.components
        ctx = eng.context(learn=True, now=now, processing_day=processing_day)
        if headline:
            ctx.notes["headline"] = headline
        if proposal_kind:
            ctx.notes["proposal_kind"] = proposal_kind
        with ctx.mutator.begin(cause=event.id, at=now) as txn:
            shared = self.shared.run(event, ctx, txn)
            fold = comp["folder"].fold(shared.parsed, shared.analysis, eng.wm, ctx, txn)
            comp["generalization_updater"].update(shared.classifications, eng.ltm, ctx, txn)
            if ctx.initializing:
                frontier = FrontierResult()
            else:
                frontier = comp["frontier"].test(fold, eng.wm, eng.ltm, ctx, txn)
            explanation = comp["explainer"].explain_learning(shared, fold, frontier, ctx)
            txn.add("ltm.prior_states.explanations", explanation)
            ctx.tracer.emit(Phase.EXPLAIN, "explain.stored", refs=[explanation.id, event.id],
                            explanation_id=explanation.id, top_paths=[], text=explanation.text)
            txn.append("wm.episode_buffer", episode_entry(shared.parsed, explanation, now))
        events = list(shared.induction.proposal_events) + list(getattr(frontier, "proposal_events", []))
        return LearningResult(shared=shared, fold=fold, frontier=frontier, explanation=explanation,
                              proposal_events=events)


class StructuralApplier:
    """Applies approved structural changes and the user's drawn edits: parse, classify, and update
    generalizations through the mutator, without a fold (§7.6, §8.6)."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def apply(self, event: GraphUpdateEvent, now: datetime, proposal_kind: str | None = None) -> list[Classification]:
        from axelrod_wm.events.graph_update import DissolveSuperentity, ProposeSuperentity

        eng = self.engine
        comp = eng.components
        ctx = eng.context(learn=True, now=now)
        if proposal_kind:
            ctx.notes["proposal_kind"] = proposal_kind
        classifications: list[Classification] = []
        with ctx.mutator.begin(cause=event.id, at=now) as txn:
            other_ops = [op for op in event.ops if not isinstance(op, (ProposeSuperentity, DissolveSuperentity))]
            for op in event.ops:
                if isinstance(op, ProposeSuperentity):
                    classifications.append(self._admit(op, ctx, txn))
                elif isinstance(op, DissolveSuperentity):
                    self._dissolve(op, ctx, txn)
            if other_ops:
                sub_event = event.model_copy(update={"ops": other_ops})
                parsed = comp["parser"].parse(sub_event, eng.wm, eng.ltm, ctx, txn)
                for kind, item_id, is_new in parsed.to_classify():
                    if kind == TaxonomyKind.OBJECT and not is_new:
                        continue
                    classifications.append(comp["classifier"].classify(kind, item_id, is_new, ctx, txn))
                build_new_channels(parsed.new_interaction_ids, ctx, txn)
            if classifications:
                # the path update: for an admitted pattern it pools its realized relations' effects
                # into relation_effects on every node along its path (§8.8 step 7)
                comp["generalization_updater"].update(classifications, eng.ltm, ctx, txn)
        return classifications

    def _admit(self, op: Any, ctx: ProcessContext, txn: MutationTxn) -> Classification:
        from axelrod_wm.core.superentity import SuperentityInstance
        from axelrod_wm.memory.long_term import SuperInteractionBuilder

        eng = self.engine
        p = op.pattern
        og = eng.ltm.object_generalizations
        existing = og.patterns.get(p.id)
        if existing is None:
            txn.add(PATTERNS, p.model_copy(update={"status": SuperentityStatus.ADMITTED, "proposed_at": None}))
        else:
            txn.update(PATTERNS, p.id, status=SuperentityStatus.ADMITTED, proposed_at=None, name=p.name)
        cls = eng.components["classifier"].classify(TaxonomyKind.OBJECT, p.id, True, ctx, txn)
        # a newly admitted pattern starts from its configuration node's pooled track record (§6.9)
        node = og.taxonomy.nodes.get(cls.prior_source_id)
        if node is not None:
            _priors, record = node.prior_for_pattern()
            pat = og.patterns[p.id]
            if pat.track_record.hits + pat.track_record.misses <= 0 and record.hits + record.misses > 0:
                txn.update(PATTERNS, p.id, track_record=record)
        graph = eng.wm.graph
        if not any(i.pattern_id == p.id for i in graph.instances.values()):
            binding = eng.components["binder"].bind(og.patterns[p.id], sorted(set(op.bindings.values())), graph,
                                                    eng.ltm)
            if binding is not None:
                txn.add("wm.graph.instances", SuperentityInstance(
                    id=txn.new_id("inst"), pattern_id=p.id, bindings=binding.bindings,
                    interaction_ids=binding.interaction_ids, absent_interaction_ids=binding.absent_interaction_ids))
        SuperInteractionBuilder().rebuild(graph, og, txn)
        ctx.tracer.emit(Phase.ABDUCE, "abduce.admitted", refs=[p.id], pattern_id=p.id, path=cls.path)
        return cls

    def _dissolve(self, op: Any, ctx: ProcessContext, txn: MutationTxn) -> None:
        from axelrod_wm.memory.long_term import SuperInteractionBuilder

        eng = self.engine
        og = eng.ltm.object_generalizations
        if op.pattern_id not in og.patterns:
            return
        txn.update(PATTERNS, op.pattern_id, status=SuperentityStatus.DISSOLVED, proposed_at=None)
        for iid in sorted(eng.wm.graph.instances):
            if eng.wm.graph.instances[iid].pattern_id == op.pattern_id:
                txn.remove("wm.graph.instances", iid)
                ctx.tracer.emit(Phase.PREFILL, "induce.dissolved", refs=[iid, op.pattern_id], instance_id=iid,
                                pattern_id=op.pattern_id, transient=False)
        SuperInteractionBuilder().rebuild(eng.wm.graph, og, txn)
