"""v1 reads of the model (docs/api/openapi.yaml): world models and versions, entities with their attributes nested,
observations and states, construction, relationships and evidence, concepts and groups, the graph, the export; each
pinned to a version or a date, paged by cursor, and answered in the envelope."""

from __future__ import annotations

import pytest

from tests.service.helpers import (
    OIL_NOTE,
    V1,
    WM,
    Signer,
    attributes,
    data,
    decide_all,
    problem,
    propose,
    service,
    upload,
)

SIGNER = Signer()


@pytest.fixture(scope="module")
def c():
    with service(SIGNER) as client:
        yield client


@pytest.fixture(scope="module")
def moved(c):
    """The model before and after one reviewed change: a synthetic data note (crude at $103), approved by a person."""
    before = data(c.get(WM))
    v_before = c.get(WM).json()["meta"]["version"]
    crude = data(c.get(f"{WM}/entities/crude_oil/attributes/price"))
    res = upload(c, OIL_NOTE, "2026-09-01_data.txt", source="Data desk", source_type="data")
    propose(c, res["bundle_id"])
    decided = decide_all(c, SIGNER)
    return {"before": before, "version": v_before, "crude": crude, "decided": decided, "bundle_id": res["bundle_id"]}


# -- the credential, world models, versions --------------------------------------------------------------------------
def test_me_names_the_principal_and_its_world_models(c):
    me = data(c.get(f"{V1}/me"))
    assert me["actor"] == {"kind": "key", "org": "default", "sub": "tester", "name": None, "azp": None, "act": None,
                           "jti": None}
    assert "changes:approve" not in me["scopes"] and "admin" in me["scopes"] and me["world_model_ids"] == ["acme_demo"]
    tok = data(c.get(f"{V1}/me", headers=SIGNER.bearer(act={"sub": "mcp-client:x", "name": "Claude"}, azp="core-mcp")))
    assert tok["actor"]["kind"] == "token" and tok["actor"]["act"] == {"sub": "mcp-client:x", "name": "Claude"}
    assert tok["actor"]["jti"] and tok["scopes"] == ["world_model:read"]           # core-mcp reads only


def test_world_models_list_and_one(c):
    body = c.get(f"{V1}/world-models").json()
    assert [m["id"] for m in body["data"]] == ["acme_demo"] and body["meta"]["next_cursor"] is None
    one = c.get(WM)
    wm = one.json()["data"]
    assert wm["organization"] == "default" and wm["counts"]["attributes"] > 80 and wm["latest_version"] >= 1
    assert one.headers["etag"] == f'"{one.json()["meta"]["version"]["state_hash"]}"'
    assert c.get(f"{V1}/world-models", params={"limit": 1, "cursor": "eyJvIjoxLCJ2IjpudWxsfQ"}).json()["data"] == []


def test_versions_newest_first_and_one_by_number_or_latest(c, moved):
    rows = data(c.get(f"{WM}/versions", params={"limit": 200}))
    assert [r["number"] for r in rows] == sorted((r["number"] for r in rows), reverse=True)
    committed = [r for r in rows if r["change_ids"]]
    assert committed and set(committed[0]["change_ids"]) <= {d["change_id"] for d in moved["decided"]}
    latest = c.get(f"{WM}/versions/latest")
    assert data(latest)["number"] == rows[0]["number"] and latest.headers["etag"]
    assert data(c.get(f"{WM}/versions/1"))["number"] == 1
    problem(c.get(f"{WM}/versions/99999"), 404, "version_not_found")
    problem(c.get(f"{WM}/versions/zero"), 422, "invalid_request")


