"""Classify: sort objects and interactions down their taxonomies (§8.4.2) and grow them (§6.9)."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from axelrod_wm.core.distributions import Gaussian, from_link_moments
from axelrod_wm.core.entity import Entity
from axelrod_wm.core.evidence import Origin
from axelrod_wm.core.ids import slugify
from axelrod_wm.core.interaction import EdgeDynamics
from axelrod_wm.core.taxonomy import (
    Generalization,
    Signature,
    Taxonomy,
    TaxonomyKind,
    derive_signature,
    features_of,
)
from axelrod_wm.engine.interfaces import Classification, Classifier, TaxonomyGrower
from axelrod_wm.engine.registry import register
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import MutationTxn
    from axelrod_wm.core.graph import CausalGraph
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.memory.long_term import LongTermMemory


def collection_for(kind: TaxonomyKind) -> str:
    return "generalizations.object" if kind == TaxonomyKind.OBJECT else "generalizations.interaction"


def item_of(kind: TaxonomyKind, item_id: str, graph: CausalGraph, ltm: LongTermMemory) -> Any:
    if kind == TaxonomyKind.INTERACTION:
        return graph.interactions[item_id]
    if item_id in graph.entities:
        return graph.entities[item_id]
    return ltm.patterns.patterns[item_id]


def item_features(kind: TaxonomyKind, item_id: str, graph: CausalGraph, ltm: LongTermMemory) -> dict[str, list[str]]:
    try:
        return features_of(item_of(kind, item_id, graph, ltm), graph)
    except KeyError:
        return {}


def node_signature(tax: Taxonomy, gen_id: str, graph: CausalGraph, ltm: LongTermMemory) -> Signature:
    """The node's signature, or one derived from all instances under it (§6.9)."""
    node = tax.nodes[gen_id]
    if not node.signature.is_empty():
        return node.signature
    feats = [item_features(tax.kind, iid, graph, ltm) for iid in tax.instances_under(gen_id)]
    return derive_signature([f for f in feats if f], tax.kind)


def descend(tax: Taxonomy, feats: dict[str, list[str]], graph: CausalGraph, ltm: LongTermMemory,
            start: str | None = None, min_score: float = 0.5) -> list[str]:
    """Greedy descent: argmax over children of signature.match (ties: support, then id)."""
    node = start or tax.root_id
    path = tax.path_from_root(node)
    while tax.nodes[node].child_ids:
        best: tuple[float, float, str] | None = None
        for child in tax.children(node):
            score = node_signature(tax, child.id, graph, ltm).match(feats, ltm.attributes)
            key = (score, child.stats.support, child.id)
            if best is None or key[0] > best[0] or (key[0] == best[0] and (key[1] > best[1] or (
                    key[1] == best[1] and key[2] < best[2]))):
                best = key
        if best is None or best[0] < min_score:
            break
        node = best[2]
        path.append(node)
    return path


