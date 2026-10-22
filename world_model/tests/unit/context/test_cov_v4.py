"""The v4.1.4 context export (context/v4.py) on a small hand-built model: the domain pack's companies, edge vocabulary,
relationships, clusters, search scopes, caveats, and paths; the evidence pack; the forecast record; and the manifest."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace as NS

from axelrod_wm.context import v4

T0 = datetime(2026, 10, 1, tzinfo=UTC)


class D:
    """A distribution stub: mean, sd, and a 90% range, or one that cannot say."""

    def __init__(self, mean=None, sd=0.1, lo=None, hi=None):
        self._m, self._s, self._lo, self._hi = mean, sd, lo, hi

    def mean(self):
        if self._m is None:
            raise ValueError("no mean")
        return self._m

    def sd(self):
        if self._m is None:
            raise ValueError("no sd")
        return self._s

    def quantile(self, q):
        v = self._lo if q < 0.5 else self._hi
        if v is None:
            raise ValueError("no quantile")
        return v


def kernel(delay=3.0, lag=10.0, duration=None):
    return NS(delay=D(delay), lag=D(lag), duration=None if duration is None else D(duration))


def inter(iid, src, tgt, effect, *, gen="gen:int:a", lo=None, hi=None, p=0.9, evidence=1, retired=None,
          origin="construction", dur=None):
    return NS(id=iid, source_id=src, target_id=tgt, retired_at=retired, label="moves", generalization_id=gen,
              forward=NS(effect=D(effect, lo=lo, hi=hi), kernel=kernel(duration=dur)), existence=D(p),
              evidence=[NS(observed_at=T0)] * evidence, evidence_dropped=0, created_at=T0, origin=origin,
              quantified=True, calibration="calibrated", edge_type="causal", transition=None, fixed=False, identity=None,
              state=None, note=None,
              polarity=lambda: 1 if effect >= 0 else -1)


def pattern(pid, name, status="admitted", subs=()):
    return NS(id=pid, name=name, description="d", status=status, sub_pattern_ids=list(subs), support=3.0,
              track_record=NS(hits=2, misses=1))


def sub(sid, name, kind, constraint=None, posterior=None, observed=False):
    return NS(id=sid, entity_id=sid.split(".")[0], name=name, attribute_kind=kind, unit="usd", observed=observed,
              posterior=posterior or D(1.23456, 0.5, 1.0, 1.5), constraint=constraint)


class Tax:
    def __init__(self, nodes, paths):
        self.root_id = "root"
        self.nodes = {k: NS(name=v) for k, v in nodes.items()}
        self.paths = paths

    def path_from_root(self, gid):
        return self.paths[gid]


def ent(eid, name, kind, aliases=(), gen=None, features=None):
    return NS(id=eid, name=name, kind=kind, aliases=list(aliases), generalization_id=gen, features=features or {},
              description=f"{name} desc", subentity_ids=[])


def world():
    otax = Tax({"root": "Everything", "inst": "Institutions", "cos": "Companies", "tech": "Technology",
                "soft": "Software", "mkt": "Markets", "cmd": "Commodities"},
               {"soft": ["root", "inst", "cos", "tech", "soft"], "cmd": ["root", "mkt", "cmd"]})
    itax = Tax({"gen:int:a": "Cost pass-through (input prices)"}, {})
    ents = {"acme": ent("acme", "Acme", "company", ["ACME", "Acme Corp"], "soft", {"region": "US", "sector": "tech"}),
            "beta": ent("beta", "Beta Holdings", "company", ["8766 JP"]),
            "gamma": ent("gamma", "Gamma", "company"),
            "oil": ent("oil", "Oil", "commodity", ["crude"], "cmd"),
            "fed": ent("fed", "Fed", "central_bank", [], None, {"sector": "policy_rates"})}
    subs = {s.id: s for s in [
        sub("acme.sales", "Acme sales", "revenue", constraint=NS(reason="", min=0.0, max=None), observed=True),
        sub("acme.cost", "Acme cost", "cost"),
        sub("beta.sales", "Beta sales", "revenue", constraint=NS(reason="floor", min=1.0, max=2.0)),
        sub("oil.price", "Oil price", "price", posterior=D(None)),
        sub("fed.rate", "Fed rate", "rate")]}
    for s in subs.values():
        ents[s.entity_id].subentity_ids.append(s.id)
    ints = {i.id: i for i in [
        inter("e1", "oil.price", "acme.sales", 0.4, lo=0.1, hi=0.7),
        inter("e2", "oil.price", "beta.sales", -0.3, lo=-0.5, hi=0.1, p=0.6, evidence=0, origin="import"),
        inter("e3", "oil.price", "acme.cost", 0.2, evidence=0, dur=30.0),
        inter("e3b", "oil.price", "acme.cost", 0.25, evidence=0),
        inter("e4", "fed.rate", "oil.price", -0.2, gen=None, p=0.3),
        inter("e5", "acme.sales", "fed.rate", 0.1, gen="gen:int:unknown_concept", lo=-0.1, hi=0.3),
        inter("e6", "oil.price", "acme.sales", 0.1, retired=T0),
        inter("e7", "oil.price", "nowhere.z", 0.1),
        inter("e8", "oil.price", "beta.sales", 0.0, p=0.95)]}
    instances = {
        "i1": NS(pattern_id="P1", bindings={"firm": "acme", "peer": "beta", "lost": "zzz", "again": "acme"},
                 interaction_ids=["e2", "e1", "gone", "e6"]),
        "i2": NS(pattern_id="P2", bindings={"bank": "fed"}, interaction_ids=[]),
        "i3": NS(pattern_id="P3", bindings={"firm": "gamma"}, interaction_ids=[]),
        "i4": NS(pattern_id="P4", bindings={"firm": "gamma"}, interaction_ids=[]),
        "i5": NS(pattern_id="P5", bindings={"bank": "fed", "market": "oil"}, interaction_ids=["e4"])}
    patterns = {"P1": pattern("P1", "Oil chain"), "P2": pattern("P2", "Energy block", subs=["P1", "P9"]),
                "P3": pattern("P3", "Candidate", status="candidate"), "P4": pattern("P4", "Quiet names"),
                "P5": pattern("P5", "Policy and oil")}
    hyps = {"H1": NS(id="H1", status="open", informational_value=0.4, probability=0.6, statement="oil drives Acme",
                     subject_entity_ids=["acme", "oil", "nobody"]),
            "H2": NS(id="H2", status="open", informational_value=None, probability=0.5, statement="gamma moves",
                     subject_entity_ids=["gamma"]),
            "H3": NS(id="H3", status="refuted", informational_value=0.9, probability=0.1, statement="c",
                     subject_entity_ids=["acme"])}
    graph = NS(entities=ents, subentities=subs, interactions=ints, instances=instances, paths={}, compositions={},
               identities={}, stock_flows={}, matrices={})
    wm = NS(graph=graph, hypotheses=hyps, clock=T0)
    ltm = NS(object_generalizations=NS(patterns=patterns, taxonomy=otax), interaction_generalizations=NS(taxonomy=itax))
    return wm, ltm


PC = v4.pack_config("Small Demo!", "Small demo")


def test_helpers():
    assert PC == {"domain_pack_id": "PACK_SMALL_DEMO", "domain_pack_name": "Small demo", "slug": "small_demo",
                  "file_index": "036", "edge_start": 60}
    custom = v4.pack_config("x", "X", {"slug": "s", "domain_pack_id": "PACK_S", "name": "N", "file_index": 37,
                                       "edge_id_start": 80})
    assert custom == {"domain_pack_id": "PACK_S", "domain_pack_name": "N", "slug": "s", "file_index": "37", "edge_start": 80}
    assert [v4._confidence(p) for p in (0.9, 0.75, 0.6, 0.1)] == ["high", "medium_high", "medium", "context_only"]
    assert v4._horizon(kernel(duration=20.0)) == "starts after ~3d, builds over ~10d, fades over ~20d"
    assert v4._horizon(NS(delay=None, lag=D(5.0), duration=None)) == "builds over ~5d, persists"
    assert v4._node_id(NS(name="Acme", aliases=["ACME"])) == "N_ACME"
    assert v4._node_id(NS(name="Tokio Marine", aliases=["8766 JP"], short="Tokio")) == "N_TOKIO"
    assert v4._provenance("Origin.import") == "imported_research_reviewed" and v4._provenance("seed") == "seed"
    assert v4._direction(NS(forward=NS(effect=D(0.0)))) == "mixed"
    assert v4._direction(NS(forward=NS(effect=D(0.2, lo=-0.1, hi=0.4)))) == "mixed_lean_positive"


def test_companies_and_macro_nodes():
    wm, ltm = world()
    pack = v4.domain_pack(wm, ltm, pc=PC, book=["acme"], version=7, state_hash="h")
    cos = {c["axelrod_entity_id"]: c for c in pack["companies"]}
    assert list(cos) == ["acme", "beta", "gamma"]
    acme = cos["acme"]
    assert acme["company_id"] == "N_ACME" and acme["node_group"] == "watchlist" and acme["aliases"] == ["Acme Corp"]
    assert acme["taxonomy"]["sector"] == "Technology" and acme["taxonomy"]["subsectors"] == ["Software"]
    assert acme["role_tags"] == ["software", "tech", "technology"]
    assert acme["primary_sector_pack_id"] == "PACK_ENERGY_BLOCK" and acme["secondary_sector_pack_ids"] == []
    beta = cos["beta"]
    assert beta["company_id"] == "N_BETA_HOLDINGS" and beta["ticker"] == "8766 JP" and beta["node_group"] == "context"
    assert beta["taxonomy"]["sector"] == "" and beta["taxonomy"]["geographic_scope"] == "global"
    assert cos["gamma"]["primary_sector_pack_id"] == "PACK_QUIET_NAMES"
    macro = {m["axelrod_entity_id"]: m for m in pack["domain_specific_support_objects"]["macro_factor_nodes"]}
    assert macro["oil"]["taxonomy"]["sector"] == "Commodities" and macro["fed"]["taxonomy"]["sector"] == "Policy Rates"


def test_edge_vocabulary_and_relationships():
    wm, ltm = world()
    pack = v4.domain_pack(wm, ltm, pc=PC, book=[], version=7, state_hash="h")
    vocab = {v["axelrod_concept_id"]: v for v in pack["domain_specific_support_objects"]["axelrod_edge_vocabulary"]}
    assert vocab[None]["edge_label"] == "Unclassified link" and vocab[None]["edge_id"] == "E60"
    assert vocab["gen:int:a"]["edge_name"] == "COST_PASS_THROUGH"
    assert vocab["gen:int:unknown_concept"]["edge_label"] == "unknown_concept"
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}
    assert set(rels) == {"e1", "e2", "e3", "e3b", "e5", "e8"}            # live links a company owns
    assert rels["e1"]["relationship_id"] == "REL_ACME__E61_COST_PASS_THROUGH"
    assert rels["e3"]["relationship_id"] == "REL_ACME__E61_COST_PASS_THROUGH__COST"
    assert rels["e3b"]["relationship_id"] == "REL_ACME__E61_COST_PASS_THROUGH__COST_2"
    assert rels["e5"]["company_id"] == "N_ACME"                         # the company that drives a macro value
    assert rels["e2"]["direction"] == "mixed_lean_negative" and rels["e2"]["evidence_available"] == []
    assert rels["e2"]["source_provenance"] == "imported_research_reviewed" and rels["e2"]["confidence_prior"] == "medium"
    assert rels["e8"]["axelrod"]["effect_q05"] is None and rels["e3"]["axelrod"]["duration_days"] == 30.0
    (macro,) = pack["domain_specific_support_objects"]["macro_transmission_links"]
    assert macro["axelrod"]["interaction_id"] == "e4" and macro["status"] == "candidate"
    assert macro["link_id"].startswith("MLINK_FED_TO_OIL__E60_")
    cross = pack["cross_validation_assertions"]
    assert [c["cross_validation_id"] for c in cross] == ["CV_ACME_TO_BETA_HOLDINGS__E61_PRICE",
                                                          "CV_BETA_HOLDINGS_TO_ACME__E61_PRICE"]
    assert cross[0]["validation_direction"] == "negative_or_mixed"


def test_clusters_scopes_sector_packs_and_paths():
    wm, ltm = world()
    pack = v4.domain_pack(wm, ltm, pc=PC, book=[], version=7, state_hash="h")
    clusters = {c["axelrod_pattern_id"]: c for c in pack["clusters"]}
    assert set(clusters) == {"P1", "P2", "P4", "P5"}                  # the candidate is left out
    assert clusters["P2"]["subclusters"] == ["Oil chain"]
    assert clusters["P2"]["company_ids"] == ["N_ACME", "N_BETA_HOLDINGS", "N_FED"]
    assert clusters["P1"]["membership_ids"] == ["CLMEM_OIL_CHAIN__ACME", "CLMEM_OIL_CHAIN__BETA_HOLDINGS"]
    scopes = {s["cluster_ids"][0]: s for s in pack["required_search_scopes"]}
    assert set(scopes) == {"CL_OIL_CHAIN", "CL_QUIET_NAMES", "CL_POLICY_AND_OIL"}   # composites have none
    assert scopes["CL_OIL_CHAIN"]["metric_family_ids"] == ["MF_REVENUE"]
    assert scopes["CL_QUIET_NAMES"]["mechanisms_to_inspect"] == []
    sp = {s["sector_pack_id"]: s for s in pack["sector_packs"]}
    assert set(sp) == {"PACK_ENERGY_BLOCK", "PACK_QUIET_NAMES", "PACK_POLICY_AND_OIL"}
    # a composite whose part is no longer admitted (P9) still exports (it raised a KeyError)
    assert sp["PACK_ENERGY_BLOCK"]["required_search_scope_ids"] == ["REQ_SEARCH_OIL_CHAIN"]
    paths = {p["cluster_id"]: p for p in pack["transmission_paths"]}
    assert set(paths) == {"CL_OIL_CHAIN", "CL_POLICY_AND_OIL"}       # an empty chain has no path
    assert paths["CL_OIL_CHAIN"]["primary_company_id"] in ("N_ACME", "N_BETA_HOLDINGS")
    assert paths["CL_POLICY_AND_OIL"]["path_id"] == "PATH_CONTEXT_POLICY_AND_OIL"
    assert paths["CL_POLICY_AND_OIL"]["primary_company_id"] == "EVENT_OR_CONTEXT_DRIVEN"
    fields = {f["field_spec_id"]: f for f in pack["financial_model_semantic_fields"]}
    assert fields["FMSPEC_SALES"]["applies_to"] == ["Acme", "Beta Holdings"]
    assert [m["metric_family_id"] for m in pack["metric_families"]] == ["MF_COST", "MF_PRICE", "MF_RATE", "MF_REVENUE"]


def test_caveats_and_their_impacts():
    wm, ltm = world()
    pack = v4.domain_pack(wm, ltm, pc=PC, book=[], version=7, state_hash="h")
    cav = {c["caveat_id"]: c for c in pack["industry_caveat_definitions"]}
    assert cav["CAV_BOUND_ACME_SALES"]["definition"] == "Acme sales tends to stay within its bound"
    assert cav["CAV_BOUND_BETA_SALES"]["bounds"] == {"min": 1.0, "max": 2.0}
    assert {"CAV_UNVALIDATED_SEEDED_LINKS", "CAV_SIGN_UNCERTAIN_LINKS", "CAV_OPEN_H1", "CAV_OPEN_H2"} <= set(cav)
    assert "CAV_OPEN_H3" not in cav
    imps = {i["caveat_impact_id"]: i for i in pack["caveat_impact_assertions"]}
    merged = imps["CAVIMPACT_UNVALIDATED_SEEDED_LINKS__TO_ACME__E61"]
    assert merged["affected_metrics"] == ["cost"]                  # two links of Acme on one edge: one impact
    assert imps["CAVIMPACT_OPEN_H1__TO_ACME__E61"]["severity_prior"] == "medium_high"
    gamma = imps["CAVIMPACT_OPEN_H2__TO_GAMMA__NA"]
    assert gamma["edge_id"] is None and gamma["affected_metrics"] == [] and gamma["severity_prior"] == "medium"
    assert not any("TO_OIL" in k for k in imps)                     # only companies carry impacts


def test_a_model_with_no_doubtful_links_has_no_structural_caveats():
    wm, ltm = world()
    g = wm.graph
    for iid in ("e2", "e3", "e3b", "e5", "e8"):
        g.interactions[iid].retired_at = T0
    pack = v4.domain_pack(wm, ltm, pc=PC, book=[], version=7, state_hash="h")
    ids = {c["caveat_id"] for c in pack["industry_caveat_definitions"]}
    assert "CAV_UNVALIDATED_SEEDED_LINKS" not in ids and "CAV_SIGN_UNCERTAIN_LINKS" not in ids


def test_evidence_pack():
    wm, _ = world()
    wm.graph.subentities["ghost.x"] = sub("ghost.x", "Ghost", "price")
    ev = v4.evidence_pack(wm, pc=PC, version=7, state_hash="abc")
    vals = {v["metric_id"]: v for v in ev["values"]}
    assert vals["acme.sales"]["mean"] == 1.2346 and vals["acme.sales"]["q95"] == 1.5 and vals["acme.sales"]["observed"]
    assert vals["acme.sales"]["evidence_count"] == 2          # a retired link's evidence still counts
    assert vals["oil.price"]["mean"] is None and vals["oil.price"]["sd"] is None
    assert vals["ghost.x"]["node_id"] is None and vals["ghost.x"]["node_name"] == "ghost"
    assert [q["id"] for q in ev["unresolved_questions"]] == ["H1", "H2"]


def _forecast():
    q = NS(q05=-0.1, q50=0.2, q95=0.5)
    hop = NS(source_id="oil.price", target_id="acme.sales", interaction_id="e1:fwd")
    trans = [NS(subentity_id="acme.sales", order=1, effect=0.2, path=[hop], arrives_day=3, peak_day=20, peak=0.3,
                material=True),
             NS(subentity_id="oil.price", order=0, effect=1.0, path=[], arrives_day=0, peak_day=0, peak=1.0,
                material=True)]
    return NS(id="F1", thesis_id="T1", question="q", based_on_version=7, seed=1, config_hash="h", horizon_days=90,
              targets=["acme.sales", "zzz.none"], effect_summary={"acme.sales": [q]}, transmission=trans,
              constraints_binding=[], scenario_table=[], scenarios=[NS(id="s1", name="base", weight=1.0)],
              unquantified=[], coverage={"summary": {"contributed": 1, "excluded": 0}})


def test_forecast_record_with_and_without_an_explanation():
    wm, _ = world()
    rec = v4.forecast_record(_forecast(), None, wm, PC)
    assert rec["key_interactions"] == [] and rec["domain_pack_id"] == "PACK_SMALL_DEMO"
    assert rec["targets"][0]["effect_at_horizon_sd"] == {"q05": -0.1, "q50": 0.2, "q95": 0.5}
    assert rec["targets"][1] == {"metric_id": "zzz.none", "name": "zzz.none", "effect_at_horizon_sd": None}
    assert [t["order"] for t in rec["transmission"]] == [0, 1] and rec["transmission"][0]["path"] == ["Oil price"]
    assert rec["transmission"][1]["axelrod_interaction_ids"] == ["e1"]
    assert rec["calculation_coverage"]["summary"]["contributed"] == 1 and rec["unquantified"] == []
    key =v4.forecast_record(_forecast(), NS(key_interactions=[("e1", 0.7), ("gone", 0.1)]), wm, PC)["key_interactions"]
    assert key == [{"axelrod_interaction_id": "e1", "contribution": 0.7, "mechanism": "Oil price moves Acme sales"},
                   {"axelrod_interaction_id": "gone", "contribution": 0.1, "mechanism": "gone"}]


def test_context_pack_lists_the_forecast_in_its_load_order_only_when_given():
    wm, ltm = world()
    out = v4.context_pack(wm, ltm, scenario_id="small_demo", title="T", book=[], version=1, state_hash=None)
    assert set(out) == {"manifest", "domain_pack", "registry_entry", "evidence"}
    assert len(out["manifest"]["load_order"]) == 5
    assert out["registry_entry"]["domains"][0]["file_name"] == "036_world_model_domain_pack_small_demo_v4.1.4.json"
    out = v4.context_pack(wm, ltm, scenario_id="small_demo", title="T", book=[], version=1, state_hash=None,
                          forecast=_forecast(), pack_cfg={"file_index": "040"})
    assert out["manifest"]["load_order"][-1] == {"file": "evidence_pack_axelrod_small_demo_forecast_F1.json",
                                                 "source": "this export: forecast"}
    assert out["manifest"]["activate"]["file_index"] == "040" and out["forecast"]["forecast_id"] == "F1"