# -- entities and attributes --------------------------------------------------------------------------------------------
def test_an_entity_with_its_attributes_nested(c):
    r = c.get(f"{WM}/entities/acme_motors")
    e = data(r)
    assert e["type"] == "company" and e["attribute_count"] == len(e["attributes"]) and "relationships" not in e
    assert all(a["id"] == f"acme_motors.{a['key']}" and a["entity_id"] == "acme_motors" for a in e["attributes"])
    assert e["concepts"][-1]["name"] == "Automobiles" and r.headers["etag"]
    with_rels = data(c.get(f"{WM}/entities/acme_motors", params={"include": "attributes,relationships"}))
    ids = {a["id"] for a in with_rels["attributes"]}
    assert with_rels["relationships"]
    assert all(x["source_attribute_id"] in ids or x["target_attribute_id"] in ids for x in with_rels["relationships"])
    problem(c.get(f"{WM}/entities/nobody"), 404, "entity_not_found")
    problem(c.get(f"{WM}/entities/acme_motors", params={"include": "everything"}), 422, "invalid_request")


def test_entities_by_type_concept_group_and_name(c):
    agencies = data(c.get(f"{WM}/entities", params={"type": "agency", "limit": 200}))
    assert agencies and all(e["type"] == "agency" for e in agencies)
    banks = data(c.get(f"{WM}/entities", params={"concept": "gen:obj:bank", "limit": 200}))
    assert "acme_bank" in {e["id"] for e in banks}
    group = data(c.get(f"{WM}/groups", params={"limit": 1}))[0]
    grouped = data(c.get(f"{WM}/entities", params={"group": group["id"], "limit": 200}))
    assert {e["id"] for e in grouped} == set(group["bindings"].values())
    by_attr = data(c.get(f"{WM}/entities", params={"q": "policy rate"}))
    bank = next(e for e in by_attr if e["id"] == "central_bank")
    assert [a["key"] for a in bank["attributes"]] == ["policy_rate"]
    by_name = data(c.get(f"{WM}/entities", params={"q": "ACMO"}))
    assert [e["id"] for e in by_name] == ["acme_motors"] and len(by_name[0]["attributes"]) == by_name[0]["attribute_count"]
    prefix = data(c.get(f"{WM}/entities", params={"q": "acme mo", "limit": 200}))
    assert prefix[0]["id"] == "acme_motors"


def test_entities_page_by_cursor_on_one_version(c):
    first = c.get(f"{WM}/entities", params={"limit": 3}).json()
    second = c.get(f"{WM}/entities", params={"limit": 3, "cursor": first["meta"]["next_cursor"]}).json()
    assert len(first["data"]) == 3 and first["meta"]["next_cursor"]
    assert not {e["id"] for e in first["data"]} & {e["id"] for e in second["data"]}
    assert second["meta"]["version"]["number"] == first["meta"]["version"]["number"]
    pinned = c.get(f"{WM}/entities", params={"limit": 3, "version": 1}).json()
    after = c.get(f"{WM}/entities", params={"limit": 3, "cursor": pinned["meta"]["next_cursor"]}).json()
    assert after["meta"]["version"]["number"] == 1
    for bad in ("nope", "eyJvIjotMX0", "eyJvIjoxLCJ2IjowfQ", "W10"):
        problem(c.get(f"{WM}/entities", params={"cursor": bad}), 400, "invalid_cursor")


@pytest.mark.parametrize("ref", ["operating_profit", "acme_motors.operating_profit"])
def test_an_attribute_by_key_or_full_id(c, ref):
    a = data(c.get(f"{WM}/entities/acme_motors/attributes/{ref}"))
    assert (a["id"], a["key"], a["entity_id"]) == ("acme_motors.operating_profit", "operating_profit", "acme_motors")
    assert a["level"]["q05"] <= a["level"]["mean"] <= a["level"]["q95"] and a["epistemic_type"] in ("observed",
                                                                                                    "inferred")


@pytest.mark.parametrize("path, code", [("/entities/acme_motors/attributes/central_bank.policy_rate", "attribute_not_found"),
                                        ("/entities/acme_motors/attributes/policy_rate", "attribute_not_found"),
                                        ("/entities/nobody/attributes/operating_profit", "entity_not_found")])
def test_an_attribute_outside_its_entity_is_not_found(c, path, code):
    problem(c.get(WM + path), 404, code)


def test_an_entitys_attributes_page(c):
    body = c.get(f"{WM}/entities/acme_motors/attributes", params={"limit": 5}).json()
    assert len(body["data"]) == 5 and body["meta"]["next_cursor"]
    problem(c.get(f"{WM}/entities/nobody/attributes"), 404, "entity_not_found")