@register("classifier", "taxonomy_descent")
class TaxonomyDescentClassifier(Classifier):
    def __init__(self, config: Any = None, taxonomy_grower: TaxonomyGrower | None = None) -> None:
        self.config = config
        self.grower = taxonomy_grower

    def classify(self, taxonomy: TaxonomyKind, item_id: str, is_new: bool,
                 ctx: ProcessContext, txn: MutationTxn | None) -> Classification:
        wm, ltm = ctx.wm, ctx.ltm
        graph = wm.graph
        tax = ltm.taxonomy(taxonomy)
        item = item_of(taxonomy, item_id, graph, ltm)
        stored = getattr(item, "generalization_id", None)
        created: list[str] = []
        if not is_new and stored in tax.nodes:
            path = tax.path_from_root(stored)
        else:
            feats = features_of(item, graph)
            path = descend(tax, feats, graph, ltm)
            node = path[-1]
            self._attach(taxonomy, item_id, node, ctx, txn)
        prior_source = tax.deepest_supported(path, ctx.recall_threshold)
        if taxonomy == TaxonomyKind.OBJECT and isinstance(item, Entity):
            self._fill_subentities(item, path, ctx, txn)
        elif taxonomy == TaxonomyKind.INTERACTION and is_new:
            self._fill_interaction(item_id, prior_source, ctx, txn)
        if ctx.learn and txn is not None and is_new and self.grower is not None:
            created = self.grower.maybe_split(tax, path[-1], ctx, txn)
        ctx.tracer.emit(Phase.CLASSIFY, "classify.path", refs=[item_id] + path, item_id=item_id,
                        taxonomy=str(taxonomy), path=path, prior_source=prior_source, is_new=is_new)
        return Classification(item_id=item_id, taxonomy=taxonomy, path=path, prior_source_id=prior_source,
                              created_generalization_ids=created, is_new=is_new)

    # -- writes ----------------------------------------------------------------------------
    def _attach(self, kind: TaxonomyKind, item_id: str, node: str, ctx: ProcessContext,
                txn: MutationTxn | None) -> None:
        graph = ctx.wm.graph
        coll = {TaxonomyKind.INTERACTION: "interactions"}.get(kind)
        if coll is None:
            coll = "entities" if item_id in graph.entities else "patterns"
        if txn is None:
            if ctx.overlay is not None and coll in ("entities", "interactions"):
                target = ctx.overlay.graph.entities if coll == "entities" else ctx.overlay.graph.interactions
                target[item_id] = target[item_id].model_copy(update={"generalization_id": node})
            return
        tax = ctx.ltm.taxonomy(kind)
        for gid, n in sorted(tax.nodes.items()):
            if item_id in n.instance_ids and gid != node:
                txn.update(collection_for(kind), gid, instance_ids=[i for i in n.instance_ids if i != item_id])
        if item_id not in tax.nodes[node].instance_ids:
            txn.update(collection_for(kind), node, instance_ids=list(tax.nodes[node].instance_ids) + [item_id])
        txn.update(coll, item_id, generalization_id=node)

    def _fill_subentities(self, entity: Entity, path: list[str], ctx: ProcessContext,
                          txn: MutationTxn | None) -> None:
        """Inheritance for new subentities (§8.4.2), filling only what the op left as None."""
        provided: dict[str, list[str]] = ctx.notes.get("new_subentities", {})
        graph = ctx.wm.graph
        ltm = ctx.ltm
        tax = ltm.object_taxonomy
        filled: set[str] = ctx.notes.setdefault("filled_subentities", set())
        for sid in entity.subentity_ids:
            if sid not in provided or sid in filled or sid not in graph.subentities:
                continue
            filled.add(sid)
            given = set(provided[sid])
            sub = graph.subentities[sid]
            family = sub.posterior.family if "prior" in given or "family" in given else ltm.attributes.family(sub.attribute_kind)
            prior, scale, source = None, None, None
            # 2. the entity's generalization: deepest supported node with statistics for the kind
            for gid in reversed(path):
                node = tax.nodes.get(gid)
                if node is None or node.stats.support <= ctx.recall_threshold:
                    continue
                try:
                    prior, scale = node.prior_for_attribute(sub.attribute_kind, family)
                    source = gid
                    break
                except KeyError:
                    continue
            # 3. the mean over other subentities with the same attribute kind
            if prior is None:
                peers = [s for s in graph.subentities.values()
                         if s.attribute_kind == sub.attribute_kind and s.id != sid and s.id not in provided]
                if peers:
                    ms = [p.posterior.link_moments()[0] for p in peers]
                    sc = sum(p.scale for p in peers) / len(peers)
                    mean = sum(ms) / len(ms)
                    var = sum((m - mean) ** 2 for m in ms) / len(ms) + sc * sc
                    prior, scale, source = from_link_moments(family, mean, var), sc, "graph"
            # 4. the vocabulary family with a scale of 1
            if prior is None:
                prior, scale, source = from_link_moments(family, 0.0, 1.0), 1.0, "vocabulary"
            fields: dict[str, Any] = {}
            if "prior" not in given:
                fields["prior"] = prior
                fields["posterior"] = prior
            if "scale" not in given:
                fields["scale"] = float(scale)
            final_prior = fields.get("prior", sub.prior)
            fields["anchor"] = final_prior.link_moments()[0]
            fields["prior_source_id"] = source if "prior" not in given else "op"
            if txn is not None:
                txn.update("subentities", sid, **fields)
            elif ctx.overlay is not None:
                ctx.overlay.graph.subentities[sid] = sub.model_copy(update=fields)

    def _fill_interaction(self, iid: str, prior_source: str, ctx: ProcessContext, txn: MutationTxn | None) -> None:
        provided: dict[str, list[str]] = ctx.notes.get("new_interactions", {})
        given = set(provided.get(iid, []))
        tax = ctx.ltm.interaction_taxonomy
        node = tax.nodes[prior_source]
        dyn, existence = node.prior_dynamics()
        inter = ctx.wm.graph.interactions[iid]
        polarity = ctx.notes.get("polarity", {}).get(iid)
        fields: dict[str, Any] = {"prior_source_id": prior_source}
        if "dynamics" not in given:
            mu = dyn.effect.mean()
            if polarity is not None:
                # DECISION: an inherited effect takes the op's polarity, with magnitude at least 0.1.
                mu = float(polarity) * max(abs(mu), 0.1)
            fields["forward"] = EdgeDynamics(effect=Gaussian(mu=mu, sigma=dyn.effect.sd()), kernel=dyn.kernel)
            if inter.direction == "bidirectional" and "reverse" not in given:
                fields["reverse"] = fields["forward"]
        if "existence" not in given:
            fields["existence"] = existence
        if txn is not None:
            txn.update("interactions", iid, **fields)
        elif ctx.overlay is not None:
            ctx.overlay.graph.interactions[iid] = inter.model_copy(update=fields)


