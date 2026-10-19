"""Schema induction: long-term learning's superentities (§8.8, D9).

Once a day (in the daily distillation) it counts which configurations of entities and interactions were
active together, forms candidate patterns, proposes admissions (nodes collapse into one schema) and
dissolutions (a schema breaks back into its constituents) for review, and finds compositions (schemas
made of schemas). The per-event bind step is recognition (shared/recognize.py).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from axelrod_wm.engine.registry import registry
from axelrod_wm.model.superentity import PatternRelation
from axelrod_wm.shared.recognize import (
    BfsRoleFillingBinder,
    InductionResult,
    PatternBinder,
    PatternRecognizer,
    _vocab_of,
    deepest_supported_up,
    roles_and_relations,
)

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.interfaces import RecallResult
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.model.graph import CausalGraph
    from axelrod_wm.model.superentity import SuperentityPattern
    from axelrod_wm.repo.mutator import MutationTxn
    from axelrod_wm.shared.process import ParsedEvent


class SuperentityInducer(ABC):
    @abstractmethod
    def bind(self, parsed: ParsedEvent, recall: RecallResult, wm: WorkingMemory, ltm: LongTermMemory,
             ctx: ProcessContext, txn: MutationTxn | None) -> InductionResult:
        """During prefill: bind recalled admitted patterns to the event's entities, refresh
        activations, and dissolve instances whose pattern was dissolved or whose edges were
        retired. Bindings made for hypothetical events are transient."""

    @abstractmethod
    def count(self, day: int, wm: WorkingMemory, ltm: LongTermMemory,
              ctx: ProcessContext, txn: MutationTxn) -> InductionResult:
        """At the daily consolidation: count support from the activity of the last
        abduction.window_days, form candidates, propose admissions and dissolutions, and find
        compositions."""


registry("inducer", SuperentityInducer)


# =============================================================================================
# Default implementations
# =============================================================================================

import math  # noqa: E402
from typing import Any  # noqa: E402

import networkx as nx  # noqa: E402

from axelrod_wm.engine.registry import register  # noqa: E402
from axelrod_wm.memory.long_term import SuperInteractionBuilder  # noqa: E402
from axelrod_wm.model.evidence import Origin  # noqa: E402
from axelrod_wm.model.interaction import base_interaction_id  # noqa: E402
from axelrod_wm.model.superentity import (  # noqa: E402
    RoleSpec,
    SuperentityInstance,
    SuperentityPattern,
    SuperentityStatus,
)
from axelrod_wm.model.taxonomy import AttributeVocabulary  # noqa: E402
from axelrod_wm.model.temporal import Bitemporal, TimeState  # noqa: E402
from axelrod_wm.trace import Phase  # noqa: E402

EXTRA_PALETTE = ["#E9DDB5", "#D8E2C8", "#F0D9C4", "#D4DFEA", "#E8D5DF", "#D5E8E4", "#EDE3CC", "#DCD9E6"]
PATTERNS = "ltm.object_generalizations.patterns"
INSTANCES = "wm.graph.instances"
MAX_PATTERN_HISTORY = 260


def relation_tuple(rel: PatternRelation, roles: dict[str, RoleSpec], ltm: LongTermMemory, thr: float) -> tuple:
    otax = ltm.object_generalizations.taxonomy
    itax = ltm.interaction_generalizations.taxonomy
    src_gen = deepest_supported_up(otax, roles[rel.source_role].generalization_id
                                   if rel.source_role in roles else None, thr)
    tgt_gen = deepest_supported_up(otax, roles[rel.target_role].generalization_id
                                   if rel.target_role in roles else None, thr)
    int_gen = deepest_supported_up(itax, rel.interaction_generalization_id, thr)
    return (src_gen, rel.source_attr, int_gen, tgt_gen, rel.target_attr, str(rel.polarity))


def pattern_tuples(p: SuperentityPattern, ltm: LongTermMemory, thr: float) -> set[tuple]:
    roles = {r.name: r for r in p.roles}
    return {relation_tuple(r, roles, ltm, thr) for r in p.relations if r.present}


def absent_tuples(p: SuperentityPattern, ltm: LongTermMemory, thr: float) -> set[tuple]:
    roles = {r.name: r for r in p.roles}
    return {relation_tuple(r, roles, ltm, thr) for r in p.relations if not r.present}


def interaction_tuple(iid: str, graph: CausalGraph, ltm: LongTermMemory, thr: float) -> tuple:
    otax = ltm.object_generalizations.taxonomy
    itax = ltm.interaction_generalizations.taxonomy
    inter = graph.interactions[iid]
    src = graph.subentities[inter.source_id]
    tgt = graph.subentities[inter.target_id]
    src_gen = deepest_supported_up(otax, graph.entities[src.entity_id].generalization_id, thr)
    tgt_gen = deepest_supported_up(otax, graph.entities[tgt.entity_id].generalization_id, thr)
    int_gen = deepest_supported_up(itax, inter.generalization_id, thr)
    return (src_gen, src.attribute_kind, int_gen, tgt_gen, tgt.attribute_kind, str(inter.polarity()))


def _jac(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def _boundary_edges(graph: CausalGraph, a: str, b: str) -> set[str]:
    ma, mb = graph.members(a), graph.members(b)
    out = set()
    for inter in graph.active_interactions():
        for _, s, t, _ in inter.channel_items():
            se, te = graph.subentities[s].entity_id, graph.subentities[t].entity_id
            if (se in ma and se not in mb and te in mb and te not in ma) or (
                    se in mb and se not in ma and te in ma and te not in mb):
                out.add(inter.id)
    return out


def _kernel_span(inter: Any) -> int:
    d, l, _ = inter.forward.kernel.means()
    return max(1, int(math.ceil(d + l)))


def spaced_count(days: list[int], spacing: int) -> int:
    """How many of the (sorted) days count under the evidence-spacing rule."""
    n, last = 0, None
    for d in sorted(days):
        if last is None or d - last >= spacing:
            n += 1
            last = d
    return n


@register("inducer", "co_activation")
class CoActivationInducer(SuperentityInducer):
    def __init__(self, config: Any = None, binder: PatternBinder | None = None, engine: Any = None) -> None:
        self.config = config
        self.engine = engine
        self.binder = binder or BfsRoleFillingBinder(config, engine)
        self.builder = SuperInteractionBuilder()
        self.recognizer = PatternRecognizer(self.binder, engine)

    def bind(self, parsed: ParsedEvent, recall: RecallResult, wm: WorkingMemory, ltm: LongTermMemory,
             ctx: ProcessContext, txn: MutationTxn | None) -> InductionResult:
        """Recognition, per event (shared/recognize.py)."""
        return self.recognizer.bind(parsed, recall, wm, ltm, ctx, txn)

    @property
    def vocab(self) -> AttributeVocabulary:
        return _vocab_of(self.engine)

    # -- count (at the daily consolidation) --------------------------------------------------
    def _active_edges(self, day: int, wm: WorkingMemory, width: int) -> dict[str, Any]:
        """Interaction id -> its latest activity record in the window, for channels whose contribution
        change has the same sign as the target's move over the same window (§8.8 step 1)."""
        graph = wm.graph
        latest: dict[str, Any] = {}
        for r in wm.activity_log.values():
            if r.day <= day - width or r.day > day:
                continue
            cur = latest.get(r.channel_id)
            if cur is None or r.day > cur.day:
                latest[r.channel_id] = r
        active: dict[str, Any] = {}
        for key in sorted(latest):
            r = latest[key]
            iid = base_interaction_id(key)
            inter = graph.interactions.get(iid)
            if inter is None or inter.retired_at is not None:
                continue
            # DECISION: a link that a kind gives every member (an airline's fuel cost squeezes its margin) is
            # what the taxonomy already predicts, so moving along it is no evidence of a new configuration;
            # superentities are induced from the links beyond the kinds' defaults
            if "kind_default" in inter.tags:
                continue
            if r.contribution_change * r.target_move > 0:
                prev = active.get(iid)
                if prev is None or abs(r.contribution_change) > abs(prev.contribution_change):
                    active[iid] = r
        return active

    def _components(self, active: dict[str, Any], wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext,
                    ) -> list[dict]:
        """Steps 2-3: components of the active edges, scored, then the greedy best explanation."""
        graph = wm.graph
        thr = ctx.recall_threshold
        mdl = float(ctx.config.abduction.mdl_lambda)
        g = nx.Graph()
        for iid in sorted(active):
            inter = graph.interactions[iid]
            g.add_edge(inter.source_id, inter.target_id)
        comps = []
        for nodes in sorted((sorted(c) for c in nx.connected_components(g)), key=lambda c: c[0]):
            node_set = set(nodes)
            edges = sorted(i for i in active if graph.interactions[i].source_id in node_set)
            if len(edges) < 2:
                continue
            contrib = sum(abs(active[i].contribution_change) for i in edges)
            moves: dict[str, float] = {}
            for i in edges:
                r = active[i]
                moves[r.target_id or graph.interactions[i].target_id] = abs(r.target_move)
            total = sum(moves.values())
            explained = min(1.0, contrib / total) if total > 1e-9 else 0.0
            comps.append({"edges": edges, "explained": explained, "score": explained - mdl * len(edges),
                          "entities": sorted({graph.subentities[s].entity_id for s in node_set}),
                          "tuples": {interaction_tuple(i, graph, ltm, thr) for i in edges}})
        # DECISION: one configuration per actor a day, but an idea (a Figure 1 entity) may sit in two. An idea
        # holds unrelated values (cross-border trade holds both trade finance and chip exports), so a banking
        # stress component that moves trade finance should not crowd out an export-controls component that
        # moves chip exports. Components never share a value, since they are connected components.
        actor = {e for e, ent in graph.entities.items() if str(ent.kind) in ("agency", "company", "person")}
        kept, used = [], set()
        for c in sorted(comps, key=lambda c: (-c["score"], c["edges"])):
            if c["score"] <= 0 or set(c["entities"]) & used & actor:
                continue
            kept.append(c)
            used |= set(c["entities"])
        return kept

    def count(self, day: int, wm: WorkingMemory, ltm: LongTermMemory,
              ctx: ProcessContext, txn: MutationTxn) -> InductionResult:
        res = InductionResult()
        cfg = ctx.config.abduction
        rec = ctx.recognition
        thr = ctx.recall_threshold
        init = ctx.initializing
        graph = wm.graph
        og = ltm.object_generalizations
        patterns = og.patterns
        dev = wm.deviations
        now = ctx.now
        width = int(cfg.window_days)
        spacing = int(cfg.evidence_spacing_days)
        episode_id = ctx.notes.get("episode_id")
        instances_changed = False
        updater = self.engine.components.get("generalization_updater") if self.engine is not None else None

        active = self._active_edges(day, wm, width)
        comps = self._components(active, wm, ltm, ctx)

        # 8 (first). every pattern's support decays by one day; seeds do not decay during initialization
        factor = 0.5 ** (1.0 / float(cfg.support_half_life_days))
        supports: dict[str, float] = {}
        for pid, p in sorted(patterns.items()):
            if p.status == SuperentityStatus.DISSOLVED:
                continue
            supports[pid] = p.support if (init and p.origin == Origin.SEED) else p.support * factor
        counted: set[str] = set()

        def count_once(pid: str) -> bool:
            """support += 1, at most once per evidence_spacing_days (§8.8 step 5)."""
            p = patterns[pid]
            if pid in counted or (p.last_counted_day is not None and day - p.last_counted_day < spacing):
                return False
            counted.add(pid)
            supports[pid] = supports.get(pid, p.support) + 1.0
            if init:
                txn.update(PATTERNS, pid, last_counted_day=day)
            else:
                txn.update(PATTERNS, pid, last_counted_day=day, counted_days=(list(p.counted_days) + [day])[-52:])
            res.supported_pattern_ids.append(pid)
            if updater is not None and p.generalization_id and hasattr(updater, "update_pattern"):
                updater.update_pattern(pid, ltm, ctx, txn, count_support=True)
            return True

        # 6. evidence of absence (before matching, so that a rival can be suppressed)
        suppressed: set[tuple[str, str]] = set()
        absence_hits: set[str] = set()
        for iid, inst in sorted(graph.instances.items()):
            p = patterns.get(inst.pattern_id)
            if p is None or p.status == SuperentityStatus.DISSOLVED or not inst.absent_interaction_ids:
                continue
            for aid in inst.absent_interaction_ids:
                inter = graph.interactions.get(aid)
                if inter is None:
                    continue
                kw = _kernel_span(inter)
                # DECISION: judge the target over the kernel's span *after* the source moved, so a slow
                # channel is not counted as absent during its own delay.
                if abs(dev.window_change(inter.source_id, day - kw, width)) >= 1.0 and \
                        abs(dev.window_change(inter.target_id, day, kw)) < 0.25:
                    absence_hits.add(p.id)
                    for rid in sorted(p.rival_ids):
                        suppressed.add((rid, aid))
        # DECISION: the symmetric counterpart of evidence of absence, for rival pairs that disagree on
        # a relation's presence: the pattern that asserts the relation gains support when the source
        # moved by at least 1 standard unit and the target then moved the predicted way by at least
        # 0.25 within the kernel's span. That is the evidence that separates them.
        rival_absent: dict[str, set[str]] = {}
        for iid, inst in sorted(graph.instances.items()):
            for aid in inst.absent_interaction_ids:
                rival_absent.setdefault(aid, set()).add(inst.pattern_id)
        for iid, inst in sorted(graph.instances.items()):
            p = patterns.get(inst.pattern_id)
            if p is None or p.status == SuperentityStatus.DISSOLVED or p.id in absence_hits:
                continue
            for pid_iid in inst.interaction_ids:
                rivals = rival_absent.get(pid_iid, set()) & set(p.rival_ids)
                inter = graph.interactions.get(pid_iid)
                if not rivals or inter is None:
                    continue
                kw = _kernel_span(inter)
                sc = dev.window_change(inter.source_id, day - kw, width)
                tc = dev.window_change(inter.target_id, day, kw)
                if abs(sc) >= 1.0 and abs(tc) >= 0.25 and sc * tc * inter.polarity() > 0:
                    absence_hits.add(p.id)
                    break
        for pid in sorted(absence_hits):
            count_once(pid)

        # 5. match or create
        living = [p for _, p in sorted(patterns.items())
                  if p.status != SuperentityStatus.DISSOLVED and not p.sub_pattern_ids]
        tuples_of = {p.id: pattern_tuples(p, ltm, thr) for p in living}
        absent_of = {p.id: absent_tuples(p, ltm, thr) for p in living}
        new_candidates: list[str] = []
        for comp in comps:
            matched = []
            for p in living:
                pt = tuples_of[p.id]
                if not pt:
                    continue
                # DECISION: a component that realizes a relation the pattern says is absent contradicts
                # it; and the subset rule needs at least two relations, or a one-relation pattern would
                # match every component that happens to contain that edge.
                if absent_of[p.id] & comp["tuples"]:
                    continue
                if _jac(pt, comp["tuples"]) >= float(cfg.match_jaccard) or (len(pt) >= 2 and pt <= comp["tuples"]):
                    if init and p.origin != Origin.SEED:
                        continue
                    if any((p.id, e) in suppressed for e in comp["edges"]):
                        continue
                    matched.append(p)
            for p in matched:
                fields: dict[str, Any] = {"last_seen": now}
                if episode_id and episode_id not in p.episode_ids:
                    fields["episode_ids"] = (list(p.episode_ids) + [episode_id])[-50:]
                txn.update(PATTERNS, p.id, **fields)
                own = [graph.instances[i] for i in sorted(graph.instances)
                       if graph.instances[i].pattern_id == p.id and not graph.instances[i].transient]
                if not init and not any(set(comp["entities"]) <= graph.members(i.id) for i in own):
                    b = self.binder.bind(p, comp["entities"], graph, ltm)
                    # DECISION: a binding that an instance of the pattern already holds is that instance
                    # recurring, not a new one; otherwise a component with one extra entity re-binds the
                    # same roles every day and identical instances pile up.
                    if b is not None and not any(dict(i.bindings) == dict(b.bindings) for i in own):
                        iid = txn.new_id("inst")
                        txn.add(INSTANCES, SuperentityInstance(
                            id=iid, pattern_id=p.id, bindings=b.bindings, interaction_ids=b.interaction_ids,
                            absent_interaction_ids=b.absent_interaction_ids))
                        instances_changed = True
                if count_once(p.id):
                    ctx.tracer.emit(Phase.ABDUCE, "abduce.support", refs=[p.id] + comp["entities"], pattern_id=p.id,
                                    support=round(supports[p.id], 3), members=comp["entities"])
            if not matched and not init:
                pid = self._create_candidate(comp, day, episode_id, wm, ltm, ctx, txn)
                new_candidates.append(pid)
                supports[pid] = 1.0
                counted.add(pid)
                instances_changed = True
                # DECISION: later components on the same day can match the new candidate, so one
                # configuration realized twice in a day makes one candidate rather than two (the
                # transaction applies the add at once, so the new pattern is already in `patterns`)
                living.append(patterns[pid])
                tuples_of[pid] = pattern_tuples(patterns[pid], ltm, thr)
                absent_of[pid] = absent_tuples(patterns[pid], ltm, thr)

        # composites earn support when both parts are active across a boundary edge (same spacing)
        if not init:
            active_patterns = {i.pattern_id for i in graph.instances.values() if i.activation > 0 and not i.transient}
            for pid, p in sorted(patterns.items()):
                if not p.sub_pattern_ids or p.status == SuperentityStatus.DISSOLVED:
                    continue
                if not set(p.sub_pattern_ids) <= active_patterns:
                    continue
                inst = next((i for i in graph.instances.values() if i.pattern_id == pid), None)
                if inst is None or len(inst.child_instance_ids) < 2:
                    continue
                a, b = inst.child_instance_ids[:2]
                if a in graph.instances and b in graph.instances and _boundary_edges(graph, a, b) & set(active):
                    count_once(pid)

        # write supports, and a weekly time state with the support
        from axelrod_wm.dynamics.daily import time_state_due

        for pid, s in sorted(supports.items()):
            p = patterns[pid]
            if abs(p.support - s) > 1e-12:
                txn.update(PATTERNS, pid, support=s)
            if time_state_due(p.history, wm, day):
                ts = TimeState(at=Bitemporal(valid_at=dev.day_end(day), recorded_at=now),
                               values={"support": round(s, 6)}, source_event_id=episode_id)
                txn.append_to(PATTERNS, pid, "history", ts, keep_last=MAX_PATTERN_HISTORY)

        if not init:
            for pid, p in sorted(patterns.items()):
                # 7. admission
                if p.status == SuperentityStatus.CANDIDATE and p.support > rec and p.proposed_at is None:
                    self._propose_admission(p, wm, ctx, txn, res)
                # 8. dissolution
                elif p.status == SuperentityStatus.ADMITTED and p.support < float(cfg.dissolve_below) \
                        and p.proposed_at is None:
                    self._propose_dissolution(p, ctx, txn, res)
            # 9. composition
            instances_changed |= self._compose(day, episode_id, active, wm, ltm, ctx, txn, res)
            # 10. rivals
            self._rivals(wm, ltm, txn)
        res.candidate_pattern_ids = new_candidates + [c for c in res.candidate_pattern_ids if c not in new_candidates]
        if instances_changed:
            self.builder.rebuild(graph, og, txn)
        return res

    def _create_candidate(self, comp: dict, day: int, episode_id: str | None, wm: WorkingMemory,
                          ltm: LongTermMemory, ctx: ProcessContext, txn: MutationTxn) -> str:
        graph = wm.graph
        og = ltm.object_generalizations
        roles, relations = roles_and_relations(comp["entities"], comp["edges"], graph, ltm, ctx.recall_threshold)
        top = max(comp["edges"], key=lambda i: (graph.interactions[i].significance_mean(), i))
        ti = graph.interactions[top]
        # DECISION (Oct 9): a learned pattern is named by the kinds it relates, not by the entities it was first seen
        # in: the same pattern binds other members later (Delta in an airline role first filled by SkyBridge), and a
        # name like "Oil → SkyBridge jet fuel cost" would then sit on a hull around Oil and Delta
        tax = og.taxonomy
        kind_of = {r.name: r.generalization_id for r in roles}

        def kind_name(sid: str) -> str:
            eid = graph.subentities[sid].entity_id
            gid = kind_of.get(eid) or graph.entities[eid].generalization_id
            node = tax.nodes.get(gid) if gid else None
            return node.name if node is not None and gid != tax.root_id else graph.entities[eid].name

        def value_word(sid: str) -> str:
            # the value's own name without its owner's ("Delta jet fuel cost" -> "jet fuel cost")
            sub = graph.subentities[sid]
            ent = graph.entities[sub.entity_id]
            low = sub.name.lower()
            for owner in sorted([ent.name, *ent.aliases, ent.name.split(" (")[0], ent.name.split()[0]], key=len, reverse=True):
                if owner and low.startswith(owner.lower() + " "):
                    return sub.name[len(owner) + 1:]
            return sub.name

        name = f"{kind_name(ti.source_id)} {value_word(ti.source_id)} → {kind_name(ti.target_id)} {value_word(ti.target_id)}"
        # DECISION: a candidate named after its strongest edge says how many more relations it has, so
        # two configurations that share that edge do not read as duplicates (a component has two edges or more,
        # one relation each)
        more = len(relations) - 1
        name += f" + {more} more relation{'s' if more > 1 else ''}"
        pid = txn.new_id("pat")
        n_pat = sum(1 for p in og.patterns.values() if p.origin != Origin.SEED)
        palette_key = f"x{n_pat % len(EXTRA_PALETTE) + 1}"
        if palette_key not in og.palettes:
            color = EXTRA_PALETTE[n_pat % len(EXTRA_PALETTE)]
            txn.set("ltm.object_generalizations.palettes",
                    {**og.palettes, palette_key: {"fill": color, "line": "#8A7F70"}})
        pattern = SuperentityPattern(id=pid, name=name, roles=roles, relations=relations, support=1.0,
                                     status=SuperentityStatus.CANDIDATE,
                                     episode_ids=[episode_id] if episode_id else [],
                                     origin=Origin.INFERENCE, palette=palette_key, created_at=ctx.now,
                                     last_seen=ctx.now, last_counted_day=day)
        txn.add(PATTERNS, pattern)
        iid = txn.new_id("inst")
        bindings = {e: e for e in comp["entities"]}
        realized = self.binder.evaluate(pattern, bindings, graph, ltm).interaction_ids \
            if hasattr(self.binder, "evaluate") else list(comp["edges"])
        txn.add(INSTANCES, SuperentityInstance(id=iid, pattern_id=pid, bindings=bindings,
                                               interaction_ids=sorted(set(realized) | set(comp["edges"]))))
        ctx.tracer.emit(Phase.ABDUCE, "abduce.candidate", refs=[pid, iid] + comp["entities"], pattern_id=pid,
                        instance_id=iid, name=name, support=1.0, members=comp["entities"], edges=comp["edges"])
        return pid

    def _propose_admission(self, p: SuperentityPattern, wm: WorkingMemory, ctx: ProcessContext,
                           txn: MutationTxn, res: InductionResult) -> None:
        from axelrod_wm.events.graph_update import EventKind, GraphUpdateEvent, ProposeSuperentity

        inst = next((i for _, i in sorted(wm.graph.instances.items()) if i.pattern_id == p.id), None)
        bindings = dict(inst.bindings) if inst is not None else {}
        ev = GraphUpdateEvent(id=f"GUE-ADMIT-{p.id}", kind=EventKind.REAL, event_type="superentity_admission",
                              occurred_at=ctx.now, recorded_at=ctx.now, produced_by="engine", confidence=0.6,
                              ops=[ProposeSuperentity(pattern=p, bindings=bindings)])
        txn.update(PATTERNS, p.id, proposed_at=ctx.now)
        res.proposal_events.append({"kind": "superentity_admission", "event": ev.model_dump(mode="json"),
                                    "reason": f"support {p.support:.2f} exceeds the recognition threshold"})
        ctx.tracer.emit(Phase.ABDUCE, "abduce.admission_proposed", refs=[p.id] + sorted(set(bindings.values())),
                        pattern_id=p.id, support=round(p.support, 3), members=sorted(set(bindings.values())))

    def _propose_dissolution(self, p: SuperentityPattern, ctx: ProcessContext, txn: MutationTxn,
                             res: InductionResult) -> None:
        from axelrod_wm.events.graph_update import DissolveSuperentity, EventKind, GraphUpdateEvent

        ev = GraphUpdateEvent(id=f"GUE-DISSOLVE-{p.id}-{ctx.now.strftime('%Y%m%d')}", kind=EventKind.REAL,
                              event_type="superentity_dissolution", occurred_at=ctx.now, recorded_at=ctx.now,
                              produced_by="engine", confidence=0.6,
                              ops=[DissolveSuperentity(pattern_id=p.id, reason=f"support fell to {p.support:.2f}")])
        txn.update(PATTERNS, p.id, proposed_at=ctx.now)
        res.proposal_events.append({"kind": "superentity_dissolution", "event": ev.model_dump(mode="json"),
                                    "reason": f"support {p.support:.2f} below the dissolve threshold"})
        ctx.tracer.emit(Phase.ABDUCE, "abduce.dissolution_proposed", refs=[p.id], pattern_id=p.id,
                        support=round(p.support, 3), members=[])

    def _compose(self, day: int, episode_id: str | None, active: dict[str, Any], wm: WorkingMemory,
                 ltm: LongTermMemory, ctx: ProcessContext, txn: MutationTxn, res: InductionResult) -> bool:
        """Step 9: two admitted patterns whose instances were both counted active, under the spacing
        rule, more than `recognition` times, with a boundary edge between them, form a candidate."""
        graph = wm.graph
        og = ltm.object_generalizations
        rec = ctx.recognition
        spacing = int(ctx.config.abduction.evidence_spacing_days)
        admitted = [p for p in og.admitted() if not p.sub_pattern_ids]
        inst_of = {}
        for p in admitted:
            for iid in sorted(graph.instances):
                if graph.instances[iid].pattern_id == p.id and not graph.instances[iid].transient:
                    inst_of[p.id] = iid
                    break
        existing = {tuple(sorted(p.sub_pattern_ids)) for p in og.patterns.values() if p.sub_pattern_ids}
        changed = False
        for i, p in enumerate(admitted):
            for q in admitted[i + 1:]:
                if p.id not in inst_of or q.id not in inst_of:
                    continue
                pair = tuple(sorted((p.id, q.id)))
                if pair in existing or p.id in q.rival_ids:
                    continue
                # DECISION: "both counted active" means count() added support to both on the same day,
                # and only live counts are kept (counted_days), so composites form on screen from what
                # happens after initialization rather than all at once from three years of history.
                together = sorted(set(p.counted_days) & set(q.counted_days))
                if spaced_count(together, spacing) <= rec:
                    continue
                boundary = _boundary_edges(graph, inst_of[p.id], inst_of[q.id])
                if not boundary:
                    continue
                # DECISION: a composite starts like any candidate (support 1) and earns support under
                # the same spacing rule whenever both parts are active across a boundary edge.
                pid = txn.new_id("pat")
                roles = list({r.name: r for r in p.roles + q.roles}.values())
                relations = p.relations + [r for r in q.relations if r not in p.relations]
                comp = SuperentityPattern(id=pid, name=f"{p.name} + {q.name}", roles=roles, relations=relations,
                                          sub_pattern_ids=[p.id, q.id], support=1.0,
                                          status=SuperentityStatus.CANDIDATE, origin=Origin.INFERENCE,
                                          created_at=ctx.now, last_seen=ctx.now, last_counted_day=day,
                                          episode_ids=[episode_id] if episode_id else [])
                txn.add(PATTERNS, comp)
                ip, iq = graph.instances[inst_of[p.id]], graph.instances[inst_of[q.id]]
                iid = txn.new_id("inst")
                txn.add(INSTANCES, SuperentityInstance(
                    id=iid, pattern_id=pid, bindings={**ip.bindings, **iq.bindings},
                    interaction_ids=sorted(set(ip.interaction_ids) | set(iq.interaction_ids) | boundary),
                    absent_interaction_ids=sorted(set(ip.absent_interaction_ids) | set(iq.absent_interaction_ids)),
                    child_instance_ids=[ip.id, iq.id]))
                existing.add(pair)
                changed = True
                res.candidate_pattern_ids.append(pid)
                ctx.tracer.emit(Phase.ABDUCE, "abduce.candidate", refs=[pid, iid, p.id, q.id], pattern_id=pid,
                                instance_id=iid, name=comp.name, support=1.0, composite=True,
                                members=sorted(graph.members(ip.id) | graph.members(iq.id)))
        return changed

    def _rivals(self, wm: WorkingMemory, ltm: LongTermMemory, txn: MutationTxn) -> None:
        graph = wm.graph
        patterns = ltm.object_generalizations.patterns
        by_members: dict[tuple[str, ...], list[str]] = {}
        for iid in sorted(graph.instances):
            inst = graph.instances[iid]
            if inst.transient:
                continue
            by_members.setdefault(tuple(sorted(graph.members(iid))), []).append(inst.pattern_id)
        for _, pids in sorted(by_members.items()):
            pids = sorted(set(pids))
            for i, a in enumerate(pids):
                for b in pids[i + 1:]:
                    pa, pb = patterns.get(a), patterns.get(b)
                    if pa is None or pb is None or b in pa.rival_ids:
                        continue
                    ra = {(r.source_role, r.source_attr, r.target_role, r.target_attr): (r.present, r.polarity)
                          for r in pa.relations}
                    rb = {(r.source_role, r.source_attr, r.target_role, r.target_attr): (r.present, r.polarity)
                          for r in pb.relations}
                    if any(k in rb and rb[k] != v for k, v in ra.items()):
                        txn.update(PATTERNS, a, rival_ids=set(pa.rival_ids) | {b})
                        txn.update(PATTERNS, b, rival_ids=set(pb.rival_ids) | {a})
