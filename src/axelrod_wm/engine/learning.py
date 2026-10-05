"""The learning task: fold a real event into the state (§8.6)."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.distributions import Beta, Gaussian, from_link, from_link_moments, to_link
from axelrod_wm.core.entity import DecisionObservation, EntityMemory
from axelrod_wm.core.evidence import Evidence
from axelrod_wm.core.superentity import SuperentityStatus
from axelrod_wm.core.taxonomy import RunningStats, TaxonomyKind
from axelrod_wm.core.temporal import Bitemporal, TimeState
from axelrod_wm.engine.interfaces import Analysis, Classification
from axelrod_wm.engine.registry import register, registry
from axelrod_wm.engine.regressors import level_noise_of, regressor_cache
from axelrod_wm.engine.shared import ParsedEvent, SharedResult
from axelrod_wm.memory.frontier import FrontierResult
from axelrod_wm.memory.working import ActivityRecord, EpisodeEntry
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import MutationTxn
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.explain_records import Explanation
    from axelrod_wm.events.graph_update import GraphUpdateEvent
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory

MAX_TIME_STATES = 300
MAX_EVIDENCE = 50


class FoldResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_subentities: list[str]
    updated_interactions: list[str]
    innovations: dict[str, float]          # standardized, at this step
    active_interactions: list[str]
    decisions: list[DecisionObservation]
    step: int = 0
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


def _effect(dist_family: str, mean: float, var: float):
    if dist_family == "gaussian":
        return Gaussian(mu=float(mean), sigma=float(math.sqrt(max(var, 1e-12))))
    return from_link_moments(dist_family, mean, var)


def _pair(a: str, b: str) -> str:
    return f"{a}|{b}" if a <= b else f"{b}|{a}"


def _norm_pdf(x: float, mu: float, var: float) -> float:
    var = max(var, 1e-12)
    return math.exp(-0.5 * (x - mu) ** 2 / var) / math.sqrt(2 * math.pi * var)


@register("folder", "kalman_edge")
class KalmanEdgeFolder(Folder):
    """Joint Kalman update of each observed subentity's level and in-channel effects (§8.6)."""

    def __init__(self, config: Any = None) -> None:
        self.config = config

    def fold(self, parsed: ParsedEvent, analysis: Analysis, wm: WorkingMemory,
             ctx: ProcessContext, txn: MutationTxn) -> FoldResult:
        cfg = ctx.config
        L = cfg.learning
        graph = wm.graph
        dev = wm.deviations
        ltm = ctx.ltm
        cache = regressor_cache(wm, ctx)
        min_reg = float(L.min_regressor)
        q_b = float(L.effect_process_noise)
        rate = float(L.existence_learning_rate)
        min_contrib = float(cfg.abduction.min_edge_contribution)
        w = int(cfg.frontier.window_steps)
        upd_subs: list[str] = []
        upd_ints: list[str] = []
        innovations: dict[str, float] = {}
        active: list[str] = []
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
        last_step = parsed.step
        for sid, y_raw, noise, at, is_change in items:
            sub = graph.subentities[sid]
            t = dev.step_of(at)
            last_step = max(last_step, t)
            z_prev = dev.z_at(sid, t)
            if is_change:
                y = (z_prev if z_prev is not None else sub.level_mean) + y_raw
            else:
                y = y_raw
            R = noise * noise
            used = []
            additive = 0.0
            for key, inter, s, _t, dyn in graph.in_channel_items(sid):
                params = inter.parameters if key == inter.id else []
                phi, add = cache.phi(key, s, dyn, params, t)
                additive += add
                if abs(phi) >= min_reg:
                    used.append((key, inter, dyn, phi))
            y_adj = y - additive
            n = 1 if sub.last_update_step is None else max(1, t - sub.last_update_step)
            q_a = level_noise_of(sub, ctx)
            k = 1 + len(used)
            theta = np.zeros(k)
            P = np.zeros((k, k))
            theta[0] = sub.level_mean
            P[0, 0] = sub.level_var + q_a * q_a * n
            H = np.ones(k)
            names = ["level"] + [u[0] for u in used]
            for j, (_key, _inter, dyn, phi) in enumerate(used, start=1):
                theta[j] = dyn.effect.mean()
                P[j, j] = dyn.effect.var() + q_b * q_b * n
                H[j] = phi
            # DECISION: the plan keeps only the diagonal; we also keep the target's off-diagonal state
            # covariances (Subentity.state_cov). Discarding the level-effect covariance biased effect
            # estimates and made them overconfident in tests. Diagonals stay where the plan stores them.
            for a in range(k):
                for b in range(a + 1, k):
                    c = sub.state_cov.get(_pair(names[a], names[b]), 0.0)
                    lim = 0.999 * float(np.sqrt(P[a, a] * P[b, b]))
                    P[a, b] = P[b, a] = max(-lim, min(lim, c))
            pred = float(H @ theta)
            S = float(H @ P @ H) + R
            K = (P @ H) / S
            resid = y_adj - pred
            e = resid / math.sqrt(S)
            theta_post = theta + K * resid
            P_post = P - np.outer(K, H @ P)
            filtered = float(H @ theta_post)
            var_z = max(float(H @ P_post @ H), 1e-12)
            before = sub.posterior.summary()
            m_link = sub.anchor + sub.scale * filtered
            posterior = from_link_moments(sub.posterior.family, m_link, (sub.scale ** 2) * var_z)
            # DECISION: a reported change (change_value) is its own cause, not an unexplained move, so its
            # innovation is recorded as 0 for the frontier.
            e_rec = 0.0 if is_change else e
            ts = TimeState(at=Bitemporal(valid_at=at, recorded_at=ctx.now),
                           values={"mean": posterior.mean(), "sd": posterior.sd(), "z": filtered,
                                   "level": float(theta_post[0]), "step": float(t), "innovation": e_rec, "y": y},
                           source_event_id=parsed.event_id)
            cov = dict(sub.state_cov)
            for a in range(k):
                for b in range(a + 1, k):
                    cov[_pair(names[a], names[b])] = float(P_post[a, b])
            txn.update("subentities", sid, level_mean=float(theta_post[0]), level_var=float(max(P_post[0, 0], 1e-9)),
                       last_update_step=t, posterior=posterior, state_cov=dict(sorted(cov.items())))
            txn.append_to("subentities", sid, "history", ts, keep_last=MAX_TIME_STATES)
            txn.merge("wm.deviations", {"z": {sid: {t: filtered}}, "innovation": {sid: {t: e_rec}}})
            innovations[sid] = e_rec
            if sid not in upd_subs:
                upd_subs.append(sid)
            ctx.tracer.emit(Phase.FOLD, "fold.posterior", refs=[sid], subentity_id=sid, before=before,
                            after=posterior.summary(), z=round(filtered, 4), innovation=round(e, 4))
            p_resid_base = y_adj - theta[0]
            for j, (key, inter, dyn, phi) in enumerate(used, start=1):
                inter = graph.interactions[inter.id]  # fresh
                mu_prior, var_prior = theta[j], P[j, j]
                mu_post, var_post = float(theta_post[j]), float(max(P_post[j, j], 1e-9))
                p = inter.existence.mean()
                L1 = _norm_pdf(y_adj, pred, S)
                # predictive variance without channel j: S - phi^2 P_jj when P is diagonal (the plan's
                # formula); with the kept covariances the cross terms go too
                keep = [m for m in range(k) if m != j]
                S0 = float(H[keep] @ P[np.ix_(keep, keep)] @ H[keep]) + R
                L0 = _norm_pdf(y_adj, pred - mu_prior * phi, max(S0, 1e-9))
                r = p * L1 / max(p * L1 + (1 - p) * L0, 1e-300)
                wgt = rate * min(1.0, abs(phi))
                existence = Beta(alpha=inter.existence.alpha + wgt * r, beta=inter.existence.beta + wgt * (1 - r))
                new_dyn = dyn.model_copy(update={"effect": _effect(dyn.effect.family, mu_post, var_post)})
                fields: dict[str, Any] = {"existence": existence}
                if key == inter.id:
                    fields["forward"] = new_dyn
                else:
                    fields["reverse"] = new_dyn
                before_eff, before_ex = dyn.effect.mean(), p
                txn.update("interactions", inter.id, **fields)
                inter = graph.interactions[inter.id]
                ts_i = TimeState(at=Bitemporal(valid_at=at, recorded_at=ctx.now),
                                 values={"effect_mean": mu_post, "effect_sd": math.sqrt(var_post),
                                         "existence_mean": existence.mean(), "significance": inter.significance_mean(),
                                         "phi": phi},
                                 source_event_id=parsed.event_id)
                txn.append_to("interactions", inter.id, "time_states", ts_i, keep_last=MAX_TIME_STATES)
                moved = abs(mu_post - mu_prior)
                effect_changes[inter.id] = effect_changes.get(inter.id, 0.0) + moved
                existence_changes[inter.id] = existence_changes.get(inter.id, 0.0) + abs(existence.mean() - before_ex)
                if moved > 0.1 * math.sqrt(max(var_prior, 1e-12)):
                    self._evidence(inter, moved / math.sqrt(max(var_prior, 1e-12)), parsed, ctx, txn)
                if inter.id not in upd_ints:
                    upd_ints.append(inter.id)
                ctx.tracer.emit(Phase.FOLD, "fold.edge", refs=[inter.id], interaction_id=inter.id, channel=key,
                                effect_before=round(before_eff, 4), effect_after=round(mu_post, 4),
                                existence_before=round(before_ex, 4), existence_after=round(existence.mean(), 4))
                contrib = mu_post * phi
                if abs(contrib) >= min_contrib:
                    # DECISION: compare the cumulative contribution with the target's move over the channel's
                    # response horizon (delay + lag, at least the frontier window), not just the last 4 steps.
                    dd, ll, _ = dyn.kernel.means()
                    horizon = max(w, int(math.ceil((dd + ll) / ctx.step_days)))
                    target_move = dev.window_change(sid, t, horizon)
                    txn.append("wm.activity_log", ActivityRecord(step=t, interaction_id=inter.id, contribution=contrib,
                                                                 target_move=target_move, channel_key=key,
                                                                 target_id=sid))
                    if inter.id not in active:
                        active.append(inter.id)
                others = sum(theta[m] * used[m - 1][3] for m in range(1, k) if m != j)
                y_partial = p_resid_base - others
                acc = wm.fold_accumulators.get(inter.id, (0.0, 0.0))
                txn.merge("wm.fold_accumulators", {inter.id: (acc[0] + phi * y_partial, acc[1] + phi * phi)})
            if sid in wm.decision_variables and z_prev is not None:
                link = sub.posterior.link
                change = float(from_link(sub.anchor + sub.scale * filtered, link)
                               - from_link(sub.anchor + sub.scale * z_prev, link))
                context = {}
                for _key, _inter, s, _t, _dyn in graph.in_channel_items(sid):
                    zs = dev.z_at(s, t)
                    if zs is not None:
                        context[s] = round(float(zs), 6)
                obs = DecisionObservation(subentity_id=sid, at=at, change=change, context=context)
                decisions.append(obs)
                eid = sub.entity_id
                if eid in ltm.entity_memories:
                    txn.append_to("entity_memories", eid, "decisions", obs, keep_last=500)
                else:
                    txn.add("entity_memories", EntityMemory(entity_id=eid, decisions=[obs]))
        self._activations(wm, txn)
        return FoldResult(updated_subentities=upd_subs, updated_interactions=upd_ints, innovations=innovations,
                          active_interactions=active, decisions=decisions, step=last_step,
                          effect_changes=effect_changes, existence_changes=existence_changes)

    def _evidence(self, inter: Any, size: float, parsed: ParsedEvent, ctx: ProcessContext, txn: MutationTxn) -> None:
        from axelrod_wm.engine.parse import source_type_for

        ev = Evidence(id=txn.new_id("EV"), source_type=source_type_for(parsed.produced_by),
                      excerpt=ctx.notes.get("headline") or parsed.event_id, observed_at=parsed.occurred_at or ctx.now,
                      strength=min(1.0, size), market_event_id=parsed.market_event_id)
        cur = inter.evidence
        if len(cur) + 1 > MAX_EVIDENCE:
            txn.update("interactions", inter.id, evidence=(list(cur) + [ev])[-MAX_EVIDENCE:],
                       evidence_dropped=inter.evidence_dropped + len(cur) + 1 - MAX_EVIDENCE)
        else:
            txn.append_to("interactions", inter.id, "evidence", ev)

    def _activations(self, wm: WorkingMemory, txn: MutationTxn) -> None:
        logged = {r.interaction_id for r in wm.activity_log}
        for iid in sorted(wm.graph.instances):
            inst = wm.graph.instances[iid]
            if inst.transient:
                continue
            ids = inst.interaction_ids
            act = len(logged & set(ids)) / len(ids) if ids else 0.0
            if abs(act - inst.activation) > 1e-12:
                txn.update("instances", iid, activation=act)