def test_observations_and_states_after_a_reviewed_change(c, moved):
    obs = data(c.get(f"{WM}/entities/crude_oil/attributes/price/observations", params={"limit": 200}))
    assert obs and all(o["attribute_id"] == "crude_oil.price" and o["epistemic_type"] == "observed" for o in obs)
    assert abs(obs[-1]["value"] - 103) < 3 and obs[-1]["observed_at"] >= obs[-1]["valid_at"][:10]
    latest = data(c.get(f"{WM}/entities/crude_oil/attributes/price"))["latest_observation"]
    assert latest == obs[-1]
    early = data(c.get(f"{WM}/entities/crude_oil/attributes/price/observations",
                       params={"valid_to": "2026-08-31T00:00:00", "valid_from": "2020-01-01T00:00:00Z"}))
    assert all(o["valid_at"] < "2026-08-31T00:00:01" for o in early)
    states = data(c.get(f"{WM}/entities/crude_oil/attributes/price/states", params={"limit": 200}))
    assert states and all(s["sd"] >= 0 for s in states)
    window = data(c.get(f"{WM}/entities/crude_oil/attributes/price/states", params={"from": "2100-01-01T00:00:00Z"}))
    assert window == []
    assert data(c.get(f"{WM}/entities/crude_oil/attributes/price/states", params={"to": "2000-01-01T00:00:00Z"})) == []


# -- construction -------------------------------------------------------------------------------------------------------------
def test_compositions_and_paths_list_and_one(c):
    comps = data(c.get(f"{WM}/entities/acme_motors/compositions", params={"limit": 200}))
    assert comps and all(x["entity_id"] == "acme_motors" and x["role"] in ("driving", "reconciling") for x in comps)
    one = data(c.get(f"{WM}/entities/acme_motors/compositions/{comps[0]['id']}"))
    assert one == comps[0]
    problem(c.get(f"{WM}/entities/acme_motors/compositions/nope"), 404, "composition_not_found")
    other = data(c.get(f"{WM}/entities/acme_bank/compositions", params={"limit": 1}))[0]
    problem(c.get(f"{WM}/entities/acme_motors/compositions/{other['id']}"), 404, "composition_not_found")
    paths = data(c.get(f"{WM}/entities/acme_motors/paths", params={"limit": 200}))
    assert paths and all(p["steps"] for p in paths)
    p = data(c.get(f"{WM}/entities/acme_motors/paths/{paths[0]['id']}"))
    assert p == paths[0] and p["uncalibrated_steps"] == sum(1 for s in p["steps"] if s["calibration"] == "uncalibrated")
    problem(c.get(f"{WM}/entities/acme_motors/paths/nope"), 404, "path_not_found")
    for path in ("compositions", "paths", "compositions/x", "paths/x", "construction"):
        problem(c.get(f"{WM}/entities/nobody/{path}"), 404, "entity_not_found")


def test_construction_json_markdown_and_traces(c):
    view = data(c.get(f"{WM}/entities/acme_motors/construction"))
    assert view["entity_id"] == "acme_motors" and view["compositions"] and view["paths"] and view["problems"] == []
    md = c.get(f"{WM}/entities/acme_motors/construction", params={"format": "markdown"})
    assert md.headers["content-type"].startswith("text/markdown") and md.text.startswith("# Acme Motors")
    assert md.headers["x-request-id"]
    accept = c.get(f"{WM}/entities/acme_motors/construction", headers={"Accept": "text/markdown"})
    assert accept.text == md.text
    by_key = data(c.get(f"{WM}/entities/acme_motors/traces", params={"from": "home_production"}))
    by_id = data(c.get(f"{WM}/entities/acme_motors/traces", params={"from": "acme_motors.home_production"}))
    assert by_key == by_id and by_key["from_attribute_id"] == "acme_motors.home_production" and by_key["routes"]
    other = data(c.get(f"{WM}/entities/acme_motors/traces", params={"from": "dollar.index"}))
    assert other["reaches_endpoint"] and other["routes"][0]["steps"][0]["relationship_id"]
    assert other["through_totals"] is False
    deep = data(c.get(f"{WM}/entities/acme_motors/traces", params={"from": "dollar.index", "through_totals": True,
                                                               "max_depth": 12}))
    assert deep["through_totals"] is True and len(deep["routes"]) >= len(other["routes"])
    longest = max(len(r["steps"]) for r in deep["routes"])
    assert longest >= max(len(r["steps"]) for r in other["routes"])
    short = data(c.get(f"{WM}/entities/acme_motors/traces", params={"from": "dollar.index", "max_depth": 1}))
    assert all(len(r["steps"]) <= 1 for r in short["routes"])
    for bad in (0, 17):
        problem(c.get(f"{WM}/entities/acme_motors/traces", params={"from": "dollar.index", "max_depth": bad}), 422,
                "invalid_request")
    problem(c.get(f"{WM}/entities/acme_motors/traces", params={"from": "nope"}), 404, "attribute_not_found")
    problem(c.get(f"{WM}/entities/nobody/traces", params={"from": "x"}), 404, "entity_not_found")
    problem(c.get(f"{WM}/entities/acme_motors/traces"), 422, "invalid_request")


