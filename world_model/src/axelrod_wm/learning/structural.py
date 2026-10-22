"""Structural changes after review (§7.6, §8.8): admitting a superentity (nodes collapse into one
schema), dissolving one (it breaks back into its constituents), retiring structure (an interaction, or an
entity with its values and interactions), and the user's drawn edits. They pass through the same vetting
as market events and commit through the mutator, without a fold.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from axelrod_wm.engine.interfaces import Classification
from axelrod_wm.model.superentity import SuperentityStatus
from axelrod_wm.model.taxonomy import TaxonomyKind
from axelrod_wm.shared.process import build_new_channels
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.events.graph_update import GraphUpdateEvent
    from axelrod_wm.repo.mutator import MutationTxn

PATTERNS = "ltm.object_generalizations.patterns"


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
        with ctx.mutator.begin(cause=event.id, at=now, process="structural",
                               message=f"Structure: {', '.join(op.op for op in event.ops)}") as txn:
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
        from axelrod_wm.memory.long_term import SuperInteractionBuilder
        from axelrod_wm.model.superentity import SuperentityInstance

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
        if p.sub_pattern_ids and not any(i.pattern_id == p.id for i in graph.instances.values()):
            # a composite (Oct 9): its instance holds its parts' instances, their interactions, and the interactions
            # that cross between them
            from axelrod_wm.shared.recognize import interactions_among

            kids = [iid for q in p.sub_pattern_ids for iid, inst in sorted(graph.instances.items())
                    if inst.pattern_id == q and not inst.transient][:len(p.sub_pattern_ids)]
            bindings: dict[str, str] = {}
            held: set[str] = set()
            absent: set[str] = set()
            for k in kids:
                bindings.update(graph.instances[k].bindings)
                held |= set(graph.instances[k].interaction_ids)
                absent |= set(graph.instances[k].absent_interaction_ids)
            bindings.update({m: m for m in op.bindings.values() if m not in bindings.values()})
            members = sorted({m for k in kids for m in graph.members(k)} | set(op.bindings.values()))
            held |= set(interactions_among(members, graph))
            txn.add("wm.graph.instances", SuperentityInstance(
                id=txn.new_id("inst"), pattern_id=p.id, bindings=bindings, interaction_ids=sorted(held),
                absent_interaction_ids=sorted(absent - held), child_instance_ids=kids))
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
        # DECISION (Oct 9): a composite cannot outlive a part; dissolving a part dissolves the composites made of it
        gone = {op.pattern_id}
        grew = True
        while grew:
            grew = False
            for pid, q in og.patterns.items():
                if pid not in gone and q.status == SuperentityStatus.ADMITTED and gone & set(q.sub_pattern_ids):
                    gone.add(pid)
                    grew = True
        for pid in sorted(gone):
            txn.update(PATTERNS, pid, status=SuperentityStatus.DISSOLVED, proposed_at=None)
        for iid in sorted(eng.wm.graph.instances):
            ip = eng.wm.graph.instances[iid].pattern_id
            if ip in gone:
                txn.remove("wm.graph.instances", iid)
                ctx.tracer.emit(Phase.PREFILL, "induce.dissolved", refs=[iid, ip], instance_id=iid,
                                pattern_id=ip, transient=False)
        SuperInteractionBuilder().rebuild(eng.wm.graph, og, txn)