@register("generalization_updater", "path_stats")
class PathStatsUpdater(GeneralizationUpdater):
    """For every node on each classification path: support += 1, plus attribute or edge statistics."""

    def __init__(self, config: Any = None) -> None:
        self.config = config

    def update(self, classifications: list[Classification], ltm: LongTermMemory,
               ctx: ProcessContext, txn: MutationTxn) -> None:
        if not ctx.learn:
            return
        graph = ctx.wm.graph
        pending: dict[tuple[str, str], Any] = {}
        for c in classifications:
            tax = ltm.taxonomy(c.taxonomy)
            coll = "generalizations.object" if c.taxonomy == TaxonomyKind.OBJECT else "generalizations.interaction"
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
        for (coll, gid), st in sorted(pending.items()):
            txn.update(coll, gid, stats=st)
        if pending:
            ctx.tracer.emit(Phase.GENERALIZE, "generalize.updated", refs=[g for _, g in sorted(pending)],
                            supports={g: round(st.support, 3) for (_, g), st in sorted(pending.items())})


def episode_entry(parsed: ParsedEvent, explanation: Explanation, wm: WorkingMemory) -> EpisodeEntry:
    z_after = {}
    for sid in parsed.touched_subentity_ids:
        z = wm.deviations.z_at(sid, parsed.step)
        if z is not None:
            z_after[sid] = z
    return EpisodeEntry(event_id=parsed.event_id, at=parsed.occurred_at or wm.clock, event_type=parsed.event_type,
                        tags=list(parsed.tags), signature=set(parsed.signature), routine=parsed.is_routine(),
                        explanation_id=explanation.id if explanation is not None else None,
                        z_before=dict(parsed.z_before), z_after=z_after,
                        touched_entity_ids=list(parsed.touched_entity_ids))


