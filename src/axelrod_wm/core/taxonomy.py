"""Taxonomies and generalizations (§6.9).

Two learned taxonomies (objects and interactions) and a small designer-provided attribute
vocabulary. Features are dicts of string lists; signatures match them.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.distributions import Beta, Distribution, Gaussian, from_link_moments
from axelrod_wm.core.evidence import Origin
from axelrod_wm.core.interaction import EdgeDynamics
from axelrod_wm.core.temporal import KernelSpec, gamma_from_mean

if TYPE_CHECKING:
    from axelrod_wm.core.entity import Entity
    from axelrod_wm.core.graph import CausalGraph
    from axelrod_wm.core.interaction import Interaction
    from axelrod_wm.core.superentity import SuperentityPattern

ATTRIBUTE_KEYS = frozenset({"attribute_kinds", "source_attr", "target_attr"})
DEFAULT_EFFECT_SD = 0.15


class TaxonomyKind(StrEnum):
    OBJECT = "object"
    INTERACTION = "interaction"


class AttributeKind(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    parent: str | None
    family: str                       # default distribution family


class AttributeVocabulary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kinds: dict[str, AttributeKind]

    def ancestors(self, kind: str) -> list[str]:
        """``kind`` and its ancestors, nearest first."""
        out: list[str] = []
        cur: str | None = kind
        seen: set[str] = set()
        while cur is not None and cur in self.kinds and cur not in seen:
            out.append(cur)
            seen.add(cur)
            cur = self.kinds[cur].parent
        if cur is not None and cur not in self.kinds and cur not in seen:
            out.append(cur)
        return out

    def is_a(self, kind: str, ancestor: str) -> bool:
        return ancestor in self.ancestors(kind) if kind in self.kinds else kind == ancestor

    def distance(self, a: str, b: str) -> int:
        """Edges between two kinds through their lowest common ancestor (99 if unrelated)."""
        pa, pb = self.ancestors(a), self.ancestors(b)
        for i, x in enumerate(pa):
            if x in pb:
                return i + pb.index(x)
        return 99

    def family(self, kind: str) -> str:
        k = self.kinds.get(kind)
        return k.family if k is not None else "gaussian"

    def root_of(self, kind: str) -> str:
        anc = self.ancestors(kind)
        return anc[-1] if anc else kind


def _value_ok(key: str, value: str, allowed: list[str], vocab: AttributeVocabulary | None) -> bool:
    if key in ATTRIBUTE_KEYS and vocab is not None:
        return any(vocab.is_a(value, a) for a in allowed)
    return value in allowed


class Signature(BaseModel):
    """Features a member must match. All values are strings.
    required: the key must be present, and the item's value must be one of the listed values.
    any_of:   the key must be present, and at least one of the item's values must be listed.
    The attribute keys ("attribute_kinds", "source_attr", "target_attr") match through
    AttributeVocabulary.is_a, so a listed kind also matches its descendants."""

    model_config = ConfigDict(extra="forbid")

    required: dict[str, list[str]] = {}
    any_of: dict[str, list[str]] = {}

    def is_empty(self) -> bool:
        return not self.required and not self.any_of

    def _key_results(self, features: dict[str, list[str]], vocab: AttributeVocabulary | None,
                     known_only: bool) -> list[bool]:
        results: list[bool] = []
        for key, allowed in self.required.items():
            vals = features.get(key)
            if not vals:
                if not known_only:
                    results.append(False)
                continue
            results.append(all(_value_ok(key, v, allowed, vocab) for v in vals))
        for key, allowed in self.any_of.items():
            vals = features.get(key)
            if not vals:
                if not known_only:
                    results.append(False)
                continue
            results.append(any(_value_ok(key, v, allowed, vocab) for v in vals))
        return results

    def match(self, features: dict[str, list[str]], vocab: AttributeVocabulary) -> float:
        """Fraction of keys (required plus any_of) that hold. An empty signature scores 0."""
        if self.is_empty():
            return 0.0
        res = self._key_results(features, vocab, known_only=False)
        return sum(res) / len(res) if res else 0.0

    def satisfied_by_known(self, features: dict[str, list[str]], vocab: AttributeVocabulary) -> bool:
        """Every key whose feature is known holds, and at least one key is known.
        # DECISION: a signature with no known keys is not vacuously satisfied."""
        if self.is_empty():
            return False
        res = self._key_results(features, vocab, known_only=True)
        return bool(res) and all(res)


class RunningStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: float = 0.0
    mean: float = 0.0
    m2: float = 0.0        # Welford

    def push(self, x: float, w: float = 1.0) -> None:
        if w <= 0 or not math.isfinite(x):
            return
        n_new = self.n + w
        delta = x - self.mean
        self.mean += delta * w / n_new
        self.m2 += w * delta * (x - self.mean)
        self.n = n_new

    def var(self) -> float:
        return self.m2 / self.n if self.n > 0 else 0.0

    def merged(self, other: RunningStats) -> RunningStats:
        if other.n <= 0:
            return self.model_copy()
        if self.n <= 0:
            return other.model_copy()
        n = self.n + other.n
        delta = other.mean - self.mean
        mean = self.mean + delta * other.n / n
        m2 = self.m2 + other.m2 + delta * delta * self.n * other.n / n
        return RunningStats(n=n, mean=mean, m2=m2)


class GeneralizationStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    support: float = 0.0                        # observations classified through this node
    attribute_level: dict[str, RunningStats] = {}    # objects: link-space level per attribute kind
    attribute_scale: dict[str, RunningStats] = {}    # objects: scale per attribute kind
    effect: RunningStats = RunningStats()       # interactions: effect means seen
    existence_alpha: float = 1.0                # interactions: beta pseudo-counts
    existence_beta: float = 1.0
    delay_days: RunningStats = RunningStats()
    lag_days: RunningStats = RunningStats()
    duration_days: RunningStats = RunningStats()
    duration_permanent: float = 0.0             # weight of permanent kernels seen (duration None)

    def merged(self, other: GeneralizationStats) -> GeneralizationStats:
        out = GeneralizationStats(
            support=self.support + other.support,
            effect=self.effect.merged(other.effect),
            existence_alpha=self.existence_alpha + other.existence_alpha - 1.0,
            existence_beta=self.existence_beta + other.existence_beta - 1.0,
            delay_days=self.delay_days.merged(other.delay_days),
            lag_days=self.lag_days.merged(other.lag_days),
            duration_days=self.duration_days.merged(other.duration_days),
            duration_permanent=self.duration_permanent + other.duration_permanent,
        )
        for name in ("attribute_level", "attribute_scale"):
            mine: dict[str, RunningStats] = getattr(self, name)
            theirs: dict[str, RunningStats] = getattr(other, name)
            merged = {k: v.model_copy() for k, v in mine.items()}
            for k, v in theirs.items():
                merged[k] = merged[k].merged(v) if k in merged else v.model_copy()
            setattr(out, name, merged)
        return out


class Generalization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: TaxonomyKind
    name: str
    parent_id: str | None
    child_ids: list[str] = []
    signature: Signature = Signature()
    stats: GeneralizationStats = GeneralizationStats()
    instance_ids: list[str] = []      # objects or interactions attached directly to this node
    origin: Origin = Origin.CONSTRUCTION

    def prior_for_attribute(self, attribute_kind: str, family: str) -> tuple[Distribution, float]:
        """(prior, scale) for a new subentity of this kind, from attribute_level and attribute_scale.
        Raises KeyError when this node has no statistics for the kind."""
        lvl = self.stats.attribute_level.get(attribute_kind)
        if lvl is None or lvl.n <= 0:
            raise KeyError(attribute_kind)
        sc = self.stats.attribute_scale.get(attribute_kind)
        scale = sc.mean if sc is not None and sc.n > 0 and sc.mean > 0 else 1.0
        prior = from_link_moments(family, lvl.mean, lvl.var() + scale * scale)
        return prior, scale

    def has_dynamics(self) -> bool:
        return self.stats.effect.n > 0

    def prior_dynamics(self) -> tuple[EdgeDynamics, Beta]:
        """(dynamics, existence) for a new interaction classified here."""
        st = self.stats
        mu = st.effect.mean if st.effect.n > 0 else 0.0
        sd = math.sqrt(st.effect.var() + DEFAULT_EFFECT_SD**2)
        delay = st.delay_days.mean if st.delay_days.n > 0 else 14.0
        lag = st.lag_days.mean if st.lag_days.n > 0 else 30.0
        permanent = st.duration_permanent >= st.duration_days.n
        duration = None if permanent or st.duration_days.n <= 0 else st.duration_days.mean
        kernel = KernelSpec(delay=gamma_from_mean(delay), lag=gamma_from_mean(lag),
                            duration=gamma_from_mean(duration) if duration is not None else None)
        dyn = EdgeDynamics(effect=Gaussian(mu=mu, sigma=sd), kernel=kernel)
        return dyn, Beta(alpha=max(st.existence_alpha, 1e-3), beta=max(st.existence_beta, 1e-3))


