"""A compartment per login (Oct 25): the unified demo (acme_demo's and northwind_demo's worlds merged) runs as the main
engine, and two logins whose scenarios are focuses over it are views onto that one engine, not engines of their own.

Northwind's compartment is northwind_air, crude_oil, and jet_fuel; Acme's is acme_motors, acme_re, and the players
around them. Each test reads, asks, or writes as a login and checks that nothing outside its compartment shows."""

from __future__ import annotations

import json
import re

import pytest

from tests.integration.service.conftest import SIGNER, upload
from tests.service.helpers import data, problem, service

pytestmark = pytest.mark.integration
KA, KN, KM = "a" * 32, "n" * 32, "m" * 32
SCOPES = "world_model:read+documents:create+changes:create+simulations:create+admin"
ENV = {"WORLD_MODEL_BASIC_AUTH_USERNAME": "admin", "WORLD_MODEL_BASIC_AUTH_PASSWORD": "pw-admin",
       "WORLD_MODEL_LOGINS": "acme:pw-acme:acme_unified_focus,nw:pw-nw:northwind_focus",
       "WORLD_MODEL_API_KEYS": f"main:{KM}:admin:{SCOPES},acme:{KA}:acme:{SCOPES},nw:{KN}:nw:{SCOPES}"}
MAIN, ACME, NW = ({"Authorization": f"Bearer {k}"} for k in (KM, KA, KN))
U, WA, WN = "/v1/world-models/unified_demo", "/v1/world-models/acme_unified_focus", "/v1/world-models/northwind_focus"
NW_OWN = {"crude_oil", "jet_fuel", "northwind_air"}
CRUDE_NOTE = b"Data, September 1, 2026. The central bank held rates at 4.0%. The crude price rose to $103 a barrel."


def sign_in(c, user: str) -> None:
    c.cookies.clear()
    r = c.post("/login", data={"username": user, "password": f"pw-{user}", "next": "/"}, follow_redirects=False)
    assert r.status_code == 303


def keep(c, path: str, headers: dict | None = None, **params) -> list:
    return data(c.get(path, params={"limit": 200, **params}, headers=headers or {}))


class Outside:
    """What a compartment must never show: every entity and value of the unified model that is not in it, by id, and
    every outside company by name."""

    def __init__(self, c, inside: set[str]) -> None:
        rows = keep(c, f"{U}/entities", MAIN)
        gone = [e for e in rows if e["id"] not in inside]
        self.ids = [e["id"] for e in gone]
        names = [e["name"] for e in gone if e["type"] == "company"]
        self.pattern = re.compile("|".join([rf"(?<![\w:]){re.escape(i)}(?![\w])" for i in self.ids]
                                           + [re.escape(n) for n in names]), re.I)

    def found(self, text: str) -> list[str]:
        return sorted({m.group(0) for m in self.pattern.finditer(text)})


@pytest.fixture(scope="module")
def run():
    with service(SIGNER, scenario="unified_demo", **ENV) as c:
        yield c


def test_a_compartment_login_is_a_view_onto_the_main_engine_and_owns_its_compartment(run):
    state = run.app.state
    assert set(state.views) == {"acme", "nw"} and state.axelrod_by_login == {}
    assert state.axelrod.first_scenario == "unified_demo"
    assert [m["id"] for m in data(run.get("/v1/world-models", headers=MAIN))] == ["unified_demo"]
    assert [m["id"] for m in data(run.get("/v1/world-models", headers=NW))] == ["northwind_focus"]
    assert [m["id"] for m in data(run.get("/v1/world-models", headers=ACME))] == ["acme_unified_focus"]
    whole = data(run.get(U, headers=MAIN))["counts"]
    mine = data(run.get(WN, headers=NW))["counts"]
    assert whole["entities"] == 24 and mine["entities"] == 3 and mine["attributes"] < whole["attributes"]


