"""Initialization (Figure 6, "executed once"; §8.13): construction specs, taxonomies, seeds.

The history replay is one long update run (§7.8) driven by the scenario runner, which also caches
the init snapshot.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, ConfigDict

from axelrod_wm.memory.long_term import SuperInteractionBuilder
from axelrod_wm.model.categories import CategoryTag
from axelrod_wm.model.distributions import (
    FAMILIES,
    Beta,
    parse_distribution,
    prior_from_native,
)
from axelrod_wm.model.entity import Entity, EntityKind, Subentity
from axelrod_wm.model.evidence import Evidence, Origin, SourceType
from axelrod_wm.model.ids import entity_of
from axelrod_wm.model.interaction import (
    Direction,
    EdgeDynamics,
    EdgeType,
    Interaction,
    ParameterBinding,
    ParameterForm,
)
from axelrod_wm.model.serialization import canonical_json, sha256_text
from axelrod_wm.model.superentity import (
    PatternRelation,
    RoleSpec,
    SuperentityInstance,
    SuperentityPattern,
    SuperentityStatus,
)
from axelrod_wm.model.taxonomy import (
    AttributeKind,
    AttributeVocabulary,
    Generalization,
    Signature,
    Taxonomy,
    TaxonomyKind,
)
from axelrod_wm.model.temporal import parse_kernel
from axelrod_wm.repo.ledger import LedgerKind

if TYPE_CHECKING:
    from axelrod_wm.engine.engine import Engine
    from axelrod_wm.repo.mutator import MutationTxn

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_PALETTES: dict[str, dict[str, str]] = {
    "h1": {"fill": "#F3E1A6", "line": "#B08F2E"},
    "h2": {"fill": "#F4CDB6", "line": "#C9825A"},
    "h3": {"fill": "#C9D9EA", "line": "#6F93B8"},
    "h4": {"fill": "#E3D9C6", "line": "#9A8C74"},
    "h5": {"fill": "#CFE3CC", "line": "#6E9E72"},
    "h6": {"fill": "#EFCBD6", "line": "#B86A84"},
    "h7": {"fill": "#CBE6E0", "line": "#5E9C8F"},
}


class ConstructionError(ValueError):
    """An invalid construction spec, with a message that names the offending item."""


def resolve_path(p: str | Path) -> Path:
    path = Path(p)
    if path.is_absolute() or path.exists():
        return path
    return REPO_ROOT / path


# ---------------------------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------------------------

class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubentitySpec(_Spec):
    id: str
    name: str
    attribute_kind: str
    unit: str
    family: str | None = None
    prior: dict[str, Any] | None = None
    mean: float | None = None
    scale: float | None = None
    aliases: list[str] = []
    features: dict[str, str] = {}
    obs_noise: float | None = None
    slot: str | None = None          # the kind's default it fills, when its id does not say so (addition)
    slot_of: str | None = None       # set by apply_kind_defaults: the object generalization of that default
    constraint: dict[str, Any] | None = None   # a soft economic bound: {min, max, reason} in native units


class EntitySpec(_Spec):
    id: str
    name: str
    kind: EntityKind
    category_tags: list[CategoryTag]
    aliases: list[str] = []
    features: dict[str, str] = {}
    description: str = ""
    subentities: list[SubentitySpec] = []
    short: str | None = None         # names its default subentities ("Delta jet fuel cost"); else the name
    levels: dict[str, float] = {}    # slot -> typical native level of a default it gets (else the kind's)


class ParameterSpec(_Spec):
    name: str
    moderator: str
    form: ParameterForm = ParameterForm.MULTIPLICATIVE
    coefficient: dict[str, Any]
    threshold: float | None = None


class EvidenceSpec(_Spec):
    source_type: SourceType = SourceType.HUMAN
    excerpt: str | None = None
    strength: float = 0.5
    source_ref: str | None = None


class DynamicsSpec(_Spec):
    effect: dict[str, Any]
    kernel: dict[str, Any]


class InteractionSpec(_Spec):
    id: str
    source: str
    target: str
    label: str
    direction: Direction = Direction.UNIDIRECTIONAL
    edge_type: EdgeType = EdgeType.CAUSAL
    effect: dict[str, Any] | None = None
    kernel: dict[str, Any] | None = None
    existence: dict[str, float] | None = None
    reverse: DynamicsSpec | None = None
    parameters: list[ParameterSpec] = []
    evidence: list[EvidenceSpec] = []
    tags: list[str] = []
    note: str | None = None
    generalization: str | None = None    # its interaction generalization, for links made from a kind's defaults


class ConstructionSpec(_Spec):
    """The pydantic model for entities.yaml and interactions.yaml (§14.1)."""

    decision_variables: list[str] = []
    entities: list[EntitySpec]
    interactions: list[InteractionSpec] = []
    entity_link_labels: dict[str, str] = {}

    @classmethod
    def load(cls, construction_dir: str | Path, taxonomy_dir: str | Path | None = None) -> ConstructionSpec:
        """The spec, with each kind's default subentities and links filled in from the object taxonomy
        (`taxonomy_dir`; else the world's own `taxonomy/` folder if it has one; else the shared data/taxonomy)."""
        d = resolve_path(construction_dir)
        ent = yaml.safe_load((d / "entities.yaml").read_text()) or {}
        inter = yaml.safe_load((d / "interactions.yaml").read_text()) or {}
        data = {"decision_variables": ent.get("decision_variables", []), "entities": ent.get("entities", []),
                "interactions": inter.get("interactions", []),
                "entity_link_labels": inter.get("entity_link_labels", {}) or {}}
        try:
            spec = cls.model_validate(data)
        except Exception as exc:  # pydantic's message names the field
            raise ConstructionError(f"invalid construction spec in {d}: {exc}") from exc
        tax = resolve_path(taxonomy_dir) if taxonomy_dir is not None else world_taxonomy_dir(d)
        objects = tax / "objects.yaml"
        return apply_kind_defaults(spec, objects) if objects.exists() else spec

    def subentity_ids(self) -> set[str]:
        return {s.id for e in self.entities for s in e.subentities}

    def validate_spec(self, vocab: AttributeVocabulary | None = None) -> None:
        """Every edge is binary, directional, and labeled; its endpoints exist; and no two edges
        share the same source, target, and label. Ids and attribute kinds are well formed."""
        ent_ids: set[str] = set()
        subs: set[str] = set()
        for e in self.entities:
            if e.id in ent_ids:
                raise ConstructionError(f"duplicate entity id {e.id!r}")
            ent_ids.add(e.id)
            for s in e.subentities:
                if not s.id.startswith(e.id + "."):
                    raise ConstructionError(f"subentity id {s.id!r} must start with '{e.id}.'")
                if s.id in subs:
                    raise ConstructionError(f"duplicate subentity id {s.id!r}")
                subs.add(s.id)
                if vocab is not None and vocab.kinds and s.attribute_kind not in vocab.kinds:
                    raise ConstructionError(f"subentity {s.id!r}: unknown attribute kind {s.attribute_kind!r}")
                fam = s.family or (s.prior or {}).get("family")
                if fam is not None and fam not in FAMILIES:
                    raise ConstructionError(f"subentity {s.id!r}: unknown family {fam!r}")
                if s.prior is None and s.mean is None and s.scale is None:
                    continue
                if s.scale is not None and s.scale <= 0:
                    raise ConstructionError(f"subentity {s.id!r}: scale must be positive")
        for dv in self.decision_variables:
            if dv not in subs:
                raise ConstructionError(f"decision variable {dv!r} is not a subentity")
        seen_ids: set[str] = set()
        seen_triples: set[tuple[str, str, str]] = set()
        for i in self.interactions:
            if i.id in seen_ids:
                raise ConstructionError(f"duplicate interaction id {i.id!r}")
            seen_ids.add(i.id)
            if not i.label.strip():
                raise ConstructionError(f"interaction {i.id!r} has no label")
            for end, ref in (("source", i.source), ("target", i.target)):
                if ref not in subs:
                    raise ConstructionError(f"interaction {i.id!r}: {end} {ref!r} is not a known subentity")
            if i.source == i.target:
                raise ConstructionError(f"interaction {i.id!r}: source and target are the same subentity")
            triple = (i.source, i.target, i.label)
            if triple in seen_triples:
                raise ConstructionError(f"interaction {i.id!r} duplicates source, target, and label of another edge")
            seen_triples.add(triple)
            if i.direction == Direction.BIDIRECTIONAL and i.reverse is None:
                raise ConstructionError(f"interaction {i.id!r} is bidirectional but has no reverse dynamics")
            for p in i.parameters:
                if p.moderator not in subs:
                    raise ConstructionError(f"interaction {i.id!r}: moderator {p.moderator!r} is not a known subentity")

    def spec_hash(self) -> str:
        return sha256_text(canonical_json(self.model_dump(mode="json")))


# ---------------------------------------------------------------------------------------------
# A kind's defaults (addition)
# ---------------------------------------------------------------------------------------------
# DECISION: the user asked that similar objects visibly have similar subentities. An object
# generalization lists the subentities every instance of it has ("slots") and the typical links among
# them; each instance gets the slots of every kind on its path, root first, then its own subentities.
# One of its own fills a slot when its id ends in the slot's name or it names the slot, and a typical
# link applies to each instance that has both of its ends. Defaults are construction data, so the model
# and the synthetic world are built from the same expanded spec.

class SlotSpec(_Spec):
    slot: str
    name: str                        # generic: "jet fuel cost"; the instance's is "<short> <name>"
    attribute_kind: str
    unit: str
    family: str | None = None
    mean: float                      # typical native level; an entity's `levels` overrides it
    scale: float


class SlotLinkSpec(_Spec):
    source: str                      # a value of the instance (a slot, or the end of its own id); with a dot, any subentity
    target: str
    label: str
    effect: float
    kernel: dict[str, Any]
    generalization: str | None = None


def apply_kind_defaults(spec: ConstructionSpec, objects_path: Path) -> ConstructionSpec:
    """`spec` with every entity's default subentities and links added (see the DECISION above)."""
    raw = yaml.safe_load(objects_path.read_text()) or {}
    nodes = {n["id"]: n for n in raw.get("nodes", [])}
    home = {iid: n["id"] for n in raw.get("nodes", []) for iid in n.get("instances") or []}

    def path(gid: str | None) -> list[str]:
        out: list[str] = []
        while gid is not None and gid in nodes:
            out.append(gid)
            gid = nodes[gid].get("parent")
        return out[::-1]

    try:
        slots = {gid: [SlotSpec.model_validate(s) for s in n.get("defaults") or []] for gid, n in nodes.items()}
        slot_links = {gid: [SlotLinkSpec.model_validate(s) for s in n.get("default_links") or []]
                      for gid, n in nodes.items()}
    except Exception as exc:
        raise ConstructionError(f"invalid defaults in {objects_path.name}: {exc}") from exc
    entities: list[EntitySpec] = []
    kinds_of: dict[str, list[str]] = {}
    for e in spec.entities:
        kinds = [g for g in path(home.get(e.id)) if slots[g] or slot_links[g]]
        if not kinds:
            entities.append(e)
            continue
        kinds_of[e.id] = kinds
        wanted = [(g, s) for g in kinds for s in slots[g]]
        names = {s.slot for _, s in wanted}
        filled: dict[str, SubentitySpec] = {}
        for s in e.subentities:
            key = s.slot or s.id.split(".", 1)[1]
            if key in names and key not in filled:
                filled[key] = s
        subs = []
        for g, sl in wanted:
            s = filled.get(sl.slot) or SubentitySpec(
                id=f"{e.id}.{sl.slot}", name=f"{e.short or e.name} {sl.name}", attribute_kind=sl.attribute_kind,
                unit=sl.unit, family=sl.family, mean=e.levels.get(sl.slot, sl.mean), scale=sl.scale)
            subs.append(s.model_copy(update={"slot": sl.slot, "slot_of": g}))
        taken = {s.id for s in filled.values()}
        subs += [s for s in e.subentities if s.id not in taken]
        entities.append(e.model_copy(update={"subentities": subs}))
    known = {s.id for e in entities for s in e.subentities}
    links = list(spec.interactions)
    pairs = {(i.source, i.target) for i in links}
    applied: dict[tuple[str, int], int] = {}
    for e in entities:
        # an end without a dot names a value of the instance: a slot, or the end of one of its own ids
        mine = {s.id.split(".", 1)[1]: s.id for s in e.subentities} | {s.slot: s.id for s in e.subentities if s.slot}
        for g in kinds_of.get(e.id, []):
            for k, ln in enumerate(slot_links[g]):
                src, tgt = ((end if end in known else None) if "." in end else mine.get(end)
                            for end in (ln.source, ln.target))
                if src is None or tgt is None:
                    continue                     # the link applies to the instances that have both ends
                applied[(g, k)] = applied.get((g, k), 0) + 1
                if (src, tgt) in pairs:
                    continue                     # the entity already has this link, written out
                pairs.add((src, tgt))
                links.append(InteractionSpec(
                    id=f"d-{e.id}-{src.split('.', 1)[1]}-{tgt.split('.', 1)[1]}", source=src, target=tgt,
                    label=ln.label, effect={"mu": ln.effect}, kernel=dict(ln.kernel),
                    tags=["demo_addition", "kind_default"], note=f"default link of {nodes[g]['name']}",
                    generalization=ln.generalization))
    for g in sorted({g for ks in kinds_of.values() for g in ks}):
        for k, ln in enumerate(slot_links[g]):
            if not applied.get((g, k)):
                raise ConstructionError(f"{g}: default link {ln.source} -> {ln.target} applies to no instance")
    return spec.model_copy(update={"entities": entities, "interactions": links})


def world_taxonomy_dir(world_dir: str | Path) -> Path:
    """A world (data/worlds/<name>) may carry its own taxonomy; otherwise it uses the shared one."""
    own = resolve_path(world_dir) / "taxonomy"
    return own if (own / "objects.yaml").exists() else resolve_path("data/taxonomy")


def load_vocabulary(taxonomy_dir: str | Path) -> AttributeVocabulary:
    d = resolve_path(taxonomy_dir)
    raw = yaml.safe_load((d / "attributes.yaml").read_text()) or {}
    kinds = {}
    for name, v in raw.items():
        kinds[name] = AttributeKind(name=name, parent=v.get("parent"), family=v.get("family", "gaussian"))
    for k in kinds.values():
        if k.parent is not None and k.parent not in kinds:
            raise ConstructionError(f"attribute kind {k.name!r}: unknown parent {k.parent!r}")
        if k.family not in FAMILIES:
            raise ConstructionError(f"attribute kind {k.name!r}: unknown family {k.family!r}")
    return AttributeVocabulary(kinds=kinds)


def load_taxonomy(path: str | Path, kind: TaxonomyKind) -> Taxonomy:
    p = resolve_path(path)
    raw = yaml.safe_load(p.read_text()) or {}
    root = raw.get("root")
    nodes: dict[str, Generalization] = {}
    for n in raw.get("nodes", []):
        gid = n["id"]
        if gid in nodes:
            raise ConstructionError(f"{p.name}: duplicate generalization {gid!r}")
        nodes[gid] = Generalization(id=gid, kind=kind, name=n["name"], parent_id=n.get("parent"),
                                    signature=Signature.model_validate(n.get("signature") or {}),
                                    instance_ids=list(n.get("instances") or []), origin=Origin.CONSTRUCTION)
    if root not in nodes:
        raise ConstructionError(f"{p.name}: root {root!r} is not a node")
    for gid, node in nodes.items():
        if gid == root:
            if node.parent_id is not None:
                raise ConstructionError(f"{p.name}: the root {gid!r} must have no parent")
            continue
        if node.parent_id not in nodes:
            raise ConstructionError(f"{p.name}: node {gid!r} has unknown parent {node.parent_id!r}")
        nodes[node.parent_id].child_ids.append(gid)
    return Taxonomy(kind=kind, root_id=root, nodes=nodes)


class PatternSeed(_Spec):
    id: str
    name: str
    palette: str | None = None
    members: list[str]
    interactions: list[str] = []
    absent_interactions: list[str] = []
    rivals: list[str] = []
    support: float = 0.0
    bind: bool = True
    sub_patterns: list[str] = []
    description: str = ""


class FrontierSeed(_Spec):
    earlier: str
    later: str
    lag_days: int = 7
    sign: int = 1
    support: float = 1.0


class SeedFile(_Spec):
    patterns: list[PatternSeed] = []
    super_interaction_labels: list[dict[str, str]] = []
    frontier_seeds: list[FrontierSeed] = []
    palettes: dict[str, dict[str, str]] = {}

    @classmethod
    def load(cls, path: str | Path) -> SeedFile:
        p = resolve_path(path)
        return cls.model_validate(yaml.safe_load(p.read_text()) or {})


# ---------------------------------------------------------------------------------------------
# The initializer
# ---------------------------------------------------------------------------------------------

def _native_prior(s: SubentitySpec, family: str, vocab: AttributeVocabulary) -> tuple[Any, float]:
    """(prior, scale) for a construction subentity."""
    if s.prior is not None:
        data = dict(s.prior)
        data.setdefault("family", family)
        prior = parse_distribution(data)
        if s.scale is not None:
            return prior, float(s.scale)
        _, v = prior.link_moments()
        return prior, float(max(v, 1e-12) ** 0.5)
    scale = float(s.scale) if s.scale is not None else 1.0
    if s.mean is not None:
        return prior_from_native(family, s.mean, scale), scale
    raise ConstructionError(f"subentity {s.id!r} has no prior")


class Initializer:
    """Builds the graph from construction specs (Figure 6 "Initialize")."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # -- construct -------------------------------------------------------------------------
    def construct(self, spec: ConstructionSpec, taxonomy_dir: str | Path, *, start: date | datetime,
                  vocab: AttributeVocabulary | None = None) -> None:
        """Construct entities, set priors, and specify causal edges, with origin=construction (§8.13
        step 1). Day 0 is `start`, the first history day: `wm.last_processed_day` is -1 and `wm.clock`
        is the end of the day before. Every interaction gets its ChannelStates at day 0. Writes
        through the mutator as one ChangeSet with cause "construction"."""
        from axelrod_wm.dynamics.daily import ensure_channel_states

        eng = self.engine
        vocab = vocab or eng.vocab or load_vocabulary(taxonomy_dir)
        if not eng.vocab.kinds:
            eng.vocab = vocab
        spec.validate_spec(vocab)
        day0 = start.date() if isinstance(start, datetime) else start
        clock = datetime.combine(day0 - timedelta(days=1), time(23, 59, 59), tzinfo=UTC)
        obj_tax = load_taxonomy(resolve_path(taxonomy_dir) / "objects.yaml", TaxonomyKind.OBJECT)
        int_tax = load_taxonomy(resolve_path(taxonomy_dir) / "interactions.yaml", TaxonomyKind.INTERACTION)
        obj_home = {iid: gid for gid, n in obj_tax.nodes.items() for iid in n.instance_ids}
        int_home = {iid: gid for gid, n in int_tax.nodes.items() for iid in n.instance_ids}
        # links made from a kind's defaults name their own generalization
        for ispec in spec.interactions:
            gid = ispec.generalization
            if gid is None or ispec.id in int_home:
                continue
            if gid not in int_tax.nodes:
                raise ConstructionError(f"interaction {ispec.id!r}: unknown generalization {gid!r}")
            int_home[ispec.id] = gid
            int_tax.nodes[gid].instance_ids.append(ispec.id)
        with eng.mutator.begin("construction", at=clock) as txn:
            txn.set("wm.clock", clock)
            txn.set("wm.last_processed_day", -1)
            txn.set("wm.deviations.origin_date", day0)
            txn.set("wm.deviations.first_kept_day", 0)
            txn.set("ltm.object_generalizations.taxonomy.root_id", obj_tax.root_id)
            txn.set("ltm.interaction_generalizations.taxonomy.root_id", int_tax.root_id)
            for gid in obj_tax.nodes:
                txn.add("ltm.object_generalizations.taxonomy.nodes", obj_tax.nodes[gid])
            for gid in int_tax.nodes:
                txn.add("ltm.interaction_generalizations.taxonomy.nodes", int_tax.nodes[gid])
            txn.set("wm.decision_variables", list(spec.decision_variables))
            txn.set("wm.graph.entity_link_labels", dict(spec.entity_link_labels))
            for es in spec.entities:
                self._add_entity(txn, es, vocab, obj_home.get(es.id), clock)
            for ispec in spec.interactions:
                self._add_interaction(txn, ispec, int_home.get(ispec.id), clock)
            # internal interactions of each entity
            internal: dict[str, list[str]] = {}
            for ispec in spec.interactions:
                if entity_of(ispec.source) == entity_of(ispec.target):
                    internal.setdefault(entity_of(ispec.source), []).append(ispec.id)
            for eid, ids in sorted(internal.items()):
                txn.update("wm.graph.entities", eid, internal_interaction_ids=ids)
            ctx = eng.context(learn=True, now=clock, processing_day=0)
            for iid in sorted(eng.wm.graph.interactions):
                ensure_channel_states(eng.wm.graph.interactions[iid], eng.wm, ctx, txn, day=0)
        eng.ledger.append(LedgerKind.CONSTRUCTION, {"spec_hash": spec.spec_hash(), "entities": len(spec.entities),
                                                    "subentities": len(spec.subentity_ids()),
                                                    "interactions": len(spec.interactions)},
                          recorded_at=clock)

    def _add_entity(self, txn: MutationTxn, es: EntitySpec, vocab: AttributeVocabulary,
                    gen_id: str | None, now: datetime) -> None:
        sub_ids = []
        for s in es.subentities:
            family = s.family or (s.prior or {}).get("family") or vocab.family(s.attribute_kind)
            prior, scale = _native_prior(s, family, vocab)
            m, _ = prior.link_moments()
            sub = Subentity(id=s.id, entity_id=es.id, name=s.name, attribute_kind=s.attribute_kind, unit=s.unit,
                            aliases=s.aliases, features=s.features, scale=scale, obs_noise=s.obs_noise,
                            prior=prior, posterior=prior, anchor=m, origin=Origin.CONSTRUCTION,
                            prior_source_id="construction", slot=s.slot, slot_of=s.slot_of,
                            constraint=s.constraint)
            txn.add("wm.graph.subentities", sub)
            sub_ids.append(s.id)
        ent = Entity(id=es.id, name=es.name, kind=es.kind, aliases=es.aliases, category_tags=set(es.category_tags),
                     features=es.features, subentity_ids=sub_ids, generalization_id=gen_id,
                     origin=Origin.CONSTRUCTION, created_at=now, description=es.description)
        txn.add("wm.graph.entities", ent)

    def _add_interaction(self, txn: MutationTxn, i: InteractionSpec, gen_id: str | None, now: datetime) -> None:
        eff = dict(i.effect or {"mu": 0.0})
        eff.setdefault("family", "gaussian")
        if eff["family"] == "gaussian":
            eff.setdefault("sigma", 0.15)
        kernel = parse_kernel(i.kernel or {"delay_days": 14, "lag_days": 30, "duration_days": None})
        forward = EdgeDynamics(effect=parse_distribution(eff), kernel=kernel)
        reverse = None
        if i.reverse is not None:
            reff = dict(i.reverse.effect)
            reff.setdefault("family", "gaussian")
            if reff["family"] == "gaussian":
                reff.setdefault("sigma", 0.15)
            reverse = EdgeDynamics(effect=parse_distribution(reff), kernel=parse_kernel(i.reverse.kernel))
        existence = Beta(**(i.existence or {"alpha": 9.0, "beta": 1.0}))
        params = []
        for p in i.parameters:
            coef = dict(p.coefficient)
            coef.setdefault("family", "gaussian")
            params.append(ParameterBinding(name=p.name, moderator_id=p.moderator, form=p.form,
                                           coefficient=parse_distribution(coef), threshold=p.threshold))
        evidence = []
        for ev in i.evidence:
            evidence.append(Evidence(id=txn.new_id("EV"), source_type=ev.source_type, source_ref=ev.source_ref,
                                     excerpt=ev.excerpt, observed_at=now, strength=ev.strength))
        inter = Interaction(id=i.id, source_id=i.source, target_id=i.target, label=i.label, direction=i.direction,
                            edge_type=i.edge_type, origin=Origin.CONSTRUCTION, existence=existence, forward=forward,
                            reverse=reverse, parameters=params, evidence=evidence, generalization_id=gen_id,
                            internal=entity_of(i.source) == entity_of(i.target), tags=list(i.tags), created_at=now,
                            prior_source_id="construction")
        txn.add("wm.graph.interactions", inter)

    # -- seeds -----------------------------------------------------------------------------
    def load_seeds(self, seeds: SeedFile, *, now: datetime) -> list[str]:
        """Seed patterns (origin=seed, status=admitted) and their instances inst-<id> (§14.4)."""
        eng = self.engine
        graph = eng.wm.graph
        og = eng.ltm.object_generalizations
        obj_home = {iid: gid for gid, n in og.taxonomy.nodes.items() for iid in n.instance_ids}
        created = []
        with eng.mutator.begin("seeds", at=now) as txn:
            # a second seed file (a demo's own, on top of its base world's) adds to what the first set
            palettes = dict(DEFAULT_PALETTES)
            palettes.update(getattr(og, "palettes", None) or {})
            palettes.update(seeds.palettes)
            txn.set("ltm.object_generalizations.palettes", palettes)
            labels = dict(getattr(og, "super_interaction_labels", None) or {})
            labels.update({f"{d['source']}->{d['target']}": d["label"] for d in seeds.super_interaction_labels})
            txn.set("ltm.object_generalizations.super_interaction_labels", labels)
            for ps in seeds.patterns:
                for m in ps.members:
                    if m not in graph.entities:
                        raise ConstructionError(f"seed pattern {ps.id!r}: unknown member {m!r}")
                for iid in ps.interactions + ps.absent_interactions:
                    if iid not in graph.interactions:
                        raise ConstructionError(f"seed pattern {ps.id!r}: unknown interaction {iid!r}")
                roles = []
                for m in ps.members:
                    ent = graph.entities[m]
                    kinds = sorted({graph.subentities[s].attribute_kind for s in ent.subentity_ids})
                    roles.append(RoleSpec(name=m, generalization_id=ent.generalization_id or og.taxonomy.root_id,
                                          attribute_kinds=kinds))
                relations = [self._relation(iid, True) for iid in ps.interactions]
                relations += [self._relation(iid, False) for iid in ps.absent_interactions]
                pattern = SuperentityPattern(
                    id=ps.id, name=ps.name, roles=roles, relations=relations, sub_pattern_ids=ps.sub_patterns,
                    support=ps.support, status=SuperentityStatus.ADMITTED, rival_ids=set(ps.rivals),
                    generalization_id=obj_home.get(ps.id), origin=Origin.SEED, palette=ps.palette, created_at=now,
                    description=ps.description,
                    last_seen=None)
                txn.add("ltm.object_generalizations.patterns", pattern)
                created.append(ps.id)
                if ps.bind:
                    # a composite's instance lists its parts' instances, which bind earlier in the file
                    children = [f"inst-{c}" for c in ps.sub_patterns]
                    for c in children:
                        if c not in graph.instances:
                            raise ConstructionError(f"seed pattern {ps.id!r}: part {c[5:]!r} must be a bound seed "
                                                    "listed before it")
                    inst = SuperentityInstance(id=f"inst-{ps.id}", pattern_id=ps.id,
                                               bindings={m: m for m in ps.members},
                                               interaction_ids=list(ps.interactions),
                                               absent_interaction_ids=list(ps.absent_interactions),
                                               child_instance_ids=children)
                    txn.add("wm.graph.instances", inst)
            SuperInteractionBuilder().rebuild(eng.wm.graph, og, txn)
        return created

    def load_frontier_seeds(self, seeds: SeedFile, *, now: datetime) -> list[str]:
        """Frontier seeds become CoMovement entries with seeded=True, each with its hypothesis (§8.13
        step 5). Their corr and response are backfilled from the replayed history."""
        from axelrod_wm.memory.frontier import CoMovement, backfilled, comovement_statement
        from axelrod_wm.model.hypothesis import Hypothesis, HypothesisKind

        eng = self.engine
        cfg = eng.config
        rec = float(cfg.thresholds.recognition)
        created = []
        day = int(eng.wm.last_processed_day)
        with eng.mutator.begin("frontier_seeds", at=now) as txn:
            for fs in seeds.frontier_seeds:
                for sid in (fs.earlier, fs.later):
                    if sid not in eng.wm.graph.subentities:
                        raise ConstructionError(f"frontier seed: unknown subentity {sid!r}")
                cm_id = txn.new_id("CM")
                h_id = txn.new_id("H")
                co = CoMovement(id=cm_id, earlier_id=fs.earlier, later_id=fs.later, lag_days=fs.lag_days,
                                sign=fs.sign, support=fs.support, first_seen=now, last_seen=now, seeded=True,
                                hypothesis_id=h_id, ambiguous_direction=fs.lag_days == 0)
                # non-overlapping windows ending at the last replayed day
                w = int(cfg.frontier.window_days)
                co = backfilled(co, eng.wm.deviations, day + w, w, int(cfg.frontier.backfill_days))
                txn.add("ltm.correlation_frontier.entries", co)
                hyp = Hypothesis(id=h_id, kind=HypothesisKind.INTERACTION_PRESENT,
                                 statement=comovement_statement(eng.wm.graph, fs.earlier, fs.later, fs.sign),
                                 source_id=fs.earlier, target_id=fs.later,
                                 probability=fs.support / (fs.support + rec + 1.0), scored_at=now,
                                 half_life_days=float(cfg.hypotheses.half_life_days), origin=Origin.SEED,
                                 comovement_id=cm_id)
                txn.add("wm.hypotheses", hyp)
                created.append(cm_id)
        return created

    def set_cursors(self, sources: list[str], at: datetime) -> None:
        """Put a cursor for every live source at `at`, so the first live update collects only what is
        published after the history (§8.13 step 5)."""
        eng = self.engine
        with eng.mutator.begin("cursors", at=at) as txn:
            for name in sources:
                txn.put("wm.source_cursors", name, at)

    def _relation(self, interaction_id: str, present: bool) -> PatternRelation:
        graph = self.engine.wm.graph
        inter = graph.interactions[interaction_id]
        src = graph.subentities[inter.source_id]
        tgt = graph.subentities[inter.target_id]
        return PatternRelation(source_role=src.entity_id, source_attr=src.attribute_kind, target_role=tgt.entity_id,
                               target_attr=tgt.attribute_kind, interaction_generalization_id=inter.generalization_id,
                               polarity=inter.polarity(), label=inter.label, present=present)

