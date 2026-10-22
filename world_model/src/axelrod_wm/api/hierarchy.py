"""Nested superentities for the canvas (Oct 22): groups of groups, deterministic, labelled by keywords.

A large model is unreadable as a flat set of entities, so the canvas draws groups at low zoom and reveals their members as
the view closes in (web/js/graph/semantic.js). The groups come from here, and they are a pure function of the model:

1. Similarity between two entities blends three signals, each in [0, 1]:
   - link structure (0.40): the interaction between them, and how alike their neighborhoods are (cosine over weights);
   - co-activation (0.25): how often the superentities that admit one also admit the other (Jaccard over the
     superentity instances each belongs to);
   - kind and sector (0.35): the shared prefix of their concepts in the taxonomy, the same kind, the same sector.
2. Average-linkage agglomerative clustering over that similarity. Entities are indexed by sorted id and ties go to the
   lowest pair of indexes, so the same model gives the same dendrogram.
3. The dendrogram is cut into a hierarchy by size alone: a group with more than LEAF_MAX entities splits (largest part
   first) until it has FANOUT parts, and a part smaller than MIN_CLUSTER is not a group of its own: its entities sit
   directly in the group above.
4. Labels are the top keywords of c-TF-IDF (BERTopic's class-based TF-IDF) over each group's members' names, kinds, and
   sectors, with the group's siblings as the classes, so a label says what sets the group apart from its neighbors.
   They are deterministic: ties break on the word.

An optional step (ClusterLabels) asks a language model, at temperature 0, for a label in place of the keywords. Answers
are cached by a hash of the members' ids, so a label never changes between runs, and with no provider configured nothing
is called. Building the canvas's view only reads that cache; asking is its own request (POST /api/clusters/relabel).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

W_LINK, W_CO, W_ATTR = 0.40, 0.25, 0.35
MIN_ENTITIES = 40       # a model smaller than this is shown flat, as before
LEAF_MAX = 10           # a group of this many entities or fewer holds them directly
FANOUT = 5              # a larger group splits into this many parts (fewer if its parts are small)
MIN_CLUSTER = 3         # a part smaller than this is not a group
N_KEYWORDS = 3
PROMPT_VERSION = "cluster-label-1"
SYSTEM = ("You name a group of related entities in a causal model of financial markets. Answer with a label of two to "
          "four words and nothing else: no quotes, no punctuation at the end.")

STOP = frozenset("""the and for of in on to a an at by with from group corp corporation company inc ltd plc llc co sa ag
nv holdings holding international global market markets index new""".split())
_WORD = re.compile(r"[a-z][a-z0-9&]+")


class Entityish(Protocol):
    id: str
    name: str
    kind: str
    kind_name: str | None
    features: dict[str, Any]
    concept_path: list[str]
    subentity_ids: list[str]


@dataclass(frozen=True)
class Tree:
    """The dendrogram: leaves 0..n-1, then one node per merge. members[v] are leaf indexes, sorted."""

    members: list[tuple[int, ...]]
    kids: list[tuple[int, ...]]

    @property
    def root(self) -> int:
        return len(self.members) - 1


# -- similarity ------------------------------------------------------------------------------------------------
def similarity(ents: Sequence[Entityish], links: Sequence[tuple[str, str, float]],
               groups: Sequence[Sequence[str]]) -> np.ndarray:
    """The n x n blend of link structure, co-activation, and kind or sector, entities in the order given."""
    n = len(ents)
    at = {e.id: i for i, e in enumerate(ents)}
    w = np.zeros((n, n))
    for a, b, s in links:
        if a in at and b in at and a != b:
            i, j = at[a], at[b]
            w[i, j] = w[j, i] = w[i, j] + max(float(s), 0.05)
    top = w.max() if n else 0.0
    direct = w / top if top > 0 else w
    norm = np.sqrt((w * w).sum(axis=1))
    denom = np.outer(norm, norm)
    cos = np.divide(w @ w.T, denom, out=np.zeros((n, n)), where=denom > 0)
    link = 0.5 * direct + 0.5 * cos
    # co-activation: Jaccard over the superentity instances each entity belongs to
    inst = np.zeros((n, len(groups)))
    for g, members in enumerate(groups):
        for m in members:
            if m in at:
                inst[at[m], g] = 1.0
    both = inst @ inst.T
    each = inst.sum(axis=1)
    union = each[:, None] + each[None, :] - both
    co = np.divide(both, union, out=np.zeros((n, n)), where=union > 0)
    attr = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            a, b = ents[i], ents[j]
            pa, pb = a.concept_path, b.concept_path
            shared = 0
            while shared < min(len(pa), len(pb)) and pa[shared] == pb[shared]:
                shared += 1
            prefix = shared / max(len(pa), len(pb), 1)
            sa, sb = a.features.get("sector"), b.features.get("sector")
            attr[i, j] = attr[j, i] = (2 * prefix + float(a.kind == b.kind) + float(sa is not None and sa == sb)) / 4
    s = W_LINK * link + W_CO * co + W_ATTR * attr
    np.fill_diagonal(s, 0.0)
    return np.round(s, 10)


# -- the dendrogram --------------------------------------------------------------------------------------------
def dendrogram(sim: np.ndarray) -> Tree:
    """Average-linkage agglomeration. A merge takes the most similar pair, the lowest indexes first on a tie; the merged
    group lives on in the lower index's slot, with the size-weighted mean similarity (Lance-Williams)."""
    n = len(sim)
    s = sim.astype(float).copy()
    node = list(range(n))                       # slot -> tree node
    size = [1] * n
    live = np.ones(n, dtype=bool)
    members: list[tuple[int, ...]] = [(i,) for i in range(n)]
    kids: list[tuple[int, ...]] = [() for _ in range(n)]
    for _ in range(n - 1):
        mask = live[:, None] & live[None, :]
        cand = np.where(np.triu(mask, 1), s, -np.inf)
        flat = int(np.argmax(cand))
        i, j = divmod(flat, n)
        new = (size[i] * s[i] + size[j] * s[j]) / (size[i] + size[j])
        s[i, :] = new
        s[:, i] = new
        s[i, i] = 0.0
        live[j] = False
        s[j, :] = 0.0
        s[:, j] = 0.0
        members.append(tuple(sorted(members[node[i]] + members[node[j]])))
        kids.append((node[i], node[j]))
        node[i] = len(members) - 1
        size[i] += size[j]
    return Tree(members, kids)