def test_v1_reads_show_only_the_compartment_and_an_outside_id_is_a_404(run):
    out = Outside(run, NW_OWN)
    assert "harbor_steel" in out.ids and "central_bank" in out.ids
    assert {e["id"] for e in keep(run, f"{WN}/entities", NW)} == NW_OWN
    seen = []
    for path in ("", "/entities", "/entities/northwind_air", "/entities/northwind_air/attributes",
                 "/entities/northwind_air/construction", "/entities/crude_oil/attributes/price",
                 "/entities/crude_oil/attributes/price/observations", "/relationships", "/graph", "/concepts", "/groups",
                 "/versions", "/changes", "/events", "/documents", "/simulations"):
        r = run.get(WN + path, params={"limit": 200}, headers=NW)
        assert r.status_code == 200, (path, r.text)
        seen.append(r.text)
    assert out.found("\n".join(seen)) == []
    # by id: another company, its value, one of its links, its group: none is here
    for path, code, asked in (("/entities/harbor_steel", "entity_not_found", "harbor_steel"),
                              ("/entities/acme_motors", "entity_not_found", "acme_motors"),
                              ("/entities/harbor_steel/attributes/operating_profit", "entity_not_found", "harbor_steel"),
                              ("/relationships/n04", "relationship_not_found", "n04"),
                              ("/relationships/m02", "relationship_not_found", "m02")):
        body = problem(run.get(WN + path, headers=NW), 404, code)
        said = json.dumps({k: v for k, v in body.items() if k != "instance"})
        assert out.found(said.replace(asked, "")) == [] and body["detail"].endswith(asked)
    # the main model and the other compartment do have them
    assert run.get(f"{U}/entities/harbor_steel", headers=MAIN).status_code == 200
    assert run.get(f"{WA}/entities/acme_motors", headers=ACME).status_code == 200
    # one organization cannot read another's compartment as its own model
    problem(run.get(f"{WN}/entities", headers=ACME), 404, "world_model_not_found")


def test_search_finds_no_outside_name(run):
    out = Outside(run, NW_OWN)
    for q in ("Harbor Steel", "harbor", "Acme Motors", "central bank", "steel", "operating profit"):
        for mode in ("keyword", "prefix", "semantic", "graph", "hybrid"):
            hits = data(run.get(f"{WN}/search", params={"q": q, "mode": mode}, headers=NW))
            assert out.found(json.dumps(hits)) == [], (q, mode)
    named = data(run.get(f"{WN}/search", params={"q": "Northwind Air", "mode": "graph"}, headers=NW))
    assert named and named[0]["entity_id"] == "northwind_air"
    # the whole model finds them
    assert data(run.get(f"{U}/search", params={"q": "Harbor Steel", "mode": "graph"}, headers=MAIN))


def test_the_browser_reads_show_only_the_compartment(run):
    out = Outside(run, NW_OWN)
    sign_in(run, "nw")
    assert run.get("/api/session").json() == {"login": "nw"}
    texts = []
    for path in ("/api/state", "/api/memory", "/api/frontier", "/api/hypotheses", "/api/learning-tasks", "/api/checks", "/api/versions", "/api/demos",
                 "/api/scenarios", "/api/config", "/api/context/v4", "/api/forecasts", "/api/proposals",
                 "/api/market-events", "/api/updates", "/api/decisions", "/api/scenario-theses", "/api/find?q=steel",
                 "/api/find?q=crude", "/api/entities/jet_fuel", "/api/sim/status", "/api/sim/script", "/api/trace",
                 "/api/layouts/figure1", "/api/vocabulary", "/api/import/local", "/api/import/documents", "/api/health"):
        r = run.get(path)
        assert r.status_code == 200, (path, r.text)
        texts.append(r.text)
    assert out.found("\n".join(texts)) == []
    state = run.get("/api/state").json()
    assert {e["id"] for e in state["entities"]} == NW_OWN
    # the taxonomies are the shared vocabulary (concepts such as "Capital markets"); what hangs on them is the compartment's
    for kind in ("object", "interaction"):
        nodes = run.get(f"/api/taxonomies/{kind}").json()["nodes"]
        assert out.found(" ".join(i for n in nodes for i in n["instance_ids"])) == []
    assert {i for n in run.get("/api/taxonomies/object").json()["nodes"] for i in n["instance_ids"]} >= {"crude_oil"}
    # an outside id is a 404 that says only what was asked
    for path in ("/api/entities/harbor_steel", "/api/interactions/n04", "/api/superentities/N2"):
        r = run.get(path)
        assert r.status_code == 404 and r.json() == {"detail": f"not found: {path.rsplit('/', 1)[-1]}"}
    # what is for the whole model only is refused, not narrowed
    for path in ("/api/repo/log", "/api/repo/commits/1", "/api/repo/diff?from=1"):
        assert run.get(path).status_code == 409
    sign_in(run, "admin")
    assert {e["id"] for e in run.get("/api/state").json()["entities"]} >= {"harbor_steel", "northwind_air"}


