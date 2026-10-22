"""Nested superentities for the canvas (api/hierarchy.py): the grouping, its labels, the optional language-model names,
and the view that carries them. Synthetic entities only (invented names)."""

from __future__ import annotations

import json
import random
from collections import Counter
from types import SimpleNamespace as NS

import numpy as np
import pytest

from axelrod_wm.api import hierarchy as H

SECTORS = {
    "banking": (["Aurora", "Beacon", "Cobalt", "Dunmore", "Elmstead", "Fairhaven", "Garnet", "Halcyon", "Ironwood",
                 "Juniper", "Kestrel", "Larkspur"], "Bank", "Banks", ("inst", "firm", "bank")),
    "insurance": (["Meridian", "Northgate", "Oakridge", "Pinecrest", "Quarry", "Ravenscar", "Silverton", "Thornby",
                   "Umber", "Vantage", "Westmoor"], "Assurance", "Insurers", ("inst", "firm", "insurer")),
    "energy": (["Amberly", "Brackenfield", "Cedarwood", "Driftwood", "Eastgate", "Foxglove", "Greystone", "Hollin",
                "Ivybridge", "Jasper", "Kingsley"], "Petroleum", "Producers", ("inst", "firm", "producer")),
    "retail": (["Lantern", "Marigold", "Nettle", "Orchard", "Primrose", "Quince", "Rowan", "Saffron", "Tansy",
                "Upland"], "Stores", "Retailers", ("inst", "firm", "retailer")),
}


def entity(eid, name, kind, kind_name, sector, path, subs=3):
    return NS(id=eid, name=name, kind=kind, kind_name=kind_name, features={"sector": sector} if sector else {},
              concept_path=list(path), subentity_ids=[f"{eid}.v{i}" for i in range(subs)])


def world():
    """44 entities in four sectors, dense links inside a sector and a few across, one superentity per sector."""
    ents, by_sector = [], {}
    for sector, (stems, tail, kind_name, path) in SECTORS.items():
        for stem in stems:
            e = entity(f"{sector[:3]}_{stem.lower()}", f"{stem} {tail}", "company", kind_name, sector, path)
            ents.append(e)
            by_sector.setdefault(sector, []).append(e.id)
    links = []
    for ids in by_sector.values():
        for i, a in enumerate(ids):
            for b in ids[i + 1:i + 4]:
                links.append((a, b, 0.6))
    links += [("ban_aurora", "ene_amberly", 0.3), ("ins_meridian", "ret_lantern", 0.2)]
    groups = [ids for ids in by_sector.values()]
    return ents, links, groups, by_sector


def test_a_small_model_has_no_groups():
    ents, links, groups, _ = world()
    assert H.build_clusters(ents[:10], links, groups) == []
    assert H.clusters_for(ents[:10], links, groups) == []
    assert H.build_clusters(ents[:20], links, groups, min_entities=5) != []                # lowered, it groups
    assert H.build_clusters(ents[:10], links, groups, min_entities=5) == []                # but ten fit in one group


def test_the_hierarchy_nests_and_partitions():
    ents, links, groups, _ = world()
    cs = H.build_clusters(ents, links, groups)
    by_id = {c["id"]: c for c in cs}
    assert len(by_id) == len(cs) and cs[0]["parent"] is None
    everyone = {e.id for e in ents}
    for c in cs:
        assert set(c["members"]) <= everyone and c["size"] == len(c["members"]) and c["size"] >= H.MIN_CLUSTER
        assert c["subentities"] == 3 * c["size"] and c["label"] and c["source"] == "keywords"
        parts = [m for k in c["children"] for m in by_id[k]["members"]] + c["entity_ids"]
        assert sorted(parts) == sorted(c["members"])          # the children and the direct entities partition it
        for k in c["children"]:
            assert by_id[k]["parent"] == c["id"] and by_id[k]["depth"] == c["depth"] + 1
        if c["size"] <= H.LEAF_MAX:
            assert not c["children"]
    # a parent comes before its children
    seen = set()
    for c in cs:
        assert c["parent"] is None or c["parent"] in seen
        seen.add(c["id"])
    roots = [c for c in cs if c["parent"] is None]
    assert len(roots) >= 2
    held = Counter(m for c in roots for m in c["members"])
    assert set(held.values()) == {1}                          # a top-level group never shares an entity


def test_the_groups_follow_the_sectors():
    ents, links, groups, by_sector = world()
    sector_of = {i: s for s, ids in by_sector.items() for i in ids}
    cs = H.build_clusters(ents, links, groups)
    leaves = [c for c in cs if not c["children"]]
    pure = sum(Counter(sector_of[m] for m in c["members"]).most_common(1)[0][1] for c in leaves)
    assert pure / sum(c["size"] for c in leaves) >= 0.9
    labels = " ".join(c["label"].lower() for c in cs)
    for word in ("bank", "assurance", "petroleum", "store"):
        assert word in labels