@register("taxonomy_grower", "shared_feature_split")
class SplitOnSharedFeatureGrower(TaxonomyGrower):
    """When at least recognition + 1 direct instances share a feature value that none of the other
    children have, create a child generalization for them (§6.9).

    # DECISION: objects split on keys of their `features` dict (region, function, sector, ...),
    # interactions on source_features/target_features. Kind, attribute kinds, and object type are
    # never split on, and a split must leave at least one instance at the parent.
    """

    OBJECT_EXCLUDE = frozenset({"kind", "object_type", "attribute_kinds", "role_generalizations",
                                "relation_generalizations"})
    INTERACTION_KEYS = frozenset({"source_features", "target_features"})

    def __init__(self, config: Any = None) -> None:
        self.config = config

    def _keys(self, kind: TaxonomyKind, feats: dict[str, list[str]]) -> list[tuple[str, str]]:
        out = []
        for k, vals in sorted(feats.items()):
            if kind == TaxonomyKind.OBJECT and k in self.OBJECT_EXCLUDE:
                continue
            if kind == TaxonomyKind.INTERACTION and k not in self.INTERACTION_KEYS:
                continue
            for v in vals:
                out.append((k, v))
        return out

    def maybe_split(self, taxonomy: Taxonomy, gen_id: str, ctx: ProcessContext, txn: MutationTxn) -> list[str]:
        node = taxonomy.nodes.get(gen_id)
        rec = ctx.recognition
        if node is None or len(node.instance_ids) < rec + 1:
            return []
        graph, ltm = ctx.wm.graph, ctx.ltm
        counts: Counter[tuple[str, str]] = Counter()
        members: dict[tuple[str, str], list[str]] = {}
        for iid in node.instance_ids:
            for kv in self._keys(taxonomy.kind, item_features(taxonomy.kind, iid, graph, ltm)):
                counts[kv] += 1
                members.setdefault(kv, []).append(iid)
        existing = set()
        for child in taxonomy.children(gen_id):
            for k, vals in child.signature.required.items():
                for v in vals:
                    existing.add((k, v))
        candidates = [(n, kv) for kv, n in counts.items()
                      if n >= rec + 1 and n < len(node.instance_ids) and kv not in existing]
        if not candidates:
            return []
        candidates.sort(key=lambda x: (-x[0], x[1]))
        _, (key, value) = candidates[0]
        group = sorted(members[(key, value)])
        prefix = "gen:obj:" if taxonomy.kind == TaxonomyKind.OBJECT else "gen:int:"
        tail = gen_id.split(":")[-1]
        new_id = f"{prefix}{tail}__{slugify(key)}_{slugify(value)}"
        k = 2
        while new_id in taxonomy.nodes:
            new_id = f"{prefix}{tail}__{slugify(key)}_{slugify(value)}_{k}"
            k += 1
        share = len(group) / max(len(node.instance_ids), 1)
        stats = node.stats.model_copy(deep=True)
        stats.support = node.stats.support * share
        child = Generalization(id=new_id, kind=taxonomy.kind, name=f"{node.name} ({key}={value})", parent_id=gen_id,
                               signature=Signature(required={key: [value]}), stats=stats, instance_ids=group,
                               origin=Origin.INFERENCE)
        coll = collection_for(taxonomy.kind)
        txn.add(coll, child)
        txn.update(coll, gen_id, child_ids=list(node.child_ids) + [new_id],
                   instance_ids=[i for i in node.instance_ids if i not in group])
        for iid in group:
            if taxonomy.kind == TaxonomyKind.INTERACTION:
                txn.update("interactions", iid, generalization_id=new_id)
            elif iid in graph.entities:
                txn.update("entities", iid, generalization_id=new_id)
            elif iid in ltm.patterns.patterns:
                txn.update("patterns", iid, generalization_id=new_id)
        ctx.tracer.emit(Phase.GENERALIZE, "generalize.split", refs=[gen_id, new_id], parent=gen_id, child=new_id,
                        feature=f"{key}={value}", instances=group)
        return [new_id]


@register("taxonomy_grower", "none")
class NoGrower(TaxonomyGrower):
    def __init__(self, config: Any = None) -> None:
        self.config = config

    def maybe_split(self, taxonomy: Taxonomy, gen_id: str, ctx: ProcessContext, txn: MutationTxn) -> list[str]:
        return []