def test_the_demo_menu_offers_a_compartment_only_itself(run):
    sign_in(run, "nw")
    menu = run.get("/api/demos").json()
    assert menu["current"] == "northwind_focus" and [d["id"] for d in menu["demos"]] == ["northwind_focus"]
    assert menu["demos"][0]["label"] == "Unified demo, Northwind compartment" and menu["switching"] is None
    for demo in ("unified_demo", "small_demo", "acme_unified_focus"):
        assert run.post(f"/api/demos/{demo}").status_code == 404
    assert [s["id"] for s in run.get("/api/scenarios").json()] == ["northwind_focus"]
    assert run.post("/api/sim/reset-all").status_code == 409 and run.post("/api/sim/load", json={}).status_code == 409
    assert run.post("/api/sim/step").status_code == 409
    sign_in(run, "admin")
    assert run.get("/api/demos").json()["current"] == "unified_demo"
    assert {"northwind_focus", "unified_demo"} <= {s["id"] for s in run.get("/api/scenarios").json()}


QUESTION = "What if oil prices rose by 20% next quarter?"


def test_a_forecast_on_a_compartment_runs_on_it_alone_and_leaves_the_main_engine_as_it_was(run):
    out = Outside(run, NW_OWN)
    ctl = run.app.state.axelrod.runners["unified_demo"].controller
    before = (ctl.engine.version, ctl.engine.state_hash, len(ctl.forecasts), dict(ctl.engine.wm.forecast_layer.by_thesis),
              ctl.engine.ledger.next_seq)
    sign_in(run, "nw")
    posed = run.post("/api/theses", json={"question": QUESTION})
    assert posed.status_code == 200 and out.found(posed.text) == []
    fid = posed.json()["forecast"]["id"]
    texts = [run.get(p).text for p in (f"/api/forecasts/{fid}", f"/api/forecasts/{fid}/brief", f"/api/paths/forecast/{fid}",
                                       "/api/forecasts", f"/api/context/v4?forecast={fid}", "/api/trace",
                                       "/api/learning-tasks", "/api/state")]
    explanation = run.get(f"/api/explanations/{posed.json()['explanation']['id']}")
    assert explanation.status_code == 200
    assert out.found("\n".join([*texts, explanation.text])) == []
    # the questions the compartment can ask are the ready-made ones it holds
    ready = {t["id"] for t in run.get("/api/scenario-theses").json()}
    assert ready == {"U-T1"}
    stored = run.post("/api/theses/U-T1/pose")
    assert stored.status_code == 200 and out.found(stored.text) == []
    # the engine the forecast was asked of is untouched: no version, no forecast, no state
    after = (ctl.engine.version, ctl.engine.state_hash, len(ctl.forecasts), dict(ctl.engine.wm.forecast_layer.by_thesis),
             ctl.engine.ledger.next_seq)
    assert after == before
    # asked again, it is a new forecast of the same thesis, and the earlier one stays
    again = run.post(f"/api/forecasts/{fid}/rerun")
    assert again.status_code == 200 and again.json()["forecast"]["id"] != fid
    assert {f["id"] for f in run.get("/api/forecasts").json()} >= {fid, again.json()["forecast"]["id"]}
    # the same question of the whole model reaches what the compartment does not hold, and is the main login's own
    sign_in(run, "admin")
    assert run.get("/api/forecasts").json() == []
    whole = run.post("/api/theses", json={"question": QUESTION})
    assert {"harbor_steel", "acme_motors"} <= set(out.found(whole.text))
    sign_in(run, "acme")
    assert run.get("/api/forecasts").json() == []