# -- cutting the dendrogram into nested groups ----------------------------------------------------------------
@dataclass
class Group:
    members: tuple[int, ...]
    children: list[Group]
    direct: list[int]               # entities held directly, not in a child group


def _split(tree: Tree, node: int) -> Group:
    members = tree.members[node]
    if len(members) <= LEAF_MAX:
        return Group(members, [], list(members))
    frontier = list(tree.kids[node])
    while len(frontier) < FANOUT:
        big = [f for f in frontier if len(tree.members[f]) > LEAF_MAX]
        if not big:
            break
        pick = max(big, key=lambda f: (len(tree.members[f]), -tree.members[f][0]))
        frontier.remove(pick)
        frontier.extend(tree.kids[pick])
    frontier.sort(key=lambda f: tree.members[f][0])
    out = Group(members, [], [])
    for f in frontier:
        if len(tree.members[f]) < MIN_CLUSTER:
            out.direct.extend(tree.members[f])
        else:
            out.children.append(_split(tree, f))
    out.direct.sort()
    return out


# -- labels ----------------------------------------------------------------------------------------------------
def _stem(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    return w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w


def tokens(e: Entityish) -> list[str]:
    """The words that describe an entity: its name, its kind, and its sector (the last two weigh in twice)."""
    words = _WORD.findall(e.name.lower())
    extra = _WORD.findall(f"{e.kind} {e.kind_name or ''} {e.features.get('sector') or ''}".lower().replace("_", " "))
    return [_stem(w) for w in words + extra * 2 if w not in STOP]


def ctfidf(docs: Sequence[Counter]) -> list[list[tuple[str, float]]]:
    """Class-based TF-IDF: for each class, its words ranked by tf * log(1 + A / total count of the word)."""
    total: Counter = Counter()
    for d in docs:
        total.update(d)
    avg = sum(total.values()) / max(len(docs), 1)
    out = []
    for d in docs:
        scored = [(w, round(c * math.log(1 + avg / total[w]), 12)) for w, c in d.items()]
        out.append(sorted(scored, key=lambda t: (-t[1], t[0])))
    return out


def _keywords(ranked: list[tuple[str, float]], taken: set[str], want: int) -> list[str]:
    """The top words, skipping near-duplicates (banks and banking) and words a sibling's label already uses."""
    out: list[str] = []
    for w, _ in ranked:
        if any(w[:4] == o[:4] for o in out) or w in taken:
            continue
        out.append(w)
        if len(out) == want:
            break
    return out


def _pretty(w: str, shown: dict[str, str]) -> str:
    raw = shown.get(w, w)
    return raw if raw.isupper() and len(raw) <= 5 else raw.capitalize()


def cluster_id(member_ids: Sequence[str]) -> str:
    return "cl-" + hashlib.sha1("|".join(sorted(member_ids)).encode()).hexdigest()[:10]


def build_clusters(ents: Sequence[Entityish], links: Sequence[tuple[str, str, float]],
                   groups: Sequence[Sequence[str]], *, min_entities: int | None = None) -> list[dict]:
    """The nested groups, parents before children, as plain records:
    id, parent (id or None), depth (1 at the top), label, keywords, source ("keywords"), size (entities), subentities,
    children (ids), entity_ids (held directly), members (every entity). A model under `min_entities` has none."""
    ents = sorted(ents, key=lambda e: e.id)
    if len(ents) < (MIN_ENTITIES if min_entities is None else min_entities):
        return []
    tree = dendrogram(similarity(ents, links, groups))
    top = _split(tree, tree.root)
    shown: dict[str, str] = {}
    bag: list[Counter] = []
    for e in ents:
        words = tokens(e)
        for raw_word in re.findall(r"[A-Za-z][A-Za-z0-9&]+", e.name):
            shown.setdefault(_stem(raw_word.lower()), raw_word)
        bag.append(Counter(words))
    ids = [e.id for e in ents]
    out: list[dict] = []

    def walk(g: Group, parent: str | None, depth: int, label: str, kws: list[str]) -> str:
        member_ids = [ids[i] for i in g.members]
        cid = cluster_id(member_ids)
        rec = {"id": cid, "parent": parent, "depth": depth, "label": label, "keywords": kws, "source": "keywords",
               "size": len(g.members), "subentities": sum(len(ents[i].subentity_ids) for i in g.members),
               "children": [], "entity_ids": [ids[i] for i in g.direct], "members": member_ids}
        out.append(rec)
        names = _name_children(g)
        for child, (lab, kw) in zip(g.children, names):
            rec["children"].append(walk(child, cid, depth + 1, lab, kw))
        return cid

    def _name_children(g: Group) -> list[tuple[str, list[str]]]:
        docs = [sum((bag[i] for i in c.members), Counter()) for c in g.children]
        taken: set[str] = set()
        named = []
        for ranked in ctfidf(docs):
            kws = _keywords(ranked, taken, N_KEYWORDS)
            # siblings differ in their words: a word one label took is not repeated by the next
            taken.update(kws[:1])
            named.append((" · ".join(_pretty(w, shown) for w in kws) or "Group", kws))
        return named

    for child, (lab, kw) in zip(top.children, _name_children(top)):
        walk(child, None, 1, lab, kw)
    return out


# -- the optional language-model labels ------------------------------------------------------------------------
class Provider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str) -> str: ...