# -- relationships and evidence --------------------------------------------------------------------------------------------
def test_relationships_filtered(c):
    rels = data(c.get(f"{WM}/relationships", params={"entity": "acme_motors", "limit": 200}))
    assert rels and all("acme_motors" in (r["source_entity_id"], r["target_entity_id"]) for r in rels)
    unsized = data(c.get(f"{WM}/relationships", params={"calibration": "uncalibrated", "limit": 50}))
    assert unsized and all(r["effect"] is None and r["kernel"]["lag_days"] is None for r in unsized)
    acc = data(c.get(f"{WM}/relationships", params={"type": "accounting", "limit": 20}))
    assert acc and all(r["type"] == "accounting" for r in acc)
    src = data(c.get(f"{WM}/relationships", params={"source": "dollar.index", "target": "acme_motors.operating_profit"}))
    assert [r["id"] for r in src] == ["m24"]
    assert data(c.get(f"{WM}/relationships", params={"status": "retired"})) == []
    every = c.get(f"{WM}/relationships", params={"status": "all", "limit": 1}).json()
    assert every["meta"]["next_cursor"]


def test_a_relationship_its_evidence_and_an_evidence_record(c, moved):
    r = c.get(f"{WM}/relationships/m24")
    rel = data(r)
    assert rel["sign"] in ("positive", "negative") and 0 <= rel["confidence"] <= 1 and r.headers["etag"]
    assert rel["status"] == "active" and rel["valid_to"] is None and rel["epistemic_type"]
    problem(c.get(f"{WM}/relationships/nope"), 404, "relationship_not_found")
    problem(c.get(f"{WM}/relationships/nope/evidence"), 404, "relationship_not_found")
    problem(c.get(f"{WM}/evidence/EV-nope"), 404, "evidence_not_found")


# -- concepts and groups -------------------------------------------------------------------------------------------------------
def test_concepts_and_groups(c):
    concepts = data(c.get(f"{WM}/concepts", params={"limit": 200}))
    banks = next(x for x in concepts if x["name"] == "Banks")
    assert "acme_bank" in banks["entity_ids"] and data(c.get(f"{WM}/concepts/{banks['id']}")) == banks
    assert any(x["parent_id"] is None for x in concepts)
    problem(c.get(f"{WM}/concepts/nope"), 404, "concept_not_found")
    root = c.app.state.world_models["acme_demo"].st.controller.engine.ltm.object_generalizations.taxonomy.root_id
    problem(c.get(f"{WM}/concepts/{root}"), 404, "concept_not_found")
    groups = data(c.get(f"{WM}/groups", params={"limit": 200}))
    assert groups and data(c.get(f"{WM}/groups/{groups[0]['id']}")) == groups[0]
    problem(c.get(f"{WM}/groups/nope"), 404, "group_not_found")