def test_the_same_model_gives_byte_identical_groups_and_labels():
    ents, links, groups, _ = world()
    first = json.dumps(H.build_clusters(ents, links, groups), sort_keys=True)
    rng = random.Random(7)
    for _ in range(3):
        e2, l2, g2 = list(ents), list(links), [list(g) for g in groups]
        rng.shuffle(e2)
        rng.shuffle(l2)
        rng.shuffle(g2)
        for g in g2:
            rng.shuffle(g)
        assert json.dumps(H.build_clusters(e2, l2, g2), sort_keys=True) == first
    assert json.dumps(H.clusters_for(ents, links, groups), sort_keys=True) == first


def test_ties_break_on_the_lowest_pair():
    flat = np.zeros((4, 4))
    tree = H.dendrogram(flat)
    assert tree.kids[4] == (0, 1) and tree.members[4] == (0, 1)          # all equal: the lowest indexes merge first
    assert tree.kids[5] == (4, 2) and tree.members[tree.root] == (0, 1, 2, 3)


def test_similarity_blends_links_co_activation_and_kind():
    ents = [entity("a", "Alpha", "company", "Banks", "banking", ("x", "y")),
            entity("b", "Beta", "company", "Banks", "banking", ("x", "y")),
            entity("c", "Gamma", "idea", None, None, ()),
            entity("d", "Delta", "idea", None, None, ())]
    only_kind = H.similarity(ents, [], [])
    assert only_kind[0, 1] == pytest.approx(H.W_ATTR * 1.0) and only_kind[0, 2] == 0
    assert only_kind[2, 3] == pytest.approx(H.W_ATTR * 0.25)               # the same kind, nothing else
    linked = H.similarity(ents, [("a", "c", 0.5), ("c", "zzz", 1.0), ("a", "a", 1.0)], [["a", "c", "nobody"]])
    assert linked[0, 2] > only_kind[0, 2] and linked[0, 2] == linked[2, 0]
    assert (np.diag(linked) == 0).all()


def test_words_and_class_based_tf_idf():
    e = entity("x", "The Harbor Banks of the Isles", "company", "Central banks", "banking", ())
    toks = H.tokens(e)
    assert "the" not in toks and toks.count("bank") == 1 + 2 and "central" in toks and toks.count("banking") == 2
    assert H._stem("economies") == "economy" and H._stem("glass") == "glass" and H._stem("ox") == "ox"
    docs = [Counter({"bank": 4, "rate": 2}), Counter({"oil": 3, "rate": 2}), Counter()]
    ranked = H.ctfidf(docs)
    assert ranked[0][0][0] == "bank" and ranked[1][0][0] == "oil" and ranked[2] == []
    assert H.ctfidf(docs) == ranked                                        # no randomness anywhere
    # a word both classes share ranks below the one only a class has, whatever the tie order
    tie = H.ctfidf([Counter({"b": 1, "a": 1}), Counter({"c": 1})])
    assert [w for w, _ in tie[0]] == ["a", "b"]


def test_keywords_skip_near_duplicates_and_words_a_sibling_took():
    ranked = [("banking", 3.0), ("bank", 2.5), ("capital", 2.0), ("rates", 1.0), ("fees", 0.5)]
    assert H._keywords(ranked, set(), 3) == ["banking", "capital", "rates"]
    assert H._keywords(ranked, {"capital"}, 3) == ["banking", "rates", "fees"]
    assert H._keywords(ranked, set(), 9) == ["banking", "capital", "rates", "fees"]
    assert H._pretty("ecb", {"ecb": "ECB"}) == "ECB" and H._pretty("bank", {"bank": "Bank"}) == "Bank"
    assert H._pretty("bank", {}) == "Bank" and H._pretty("capital", {"capital": "CAPITAL"}) == "Capital"


def test_a_group_with_no_words_is_still_named():
    ents = [entity(f"e{i:02d}", "The Group", "", None, None, ()) for i in range(12)]
    cs = H.build_clusters(ents, [], [], min_entities=3)
    assert cs and all(c["label"] == "Group" and c["keywords"] == [] for c in cs)