class LearningTask:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    @property
    def shared(self) -> Any:
        return self.engine.shared

    def run(self, event: GraphUpdateEvent, now: datetime, *, headline: str | None = None,
            proposal_kind: str | None = None) -> LearningResult:
        eng = self.engine
        comp = eng.components
        ctx = eng.context(learn=True, now=now)
        if headline:
            ctx.notes["headline"] = headline
        if proposal_kind:
            ctx.notes["proposal_kind"] = proposal_kind
        with ctx.mutator.begin(cause=event.id, now=now) as txn:
            if now > eng.wm.clock:
                txn.set("wm.clock", now)
            shared = self.shared.run(event, ctx, txn)
            fold = comp["folder"].fold(shared.parsed, shared.analysis, eng.wm, ctx, txn)
            comp["generalization_updater"].update(shared.classifications, eng.ltm, ctx, txn)
            if ctx.initializing:
                frontier = FrontierResult()
            else:
                frontier = comp["frontier"].test(fold, eng.wm, eng.ltm, ctx, txn)
            explanation = comp["explainer"].explain_learning(shared, fold, frontier, ctx)
            txn.add("explanations", explanation)
            ctx.tracer.emit(Phase.EXPLAIN, "explain.stored", refs=[explanation.id, event.id],
                            explanation_id=explanation.id, top_paths=[], text=explanation.text)
            txn.append("wm.episode_buffer", episode_entry(shared.parsed, explanation, eng.wm))
            if not ctx.initializing:
                comp["hypothesis_scorer"].rescore_touched(txn.touched_entities() | set(shared.parsed.touched_entity_ids),
                                                          eng.wm, eng.ltm, ctx, txn)
        events = list(shared.induction.proposal_events) + list(getattr(frontier, "proposal_events", []))
        return LearningResult(shared=shared, fold=fold, frontier=frontier, explanation=explanation,
                              proposal_events=events)