class Cache(Protocol):
    def cache_get(self, key: str) -> dict | None: ...

    def cache_put(self, key: str, provider: str, model: str, value: dict) -> None: ...


def _digest(obj: Any) -> str:
    from axelrod_ingest.lake.store import digest

    return digest(obj)


class ClusterLabels:
    """Language-model labels for groups, replayed from a cache. `provider` None (the default) means off: nothing is
    called and the keyword labels stand. The cache key is a hash of the member ids (with the provider, model, and
    prompt version), so a group keeps its label across runs and a re-ask costs nothing."""

    def __init__(self, cache: Cache, provider: Provider | None) -> None:
        self.cache = cache
        self.provider = provider

    def key(self, member_ids: Sequence[str]) -> str:
        assert self.provider is not None
        return _digest({"v": PROMPT_VERSION, "provider": self.provider.name, "model": self.provider.model,
                        "members": sorted(member_ids)})

    def apply(self, clusters: list[dict]) -> list[dict]:
        """The clusters with each cached label in place of its keywords (a copy; reads the cache, never the provider)."""
        if self.provider is None:
            return clusters
        out = []
        for c in clusters:
            hit = self.cache.cache_get(self.key(c["members"]))
            out.append({**c, "label": hit["label"], "source": "llm"} if hit else c)
        return out

    def relabel(self, clusters: list[dict], names: dict[str, str]) -> tuple[int, int]:
        """Ask for the labels the cache lacks; returns (new, failed). `names` maps an entity id to its name."""
        if self.provider is None:
            return 0, 0
        done = failed = 0
        for c in clusters:
            key = self.key(c["members"])
            if self.cache.cache_get(key) is not None:
                continue
            user = (f"Members: {', '.join(names.get(m, m) for m in c['members'])}.\n"
                    f"Keywords found by statistics: {', '.join(c['keywords'])}.")
            try:
                raw = self.provider.complete(SYSTEM, user)
            except Exception:
                failed += 1
                continue
            label = raw.strip().splitlines()[0].strip().strip("\"'").rstrip(".") if raw.strip() else ""
            if not label:
                failed += 1
                continue
            self.cache.cache_put(key, self.provider.name, self.provider.model, {"label": label[:60]})
            done += 1
        return done, failed


# -- the view's entry point ------------------------------------------------------------------------------------
_MEMO: OrderedDict[str, list[dict]] = OrderedDict()
_MEMO_MAX = 8
LABELS: ClusterLabels | None = None      # set by the app: the provider (if any) and the replay cache


def clusters_for(ents: Sequence[Entityish], links: Sequence[tuple[str, str, float]],
                 groups: Sequence[Sequence[str]]) -> list[dict]:
    """build_clusters, remembered for the last few models (a view is rebuilt on every change, a hierarchy rarely), then
    any cached language-model labels."""
    ents = sorted(ents, key=lambda e: e.id)
    if len(ents) < MIN_ENTITIES:
        return []
    key = _digest({"e": [[e.id, e.name, e.kind, e.kind_name, sorted(e.features.items()), e.concept_path,
                          len(e.subentity_ids)] for e in ents],
                   "l": sorted((a, b, round(s, 6)) for a, b, s in links),
                   "g": sorted(sorted(g) for g in groups)})
    hit = _MEMO.get(key)
    if hit is None:
        hit = build_clusters(ents, links, groups)
        _MEMO[key] = hit
        while len(_MEMO) > _MEMO_MAX:
            _MEMO.popitem(last=False)
    else:
        _MEMO.move_to_end(key)
    return LABELS.apply(hit) if LABELS is not None else hit