def test_a_simulation_through_v1_is_the_compartments_own(run):
    out = Outside(run, NW_OWN)
    thesis = data(run.post(f"{WN}/theses", json={"question": QUESTION}, headers=NW), 201)
    job = data(run.post(f"{WN}/theses/{thesis['id']}/simulations", headers=NW), 202)
    assert job["status"] == "succeeded", job
    sim = job["result"]["ids"][0]
    texts = [run.get(f"{WN}/simulations/{sim}{tail}", headers=NW) for tail in ("", "/transmission", "/coverage", "/brief")]
    assert all(r.status_code == 200 for r in texts)
    assert out.found("\n".join(r.text for r in texts)) == []
    ready = {t["id"] for t in keep(run, f"{WN}/theses", NW)}
    assert thesis["id"] in ready
    # a ready-made template the compartment does not hold is not there
    problem(run.post(f"{WN}/theses", json={"template_id": "U-T2"}, headers=NW), 404, "thesis_not_found")
    assert data(run.post(f"{WN}/theses", json={"template_id": "U-T1"}, headers=NW), 201)["id"] == "U-T1"
    # the other compartment and the whole model have none of it
    assert keep(run, f"{WA}/simulations", ACME) == [] or sim not in {s["id"] for s in keep(run, f"{WA}/simulations", ACME)}
    problem(run.get(f"{WA}/simulations/{sim}", headers=ACME), 404, "simulation_not_found")
    problem(run.get(f"{U}/simulations/{sim}", headers=MAIN), 404, "simulation_not_found")


BUNDLE = {
    "format": "axelrod.import/v1", "title": "Mixed bundle (synthetic)", "collected_by": "test", "synthetic": True,
    "items": [
        {"id": "X-OUT", "published_at": "2026-09-12T10:00:00Z", "source": "Synthetic desk", "source_type": "broker_research",
         "kind": "analyst", "headline": "Harbor Steel's profit beats", "summary": "Harbor Steel reported a larger profit.",
         "entities": ["harbor_steel"], "relevance": 0.8,
         "signals": [{"type": "observe", "value_of": "harbor_steel.operating_profit", "value": 700.0, "quote": "larger profit"}]},
        {"id": "X-IN", "published_at": "2026-09-13T10:00:00Z", "source": "Synthetic desk", "source_type": "data",
         "kind": "data", "headline": "Jet fuel rises", "summary": "Jet fuel rose to 2.9 a gallon.",
         "entities": ["jet_fuel"], "relevance": 0.8,
         "signals": [{"type": "observe", "value_of": "jet_fuel.price", "value": 2.9, "quote": "rose to 2.9 a gallon"}]},
        {"id": "X-MIX", "published_at": "2026-09-14T10:00:00Z", "source": "Synthetic desk", "source_type": "data",
         "kind": "data", "headline": "Fuel and steel", "summary": "Jet fuel and steel both moved.",
         "entities": ["jet_fuel"], "relevance": 0.8,
         "signals": [{"type": "observe", "value_of": "jet_fuel.price", "value": 3.0},
                     {"type": "observe", "value_of": "harbor_steel.operating_profit", "value": 650.0}]},
    ]}


def settle(c, timeout: float = 60.0) -> dict:
    import time

    t0 = time.time()
    while time.time() - t0 < timeout:
        st = c.get("/api/sim/status").json()
        if st["state"] != "running":
            return st
        time.sleep(0.1)
    raise AssertionError("the import kept running")


