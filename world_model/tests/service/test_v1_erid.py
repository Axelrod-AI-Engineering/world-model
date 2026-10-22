"""The unified world model, `/v1/erid` (api/v1/routes_erid.py, compartments.py; docs/design/api.md §4): the whole
graph for internal staff, compartments narrowed as a focused world is, the same reads and scopes as a world model,
and what the unified model learns reaching its compartments."""

from __future__ import annotations

import pytest

from axelrod_wm.api.v1 import compartments as comps
from tests.service.helpers import V1, WM, Signer, data, decide_all, problem, propose, service, upload

SIGNER = Signer()
E = f"{V1}/erid"
KEY, ACME, BETA = "k" * 32, "a" * 32, "b" * 32
ENV = dict(WORLD_MODEL_API_KEYS=(f"tester:{KEY}:default:world_model:read+documents:create+changes:create,"
                                 f"acme-svc:{ACME}:acme,beta-svc:{BETA}:beta"),
           WORLD_MODEL_COMPARTMENTS="acme_focus=acme")
FOCUS = {"compartment": "acme_focus"}


@pytest.fixture(scope="module")
def c():
    with service(SIGNER, **ENV) as client:
        yield client


def as_(key):
    return {"Authorization": f"Bearer {key}"}


def ids(rows):
    return {r["id"] for r in rows}


def test_the_unified_model_is_the_main_engines_whole_graph(c):
    r = c.get(E)
    u = data(r)
    assert u["id"] == "erid" and u["scenario"] == "acme_demo" and u["world_model_id"] == "acme_demo"
    assert u["compartment_ids"] == ["acme_focus"] and r.headers["etag"] == c.get(WM).headers["etag"]
    whole = data(c.get(WM))["counts"]
    assert (u["counts"]["entities"], u["counts"]["attributes"]) == (whole["entities"], whole["attributes"])
    assert u["counts"]["relationships"] == whole["relationships"]
    assert u["latest_version"] == r.json()["meta"]["version"]["number"]


def test_a_compartment_is_the_focused_world(c):
    """The compartment keeps what engine/focus.py keeps: the same entities and relationships as the focused scenario
    built from the unified one."""
    with service(SIGNER, scenario="acme_focus", WORLD_MODEL_API_KEYS=f"tester:{KEY}:default") as focused:
        own = ids(data(focused.get(f"{V1}/world-models/acme_focus/entities", params={"limit": 200})))
        own_rels = set()
        url, params = f"{V1}/world-models/acme_focus/relationships", {"limit": 200}
        while True:
            body = focused.get(url, params=params).json()
            own_rels |= ids(body["data"])
            if not body["meta"]["next_cursor"]:
                break
            params = {"limit": 200, "cursor": body["meta"]["next_cursor"]}
    assert ids(data(c.get(f"{E}/entities", params={**FOCUS, "limit": 200}))) == own
    assert {"acme_motors", "acme_re"} <= own and "acme_bank" not in own
    rels, params = set(), {**FOCUS, "limit": 200}
    while True:
        body = c.get(f"{E}/relationships", params=params).json()
        rels |= ids(body["data"])
        if not body["meta"]["next_cursor"]:
            break
        params = {**FOCUS, "limit": 200, "cursor": body["meta"]["next_cursor"]}
    assert rels == own_rels
    comp = data(c.get(f"{E}/compartments/acme_focus"))
    assert comp["companies"] == ["acme_motors", "acme_re"] and comp["base"] == "acme_demo"
    assert comp["counts"]["entities"] == len(own) and comp["counts"]["relationships"] == len(own_rels)
    assert comp["counts"]["entities"] < data(c.get(E))["counts"]["entities"]