def test_parts_that_are_too_small_to_be_groups_sit_in_the_group_above():
    # a dense block of 12 and two strays: the strays are no group of their own
    block = [entity(f"b{i:02d}", f"Bloc{chr(97 + i)} Bank", "company", "Banks", "banking", ("i", "f", "b")) for i in range(12)]
    strays = [entity("z1", "Zed One", "idea", None, None, ()), entity("z2", "Zed Two", "idea", None, None, ())]
    links = [(a.id, b.id, 0.9) for i, a in enumerate(block) for b in block[i + 1:]]
    cs = H.build_clusters(block + strays, links, [], min_entities=3)
    assert all(c["size"] >= H.MIN_CLUSTER for c in cs)
    held = {m for c in cs for m in c["members"]}
    assert held and not held & {"z1", "z2"}          # the strays are left at the top, in no group


def test_a_larger_model_nests_to_a_second_level():
    ents = [entity(f"e{i:03d}", f"Node{chr(97 + i % 26)}{chr(97 + i // 26)} Firm", "company", "Firms",
                   ["s1", "s2", "s3", "s4", "s5", "s6"][i % 6], ("a", "b")) for i in range(150)]
    cs = H.build_clusters(ents, [], [])
    assert max(c["depth"] for c in cs) >= 2
    ids = {c["id"] for c in cs}
    assert all(k in ids for c in cs for k in c["children"])


class FakeProvider:
    name, model = "fake", "fake-1"

    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def complete(self, system, user):
        self.calls.append(user)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


class DictCache:
    def __init__(self):
        self.rows = {}

    def cache_get(self, key):
        return self.rows.get(key)

    def cache_put(self, key, provider, model, value):
        self.rows[key] = value


def test_language_model_labels_are_off_without_a_provider():
    ents, links, groups, _ = world()
    cs = H.build_clusters(ents, links, groups)
    off = H.ClusterLabels(DictCache(), None)
    assert off.apply(cs) is cs and off.relabel(cs, {}) == (0, 0)


def test_language_model_labels_are_cached_by_the_members_and_never_change():
    ents, links, groups, _ = world()
    cs = H.build_clusters(ents, links, groups)
    names = {e.id: e.name for e in ents}
    answers = ['"Retail and stores."\nbecause', "", RuntimeError("down")] + ["Fine Label"] * (len(cs) - 3)
    prov, cache = FakeProvider(answers), DictCache()
    labels = H.ClusterLabels(cache, prov)
    assert labels.apply(cs) == cs                                        # nothing cached yet: the keywords stand
    done, failed = labels.relabel(cs, names)
    assert (done, failed) == (len(cs) - 2, 2) and len(prov.calls) == len(cs)
    assert "Members:" in prov.calls[0] and "Keywords found by statistics" in prov.calls[0]
    first = labels.apply(cs)
    assert first[0]["label"] == "Retail and stores" and first[0]["source"] == "llm"
    assert first[1]["source"] == "keywords" and first[2]["source"] == "keywords"       # the failures stand as keywords
    assert first[3]["label"] == "Fine Label" and cs[0]["source"] == "keywords"         # a copy; the input is not touched
    # a second ask calls only for the two that failed, and what is cached does not change
    prov.answers = ["Second", "Third"]
    assert labels.relabel(cs, names) == (2, 0) and len(prov.calls) == len(cs) + 2
    again = labels.apply(cs)
    assert again[0]["label"] == "Retail and stores" and again[1]["label"] == "Second"
    # a different model is a different question
    other = FakeProvider(["Other"])
    other.model = "fake-2"
    assert H.ClusterLabels(cache, other).apply(cs) == cs
    assert labels.key(["b", "a"]) == labels.key(["a", "b"])


def test_the_view_builder_remembers_the_last_few_models_and_applies_cached_names(monkeypatch):
    ents, links, groups, _ = world()
    monkeypatch.setattr(H, "_MEMO", H.OrderedDict())
    monkeypatch.setattr(H, "_MEMO_MAX", 2)
    monkeypatch.setattr(H, "LABELS", None)
    built = []
    real = H.build_clusters
    monkeypatch.setattr(H, "build_clusters", lambda *a, **k: built.append(1) or real(*a, **k))
    a = H.clusters_for(ents, links, groups)
    assert H.clusters_for(ents, links, groups) is a and len(built) == 1                   # remembered
    for k in range(3):                                                                      # three other models push it out
        H.clusters_for(ents, [(links[0][0], links[0][1], 0.1 * (k + 1))], groups)
    assert len(H._MEMO) == 2
    H.clusters_for(ents, links, groups)
    assert len(built) == 5
    cache = DictCache()
    labels = H.ClusterLabels(cache, FakeProvider(["Named"]))
    cache.cache_put(labels.key(a[0]["members"]), "fake", "fake-1", {"label": "Named"})
    monkeypatch.setattr(H, "LABELS", labels)
    named = H.clusters_for(ents, links, groups)
    assert named[0]["label"] == "Named" and named[0]["source"] == "llm" and named[1]["source"] == "keywords"