def test_an_import_from_a_compartment_drops_what_is_about_other_companies_and_goes_to_the_main_engine(run):
    ctl = run.app.state.axelrod.runners["unified_demo"].controller
    sign_in(run, "nw")
    preview = run.post("/api/import/preview", json={"bundle": BUNDLE})
    assert preview.status_code == 200, preview.text
    preview = preview.json()
    assert [i["id"] for i in preview["items"]] == ["X-IN"]
    assert run.post("/api/import/preview", json={"bundle": {"items": [{"id": 1}]}}).status_code in (400, 409, 422)
    assert run.get("/api/import/local").json() == [] and run.get("/api/import/local/x.json").status_code == 409
    lonely = {**BUNDLE, "items": [BUNDLE["items"][0], BUNDLE["items"][2]]}      # about another company, or touching it
    refused = run.post("/api/import", json={"bundle": lonely})
    assert refused.status_code == 409 and "nothing new to import" in refused.text
    done = run.post("/api/import", json={"bundle": BUNDLE})
    assert done.status_code == 200, done.text
    out = done.json()
    assert out["imported"] == ["X-IN"] and out["proposal"]["proposal"]["market_event_id"] == "IM-X-IN"
    status = settle(run)
    assert status["state"] == "awaiting_review" and status["pending_proposals"] == 1
    # the proposal waits on the main engine, in the main login's queue too, and names nothing outside
    proposal_id = out["waiting_on"]
    assert ctl.proposals[proposal_id].status == "pending"
    assert [p["proposal"]["id"] for p in run.get("/api/proposals?status=pending").json()] == [proposal_id]
    ev = run.get("/api/market-events").json()
    assert [e["id"] for e in ev] == ["IM-X-IN"]
    assert run.get(f"/api/updates/{out['update_id']}").status_code == 200
    # another compartment cannot see it, or decide it
    sign_in(run, "acme")
    assert run.get("/api/proposals").json() == [] and run.get("/api/market-events").json() == []
    assert run.get(f"/api/updates/{out['update_id']}").status_code == 409
    assert run.post(f"/api/proposals/{proposal_id}/approve", json={"by": "acme person"}).status_code == 409
    assert run.post(f"/api/proposals/{proposal_id}/reject", json={"by": "acme", "note": "no"}).status_code == 409
    assert run.post(f"/api/proposals/{proposal_id}/defer", json={"by": "acme"}).status_code == 409
    assert run.post(f"/api/updates/{out['update_id']}/continue").status_code == 409
    assert run.post(f"/api/updates/{out['update_id']}/cancel").status_code == 409
    # its own login decides it, on the main engine
    sign_in(run, "nw")
    version = ctl.engine.version
    jet, steel = (ctl.engine.wm.graph.subentities[s].level_mean for s in ("jet_fuel.price", "harbor_steel.operating_profit"))
    decided = run.post(f"/api/proposals/{proposal_id}/approve", json={"by": "nw person"})
    assert decided.status_code == 200 and decided.json()["proposal"]["status"] == "approved"
    assert settle(run)["state"] == "idle" and ctl.engine.version > version
    assert ctl.proposals[proposal_id].status == "approved"
    # the jet fuel price moved on the one engine; nothing was folded in on the other company's value
    level = lambda sid: ctl.engine.wm.graph.subentities[sid].level_mean     # noqa: E731
    assert level("jet_fuel.price") != jet and level("harbor_steel.operating_profit") == steel


def test_a_document_from_a_compartment_reads_against_the_compartment_and_is_held_for_its_organization(run):
    state = run.app.state
    res = upload(run, CRUDE_NOTE, "crude.txt", WN, NW)
    assert res["signals"] == 1                       # the central bank's rate is not in the compartment: no signal
    other = upload(run, CRUDE_NOTE, "crude.txt", U, MAIN)
    assert other["signals"] == 2 and other["document_id"] == res["document_id"]
    # each organization's lake partition holds its own copy
    assert [d.id for d in state.lake.list_documents("nw", limit=10)] == [res["document_id"]]
    assert [d.id for d in state.lake.list_documents("admin", limit=10)] == [res["document_id"]]
    assert state.lake.list_documents("acme", limit=10) == []
    problem(run.get(f"{WA}/documents/{res['document_id']}", headers=ACME), 404, "document_not_found")
    sign_in(run, "nw")
    docs = run.get("/api/import/documents").json()
    assert [d["id"] for d in docs] == [res["document_id"]]
    sign_in(run, "acme")
    assert run.get("/api/import/documents").json() == []
    assert run.post(f"/api/import/documents/{res['document_id']}").status_code == 404
    sign_in(run, "nw")
    view = run.post(f"/api/import/documents/{res['document_id']}")
    assert view.status_code == 200 and Outside(run, NW_OWN).found(view.text) == []