class StructuralApplier:
    """Applies approved structural proposals: parse, classify, and update generalizations through
    the mutator, without a fold (§7.6)."""

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
        with ctx.mutator.begin(cause=event.id, now=now) as txn:
            if now > eng.wm.clock:
                txn.set("wm.clock", now)
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
                comp["generalization_updater"].update(classifications, eng.ltm, ctx, txn)
        return classifications

    def _admit(self, op: Any, ctx: ProcessContext, txn: MutationTxn) -> Classification:
        from axelrod_wm.core.superentity import SuperentityInstance
        from axelrod_wm.memory.patterns import SuperInteractionBuilder

        eng = self.engine
        p = op.pattern
        existing = eng.ltm.patterns.patterns.get(p.id)
        if existing is None:
            txn.add("patterns", p.model_copy(update={"status": SuperentityStatus.ADMITTED, "proposed_at": None}))
        else:
            txn.update("patterns", p.id, status=SuperentityStatus.ADMITTED, proposed_at=None, name=p.name)
        cls = eng.components["classifier"].classify(TaxonomyKind.OBJECT, p.id, True, ctx, txn)
        graph = eng.wm.graph
        if not any(i.pattern_id == p.id for i in graph.instances.values()):
            binding = eng.components["binder"].bind(eng.ltm.patterns.patterns[p.id],
                                                    sorted(set(op.bindings.values())), graph, eng.ltm)
            if binding is not None:
                txn.add("instances", SuperentityInstance(
                    id=txn.new_id("inst"), pattern_id=p.id, bindings=binding.bindings,
                    interaction_ids=binding.interaction_ids, absent_interaction_ids=binding.absent_interaction_ids))
        SuperInteractionBuilder().rebuild(graph, eng.ltm.patterns, txn)
        ctx.tracer.emit(Phase.ABDUCE, "abduce.admitted", refs=[p.id], pattern_id=p.id, path=cls.path)
        return cls

    def _dissolve(self, op: Any, ctx: ProcessContext, txn: MutationTxn) -> None:
        from axelrod_wm.memory.patterns import SuperInteractionBuilder

        eng = self.engine
        if op.pattern_id not in eng.ltm.patterns.patterns:
            return
        txn.update("patterns", op.pattern_id, status=SuperentityStatus.DISSOLVED, proposed_at=None)
        for iid in sorted(eng.wm.graph.instances):
            if eng.wm.graph.instances[iid].pattern_id == op.pattern_id:
                txn.remove("instances", iid)
                ctx.tracer.emit(Phase.PREFILL, "induce.dissolved", refs=[iid, op.pattern_id], instance_id=iid,
                                pattern_id=op.pattern_id, transient=False)
        SuperInteractionBuilder().rebuild(eng.wm.graph, eng.ltm.patterns, txn)