def test_mirrored_reads_narrow_to_the_compartment(c):
    problem(c.get(f"{E}/entities/acme_bank", params=FOCUS), 404, "entity_not_found")
    assert data(c.get(f"{E}/entities/acme_bank"))["id"] == "acme_bank"
    view = data(c.get(f"{E}/entities/acme_motors/construction", params=FOCUS))
    assert view["entity_id"] == "acme_motors" and view["compositions"] and view["paths"]
    tr = data(c.get(f"{E}/entities/acme_motors/traces", params={**FOCUS, "from": "dollar.index"}))
    assert tr["reaches_endpoint"]
    g = data(c.get(f"{E}/graph", params={**FOCUS, "entities": "acme_motors", "depth": 1}))
    assert "acme_motors" in {e["id"] for e in g["entities"]} and "acme_bank" not in {e["id"] for e in g["entities"]}
    att = data(c.get(f"{E}/entities/acme_motors/attributes/operating_profit", params=FOCUS))
    assert att == data(c.get(f"{WM}/entities/acme_motors/attributes/operating_profit"))
    pinned = c.get(f"{E}/entities", params={**FOCUS, "version": 1, "limit": 1}).json()
    assert pinned["meta"]["version"]["number"] == 1 and pinned["meta"]["next_cursor"]
    nxt = c.get(f"{E}/entities", params={**FOCUS, "cursor": pinned["meta"]["next_cursor"]}).json()
    assert nxt["meta"]["version"]["number"] == 1
    assert data(c.get(f"{E}/versions"))[0]["number"] >= 1
    problem(c.get(f"{E}/entities", params={"compartment": "nope"}), 404, "compartment_not_found")
    problem(c.get(f"{E}/compartments/nope"), 404, "compartment_not_found")


def test_whole_graph_for_internal_staff_a_compartment_for_its_organization(c):
    problem(c.get(E, headers=as_(ACME)), 403, "internal_only")
    problem(c.get(f"{E}/entities", headers=as_(ACME)), 403, "internal_only")
    assert ids(data(c.get(f"{E}/compartments", headers=as_(ACME)))) == {"acme_focus"}
    assert "acme_motors" in ids(data(c.get(f"{E}/entities", params={**FOCUS, "limit": 200}, headers=as_(ACME))))
    assert data(c.get(f"{E}/compartments", headers=as_(BETA))) == []
    problem(c.get(f"{E}/entities", params=FOCUS, headers=as_(BETA)), 404, "compartment_not_found")
    problem(c.get(f"{E}/compartments/acme_focus", headers=as_(BETA)), 404, "compartment_not_found")
    # the unified model's own world model route stays its owner's
    problem(c.get(WM, headers=as_(ACME)), 404, "world_model_not_found")


def test_scopes_apply_as_on_a_world_model(c):
    admin_only = SIGNER.bearer(scope="admin")
    for url in (E, f"{E}/compartments", f"{E}/compartments/acme_focus", f"{E}/entities"):
        problem(c.get(url, headers=admin_only), 403, "insufficient_scope")


def test_what_the_unified_model_learns_reaches_the_compartment(c):
    before = c.get(f"{E}/entities/acme_motors", params=FOCUS).json()["meta"]["version"]["number"]
    res = upload(c, b"Oct 25, 2026. The dollar index rose to 104 as the dollar strengthened.", "dollar.txt")
    propose(c, res["bundle_id"])
    decide_all(c, SIGNER)
    assert c.get(f"{E}/entities/acme_motors", params=FOCUS).json()["meta"]["version"]["number"] > before


def test_compartment_configuration(monkeypatch):
    monkeypatch.delenv("WORLD_MODEL_INTERNAL_ORGS", raising=False)
    assert comps.internal_orgs("main") == frozenset({"main"})
    monkeypatch.setenv("WORLD_MODEL_INTERNAL_ORGS", "axelrod, ops ,")
    assert comps.internal_orgs("main") == frozenset({"axelrod", "ops"})
    monkeypatch.setenv("WORLD_MODEL_COMPARTMENTS", " a=x , b = y ,")
    assert comps.owners() == {"a": "x", "b": "y"}
    monkeypatch.setenv("WORLD_MODEL_COMPARTMENTS", "nobody")
    with pytest.raises(RuntimeError, match="compartment=org"):
        comps.owners()
    assert comps.discover("no_such_scenario") == {}
    assert set(comps.discover("acme_demo")) == {"acme_focus"}