def test_erid_serves_each_login_its_own_compartment(run):
    from axelrod_wm.api.v1.compartments import discover

    assert set(discover("unified_demo")) == {"acme_unified_focus", "northwind_focus"}
    assert set(discover("acme_demo")) == {"acme_focus"}
    assert data(run.get("/v1/erid", headers=MAIN))["compartment_ids"] == ["acme_unified_focus", "northwind_focus"]
    problem(run.get("/v1/erid", headers=NW), 403, "internal_only")
    assert [c["id"] for c in keep(run, "/v1/erid/compartments", MAIN)] == ["acme_unified_focus", "northwind_focus"]
    assert [c["id"] for c in keep(run, "/v1/erid/compartments", NW)] == ["northwind_focus"]
    assert [c["id"] for c in keep(run, "/v1/erid/compartments", ACME)] == ["acme_unified_focus"]
    problem(run.get("/v1/erid/compartments/acme_unified_focus", headers=NW), 404, "compartment_not_found")
    assert data(run.get("/v1/erid/compartments/northwind_focus", headers=NW))["counts"]["entities"] == 3
    problem(run.get("/v1/erid/entities", headers=NW), 403, "internal_only")
    out = Outside(run, NW_OWN)
    ids = keep(run, "/v1/erid/entities", NW, compartment="northwind_focus")
    assert {e["id"] for e in ids} == NW_OWN
    seen = "\n".join(run.get(f"/v1/erid{path}", params={"compartment": "northwind_focus"}, headers=NW).text
                     for path in ("/entities", "/relationships", "/graph", "/versions"))
    assert out.found(seen) == []
    # the whole model's staff read a compartment as it is
    assert {e["id"] for e in keep(run, "/v1/erid/entities", MAIN, compartment="northwind_focus")} == NW_OWN
    assert len(keep(run, "/v1/erid/entities", MAIN)) == 24


def run_tools(c, headers: dict, script):
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def main():
        http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=c.app), base_url="http://wm", headers=headers)
        async with streamable_http_client("http://wm/mcp", http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as s:
                await s.initialize()

                async def tool(name: str, **args):
                    r = await s.call_tool(name, args)
                    text = r.content[0].text
                    return (True, text) if r.is_error else (False, json.loads(text))

                return await script(tool)

    return c.portal.call(main)


def test_the_mcp_tools_read_and_ask_the_compartment(run):
    out = Outside(run, NW_OWN)

    async def script(tool):
        got = {}
        for name, args in (("world_model_list_world_models", {}), ("world_model_get_world_model", {}),
                           ("world_model_list_entities", {"q": "steel"}), ("world_model_list_entities", {"q": "air"}),
                           ("world_model_get_entity", {"entity_id": "northwind_air"}),
                           ("world_model_graph", {}), ("world_model_list_relationships", {}),
                           ("world_model_search", {"q": "Harbor Steel"}), ("world_model_search", {"q": "crude"})):
            err, body = await tool(name, **args)
            assert not err, (name, body)
            got[name + json.dumps(args)] = json.dumps(body)
        err, text = await tool("world_model_get_entity", entity_id="harbor_steel")
        assert err and "harbor_steel" in text and out.found(text.replace("harbor_steel", "")) == []
        err, sim = await tool("world_model_simulate", question=QUESTION)
        assert not err
        got["sim"] = json.dumps(sim)
        err, brief = await tool("world_model_simulation_brief", simulation_id=sim["job"]["result"]["ids"][0])
        assert not err
        got["brief"] = json.dumps(brief)
        err, text = await tool("world_model_list_entities", world_model_id="unified_demo")
        assert err                                                  # the whole model is another organization's
        return got

    got = run_tools(run, NW, script)
    assert out.found("\n".join(got.values())) == []
    assert [e["id"] for e in json.loads(got['world_model_list_entities{"q": "air"}'])["data"]] == ["northwind_air"]
    assert json.loads(got['world_model_list_entities{"q": "steel"}'])["data"] == []
