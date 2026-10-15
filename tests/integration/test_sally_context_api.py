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


def test_the_context_export_follows_the_agents_v4_format(client, posed):
    r = client.get("/api/context/v4", params={"forecast": posed["forecast"]["id"]})
    assert r.status_code == 200, r.text
    ctx = r.json()
    pack, base, fc = ctx["domain_pack"], ctx["baseline"], ctx["forecast"]
    assert pack["schema_version"] == "v4.1.4" and pack["file_role"] == "domain_pack"
    for key in ("companies", "clusters", "cluster_memberships", "sector_packs", "metric_families",
                "company_edge_relationships", "cross_validation_assertions", "industry_caveat_definitions",
                "transmission_paths"):
        assert key in pack
    assert {c["axelrod_entity_id"] for c in pack["companies"]} == BOOK
    assert all("in_book" in c["role_tags"] for c in pack["companies"])
    edge = pack["company_edge_relationships"][0]
    assert edge["direction"] in {"positive", "negative", "neutral"} and edge["confidence_prior"] in {"high", "medium", "low"}
    assert {"effect_sd_per_sd", "existence_p", "delay_days"} <= set(edge["axelrod"])
    # the baseline is dated and versioned; the decision context is kept apart from the pack
    assert base["file_role"] == "current_baseline" and base["state_version"] == fc["based_on_version"]
    assert fc["file_role"] == "decision_context" and fc["scenario_table"]["rows"]
    assert fc["transmission"] and fc["key_interactions"]
    files = [f["file"] for f in ctx["manifest"]["load_order"]]
    assert files[0].startswith("000_") and any(f.startswith("036_") for f in files)
    assert any(f["card"].startswith("5") for f in ctx["manifest"]["feeds"])
    assert "never" in ctx["manifest"]["boundary"] or "does not" in ctx["manifest"]["boundary"]


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