class Taxonomy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TaxonomyKind
    root_id: str
    nodes: dict[str, Generalization]

    def children(self, gen_id: str) -> list[Generalization]:
        return [self.nodes[c] for c in self.nodes[gen_id].child_ids if c in self.nodes]

    def path_to_root(self, gen_id: str) -> list[str]:
        """``gen_id`` first, then its ancestors, ending at the root."""
        out: list[str] = []
        cur: str | None = gen_id
        while cur is not None and cur in self.nodes and cur not in out:
            out.append(cur)
            cur = self.nodes[cur].parent_id
        return out

    def path_from_root(self, gen_id: str) -> list[str]:
        return list(reversed(self.path_to_root(gen_id)))

    def depth(self, gen_id: str) -> int:
        return len(self.path_to_root(gen_id)) - 1

    def deepest_supported(self, path: list[str], recall_threshold: float) -> str:
        """Deepest node on `path` whose support exceeds the recall threshold (the root if none)."""
        best, best_depth = self.root_id, -1
        for gid in path:
            node = self.nodes.get(gid)
            if node is None:
                continue
            d = self.depth(gid)
            if node.stats.support > recall_threshold and d > best_depth:
                best, best_depth = gid, d
        return best

    def instances_under(self, gen_id: str) -> list[str]:
        out: list[str] = []
        stack = [gen_id]
        seen: set[str] = set()
        while stack:
            gid = stack.pop()
            if gid in seen or gid not in self.nodes:
                continue
            seen.add(gid)
            node = self.nodes[gid]
            out.extend(node.instance_ids)
            stack.extend(reversed(node.child_ids))
        return out

    def node_of_instance(self, item_id: str) -> str | None:
        for gid in sorted(self.nodes):
            if item_id in self.nodes[gid].instance_ids:
                return gid
        return None

    def is_under(self, gen_id: str, ancestor_id: str) -> bool:
        return ancestor_id in self.path_to_root(gen_id)


# ---------------------------------------------------------------------------------------------
# Features (§6.9)
# ---------------------------------------------------------------------------------------------

LABEL_SYNONYMS = {
    "increase": {"raises", "lifts", "increases", "sets", "feeds"},
    "decrease": {"cuts", "lowers", "limits", "restricts", "reduces", "erodes"},
}


def label_family(label: str) -> str:
    for word in label.lower().replace(",", " ").split():
        for fam, words in LABEL_SYNONYMS.items():
            if word in words:
                return fam
    return "other"


def features_of_entity(entity: Entity, graph: CausalGraph) -> dict[str, list[str]]:
    feats: dict[str, list[str]] = {"kind": [str(entity.kind)], "object_type": ["entity"]}
    for k, v in sorted(entity.features.items()):
        feats[k] = [v]
    kinds = sorted({graph.subentities[s].attribute_kind for s in entity.subentity_ids
                    if s in graph.subentities})
    if kinds:
        feats["attribute_kinds"] = kinds
    return feats


def features_of_pattern(pattern: SuperentityPattern) -> dict[str, list[str]]:
    feats: dict[str, list[str]] = {"object_type": ["superentity"]}
    roles = sorted({r.generalization_id for r in pattern.roles})
    rels = sorted({r.interaction_generalization_id for r in pattern.relations if r.interaction_generalization_id})
    if roles:
        feats["role_generalizations"] = roles
    if rels:
        feats["relation_generalizations"] = rels
    return feats


