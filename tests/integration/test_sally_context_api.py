"""Sally's demo (Oct 15): eleven names seeded, with five ready theses; each forecast carries a scenario table (bull,
base, and bear bands of its draws, read for the book), and the world model exports as context for a client's agents in
their v4.1.4 world-model format (GET /api/context/v4). The research itself is local only, so these tests use none."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import MemoryBackend

BOOK = {"jpmorgan", "morgan_stanley", "citigroup", "china_construction_bank", "unicredit", "aib_group",
        "tokio_marine", "msad", "toyota", "komatsu", "softbank_corp"}


@pytest.fixture(scope="module")
def client():
    app = create_app(scenario="sally_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def posed(client):
    r = client.post("/api/theses/S-T2/pose")
    assert r.status_code == 200, r.text
    return r.json()


def test_the_seeded_model_holds_the_book_and_its_groups(client):
    st = client.get("/api/sim/status").json()
    assert st["imports"] is True and st["canvas"] == "seeded"
    view = client.get("/api/state").json()
    assert BOOK <= {e["id"] for e in view["entities"]}
    assert {"G1", "G2", "G3", "S4", "S6", "S7"} <= {h["pattern_id"] for h in view["hulls"]}
    assert {t["id"] for t in client.get("/api/scenario-theses").json()} == {"S-T1", "S-T2", "S-T3", "S-T4", "S-T5"}


def test_a_forecast_carries_a_scenario_table_for_the_book(posed):
    t = posed["forecast"]["scenario_table"]
    assert {b["entity"] for b in t["book"]} == BOOK
    bands = {r["band"]: r for r in t["rows"]}
    assert set(bands) == {"Bull", "Base", "Bear"}
    assert sum(r["probability"] for r in t["rows"]) == pytest.approx(1.0, abs=0.02)
    assert bands["Bull"]["book_move"] >= bands["Base"]["book_move"] >= bands["Bear"]["book_move"]
    assert 0.0 <= t["p_book_up"] <= 1.0 and 0.0 <= t["p_book_down"] <= 1.0
    # names in a band carry their move in their own units too (percent for prices and profits)
    moved = bands["Bull"]["favored"] + bands["Bear"]["hurt"]
    assert moved and all("pct" in m or "change" in m for m in moved)
    assert bands["Bull"]["mechanism"] and t["changes_the_read"]


# the client's v4.1.4 domain-pack layout: the keys every item of a section carries in their packs, and the contract's ID rules
REQUIRED = {
    "companies": ({"company_id", "descriptive_node_id", "company_name", "ticker", "role_tags", "primary_sector_pack_id",
                   "node_group", "source_packs_present", "ontology_entity_type", "taxonomy"}, "company_id", r"^N_[A-Z0-9_]+$"),
    "clusters": ({"cluster_id", "cluster_name", "company_ids"}, "cluster_id", r"^CL_[A-Z0-9_]+$"),
    "cluster_memberships": ({"cluster_membership_id", "cluster_id", "company_id", "membership_role"}, "cluster_membership_id",
                            r"^CLMEM_[A-Z0-9_]+__[A-Z0-9_]+$"),
    "sector_packs": ({"sector_pack_id", "sector_pack_name", "when_to_activate", "company_role_tags_covered", "metric_family_ids",
                      "required_baselines", "do_not_infer", "source_packs_present"}, "sector_pack_id", r"^PACK_[A-Z0-9_]+$"),
    "metric_families": ({"metric_family_id", "metric_family_name", "metrics", "required_baselines", "do_not_conclude_without",
                         "source_packs_present"}, "metric_family_id", r"^MF_[A-Z0-9_]+$"),
    "required_search_scopes": ({"required_search_scope_id", "search_scope_label", "sector_pack_ids", "cluster_ids", "caveat_ids",
                                "metric_family_ids", "why_required", "member_selector", "seed_search_targets",
                                "mechanisms_to_inspect", "confirming_evidence", "breaking_evidence", "search_templates",
                                "search_cost_hint", "freshness_window_default", "result_states_allowed"},
                               "required_search_scope_id", r"^REQ_SEARCH_[A-Z0-9_]+$"),
    "company_edge_relationships": ({"relationship_id", "company_id", "edge_id", "direction", "confidence_prior", "affected_metrics"},
                                   "relationship_id", r"^REL_[A-Z0-9_]+__E\d\d_[A-Z0-9_]+$"),
    "cross_validation_assertions": ({"cross_validation_id", "source_company_id", "target_company_id", "edge_id",
                                     "validation_direction", "mechanism"}, "cross_validation_id", r"^CV_[A-Z0-9_]+_TO_[A-Z0-9_]+__E\d\d_"),
    "industry_caveat_definitions": ({"caveat_id", "caveat_name", "caveat_type", "definition"}, "caveat_id", r"^CAV_[A-Z0-9_]+$"),
    "caveat_impact_assertions": ({"caveat_impact_id", "caveat_id", "affected_metrics"}, "caveat_impact_id", r"^CAVIMPACT_[A-Z0-9_]+__TO_"),
    "transmission_paths": ({"path_id", "primary_company_id", "trigger", "ordered_steps", "edge_ids", "company_ids"}, "path_id",
                           r"^PATH_[A-Z0-9_]+$"),
    "financial_model_semantic_fields": ({"field_spec_id", "field_name", "applies_to", "required_for", "ontology_entity_type"},
                                        "field_spec_id", r"^FMSPEC_[A-Z0-9_]+$"),
}


def test_the_context_export_follows_the_clients_v4_layout(client, posed):
    import re

    r = client.get("/api/context/v4", params={"forecast": posed["forecast"]["id"]})
    assert r.status_code == 200, r.text
    ctx = r.json()
    pack, ev, fc, reg = ctx["domain_pack"], ctx["evidence"], ctx["forecast"], ctx["registry_entry"]
    assert pack["schema_version"] == "v4.1.4_modular_domain_pack"
    assert pack["file_role"] == "DOMAIN_PACK__LOAD_AFTER_CORE_WHEN_ACTIVATED"
    assert pack["domain_pack_id"] == "PACK_GLOBAL_RATES_BANKS_INSURERS_JAPAN_EXPORTERS" and pack["file_index"] == "036"
    for sec, (keys, idk, rx) in REQUIRED.items():
        items = pack[sec]
        assert items, sec
        for it in items:
            assert keys <= set(it), (sec, sorted(keys - set(it)))
            assert re.match(rx, it[idk]), (sec, it[idk])
        ids = [it[idk] for it in items]
        assert len(ids) == len(set(ids)), f"duplicate ids in {sec}"
    assert {c["axelrod_entity_id"] for c in pack["companies"]} == BOOK
    assert all(c["ontology_entity_type"] == "Company" for c in pack["companies"])
    # every relationship is owned by a company and points at the pack's own edge vocabulary, clear of the client's E03-E35
    vocab = {e["edge_id"] for e in pack["domain_specific_support_objects"]["axelrod_edge_vocabulary"]}
    cos = {c["company_id"] for c in pack["companies"]}
    for rel in pack["company_edge_relationships"]:
        assert rel["company_id"] in cos and rel["edge_id"] in vocab and int(rel["edge_id"][1:]) >= 60
        assert rel["confidence_prior"] in {"high", "medium_high", "medium", "context_only"}
        assert {"effect_sd_per_sd", "existence_p", "delay_days"} <= set(rel["axelrod"])
    macro = {m["node_id"] for m in pack["domain_specific_support_objects"]["macro_factor_nodes"]}
    assert all(m in cos | macro for cl in pack["clusters"] for m in cl["company_ids"])
    # the registry row the client's 020 takes, and live state as evidence, never in the pack
    row = reg["domains"][0]
    assert set(row) == {"domain_pack_id", "domain_pack_name", "file_name", "activation_terms", "never_merge_into_base", "file_index"}
    assert row["file_name"].startswith("036_world_model_domain_pack_") and row["never_merge_into_base"] is True
    assert ev["file_role"].startswith("EVIDENCE_PACK__") and ev["state_version"] == fc["based_on_version"]
    assert fc["file_role"].startswith("EVIDENCE_PACK__") and fc["scenario_table"]["rows"] and fc["transmission"]
    files = [f["file"] for f in ctx["manifest"]["load_order"]]
    assert [f[:3] for f in files[:4]] == ["000", "010", "020", "036"] and files[4].startswith("evidence_pack_axelrod_")
    assert any(f["card"].startswith("5") for f in ctx["manifest"]["feeds"])


def test_the_context_without_a_forecast_and_for_an_unknown_one(client):
    ctx = client.get("/api/context/v4").json()
    assert "forecast" not in ctx and ctx["domain_pack"]["companies"]
    assert client.get("/api/context/v4", params={"forecast": "FC-nope"}).status_code == 404


def test_the_yen_is_read_as_the_reciprocal_of_dollar_yen(client):
    r = client.post("/api/theses", json={"question": "What if the yen rose by 5% next month?"})
    assert r.status_code == 200, r.text
    th = client.get(f"/api/theses/{r.json()['forecast']['thesis_id']}").json()
    op = th["event"]["ops"][0]
    assert op["target"]["subentity_id"] == "dollar_yen.usd_jpy"
    assert op["delta"] == pytest.approx(1 / 1.05 - 1)


def test_entities_carry_their_concepts_for_outlines(client):
    ents = {e["id"]: e for e in client.get("/api/state").json()["entities"]}
    jpm, boj, jgbs = ents["jpmorgan"], ents["boj"], ents["jgbs"]
    # the V1.0 taxonomy: institutions (central banks; companies by sector and industry), economies, markets and asset classes
    assert jpm["kind_name"] == "Banks" and jpm["concept_branch"] == "gen:obj:institutions" and jpm["concept_branch_name"] == "Institutions"
    assert jpm["concept_path"] == ["gen:obj:institutions", "gen:obj:companies", "gen:obj:financials", "gen:obj:bank"]
    assert ents["morgan_stanley"]["kind_name"] == "Investment banking and wealth management"
    assert boj["kind_name"] == "Central banks" and boj["concept_path"][1] == "gen:obj:public_institutions"
    assert jgbs["kind_name"] == "Sovereign bonds" and jgbs["concept_branch"] == "gen:obj:markets"
    assert {ents[e]["kind_name"] for e in ("dollar_yen", "jpy_usd", "usd_eur", "jpy_eur")} == {"Foreign exchange"}
    assert {ents[e]["kind_name"] for e in ("us_capital_markets", "china_capital_markets", "japan_capital_markets",
                                           "europe_capital_markets")} == {"Capital markets"}
    assert ents["cgbs"]["kind_name"] == "Sovereign bonds" and ents["china_economy"]["kind_name"] == "Economies"


def test_forecast_views_are_compact(client, posed):
    # the per-day series are rounded and each scenario's series is not sent twice (Oct 15, speed)
    assert "scenarios" not in posed["forecast"]
    assert all("levels" not in s for s in posed["scenarios"])
    e = posed["targets"][0]["effects"][-1]
    assert all(len(repr(v)) <= 9 for v in e.values())


def test_the_world_model_exports_on_its_own_at_the_current_version(client):
    st = client.get("/api/sim/status").json()
    ctx = client.get("/api/context/v4").json()
    assert ctx["evidence"]["state_version"] == st["version"] and ctx["evidence"]["state_hash"]
    files = [f["file"] for f in ctx["manifest"]["load_order"]]
    assert any(f.startswith("036_world_model_domain_pack") for f in files)
    assert sum(f.startswith("evidence_pack_axelrod_") for f in files) == 1 and "forecast" not in ctx