# -- the graph and the export ---------------------------------------------------------------------------------------------------
def test_the_graph_from_entities_attributes_names_or_everything(c):
    g = data(c.get(f"{WM}/graph", params={"entities": "central_bank", "attributes": "gov_bonds.yield_10y", "depth": 0}))
    assert {a["id"] for a in attributes(g)} >= {"central_bank.policy_rate", "gov_bonds.yield_10y"} and not g["truncated"]
    g1 = data(c.get(f"{WM}/graph", params={"attributes": "central_bank.policy_rate", "depth": 1}))
    ids = {a["id"] for a in attributes(g1)}
    assert len(ids) > 1 and all(r["source_attribute_id"] in ids and r["target_attribute_id"] in ids
                                for r in g1["relationships"])
    named = data(c.get(f"{WM}/graph", params={"q": "central bank", "depth": 0}))
    assert "central_bank" in {e["id"] for e in named["entities"]}
    every = data(c.get(f"{WM}/graph", params={"depth": 0, "limit": 5}))
    assert len(attributes(every)) == 5 and every["truncated"] is True
    problem(c.get(f"{WM}/graph", params={"entities": "nobody"}), 404, "entity_not_found")
    problem(c.get(f"{WM}/graph", params={"attributes": "nobody.x"}), 404, "attribute_not_found")


def test_the_export(c):
    pack = data(c.get(f"{WM}/exports/v4.1.4"))
    assert pack["manifest"]["schema_version"] == "v4.1.4" and "domain_pack" in pack
    problem(c.get(f"{WM}/exports/v4.1.4", params={"simulation": "FC-nope"}), 404, "simulation_not_found")


# -- pinning -----------------------------------------------------------------------------------------------------------------------
PINNED = ["/entities", "/entities/crude_oil", "/entities/crude_oil/attributes", "/entities/crude_oil/attributes/price",
          "/entities/crude_oil/attributes/price/observations", "/entities/crude_oil/attributes/price/states",
          "/entities/acme_motors/compositions", "/entities/acme_motors/paths", "/entities/acme_motors/construction",
          "/relationships", "/relationships/m24", "/relationships/m24/evidence", "/concepts", "/groups", "/graph"]


@pytest.mark.parametrize("path", PINNED)
def test_every_pinned_read_answers_a_version_and_refuses_what_is_not_held(c, moved, path):
    latest = c.get(WM).json()["meta"]["version"]["number"]
    for v in (1, moved["version"]["number"], latest):
        body = c.get(WM + path, params={"version": v}).json()
        assert body["meta"]["version"]["number"] == v and body["meta"]["version"]["latest"] == latest
    problem(c.get(WM + path, params={"version": latest + 1}), 404, "version_not_found")
    problem(c.get(WM + path, params={"version": 0}), 422, "invalid_request")
    problem(c.get(WM + path, params={"as_of": "2001-01-01T00:00:00Z"}), 404, "version_not_found")
    dated = c.get(WM + path, params={"as_of": "2100-01-01T00:00:00"}).json()
    assert 1 <= dated["meta"]["version"]["number"] <= latest


def test_a_pinned_read_shows_the_state_before_a_change(c, moved):
    v = moved["version"]["number"]
    then = c.get(f"{WM}/entities/crude_oil/attributes/price", params={"version": v})
    assert data(then) == moved["crude"] and then.headers["etag"] == f'"{moved["version"]["state_hash"]}"'
    now = data(c.get(f"{WM}/entities/crude_oil/attributes/price"))
    assert abs(now["level"]["mean"] - 103) < abs(moved["crude"]["level"]["mean"] - 103)
    dated = data(c.get(f"{WM}/entities/crude_oil/attributes/price", params={"as_of": "2026-08-31T23:59:59Z"}))
    assert abs(dated["level"]["mean"] - moved["crude"]["level"]["mean"]) < abs(now["level"]["mean"]
                                                                              - moved["crude"]["level"]["mean"])


def test_an_unchanged_read_is_a_304(c):
    r = c.get(f"{WM}/entities/acme_motors")
    again = c.get(f"{WM}/entities/acme_motors", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.headers["etag"] == r.headers["etag"] and not again.content
    assert c.get(f"{WM}/entities/acme_motors", headers={"If-None-Match": '"other"'}).status_code == 200