def _kv(features: dict[str, str]) -> list[str]:
    return [f"{k}={v}" for k, v in sorted(features.items())]


def features_of_interaction(interaction: Interaction, graph: CausalGraph) -> dict[str, list[str]]:
    src = graph.subentities.get(interaction.source_id)
    tgt = graph.subentities.get(interaction.target_id)
    feats: dict[str, list[str]] = {
        "polarity": [str(interaction.polarity())],
        "label_family": [label_family(interaction.label)],
    }
    for end, sub in (("source", src), ("target", tgt)):
        if sub is None:
            continue
        feats[f"{end}_attr"] = [sub.attribute_kind]
        ent = graph.entities.get(sub.entity_id)
        if ent is not None and ent.generalization_id:
            feats[f"{end}_gen"] = [ent.generalization_id]
        kv = set(_kv(sub.features))
        if ent is not None:
            kv |= set(_kv(ent.features))
        if kv:
            feats[f"{end}_features"] = sorted(kv)
    return feats


def features_of(item: Any, graph: CausalGraph) -> dict[str, list[str]]:
    from axelrod_wm.core.entity import Entity
    from axelrod_wm.core.interaction import Interaction
    from axelrod_wm.core.superentity import SuperentityPattern

    if isinstance(item, Entity):
        return features_of_entity(item, graph)
    if isinstance(item, Interaction):
        return features_of_interaction(item, graph)
    if isinstance(item, SuperentityPattern):
        return features_of_pattern(item)
    raise TypeError(f"no features for {type(item).__name__}")


def derive_signature(instance_features: list[dict[str, list[str]]], kind: TaxonomyKind) -> Signature:
    """Signature for a node given without one, derived from all instances under it (§6.9)."""
    if not instance_features:
        return Signature()
    if kind == TaxonomyKind.OBJECT:
        entity_feats = [f for f in instance_features if f.get("object_type") == ["entity"]]
        pattern_feats = [f for f in instance_features if f.get("object_type") == ["superentity"]]
        required: dict[str, list[str]] = {}
        any_of: dict[str, list[str]] = {}
        if entity_feats:
            required["kind"] = sorted({v for f in entity_feats for v in f.get("kind", [])})
            kinds = sorted({v for f in entity_feats for v in f.get("attribute_kinds", [])})
            if kinds:
                any_of["attribute_kinds"] = kinds
        if pattern_feats and not entity_feats:
            # DECISION: pattern-only nodes derive from role and relation generalizations.
            required["object_type"] = ["superentity"]
            roles = sorted({v for f in pattern_feats for v in f.get("role_generalizations", [])})
            rels = sorted({v for f in pattern_feats for v in f.get("relation_generalizations", [])})
            if roles:
                any_of["role_generalizations"] = roles
            if rels:
                any_of["relation_generalizations"] = rels
        return Signature(required=required, any_of=any_of)
    pols = {v for f in instance_features for v in f.get("polarity", [])}
    required = {"polarity": sorted(pols)} if len(pols) == 1 else {}
    any_of = {}
    src = sorted({v for f in instance_features for v in f.get("source_attr", [])})
    tgt = sorted({v for f in instance_features for v in f.get("target_attr", [])})
    if src:
        any_of["source_attr"] = src
    if tgt:
        any_of["target_attr"] = tgt
    return Signature(required=required, any_of=any_of)


def default_obs_noise(attribute_kind: str, vocab: AttributeVocabulary | None, is_decision: bool = False) -> float:
    """§6.3: 0.05 for kinds under rate and price, 0.25 under sentiment_index, 0.15 otherwise;
    decision variables 0.02."""
    if is_decision:
        return 0.02
    roots = vocab.ancestors(attribute_kind) if vocab is not None else [attribute_kind]
    if "rate" in roots or "price" in roots:
        return 0.05
    if "sentiment_index" in roots:
        return 0.25
    return 0.15
