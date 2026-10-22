"""Find's filters and words (api/find.py) and the checks view (api/checks.py) on a built small demo."""

from __future__ import annotations

import pytest

from axelrod_wm.api import checks, find
from tests.integration.test_cov_api_routes import demo


@pytest.fixture(scope="module")
def built():
    with demo(build=True) as c:
        yield c


def q(client, text):
    return client.get("/api/find", params={"q": text}).json()


def test_filters_parse():
    free, f = find._filters("moved up down learned hedged open>0.5 open<40% kind:airline fuel")
    assert free == ["fuel"] and f["open"] == ("<", 0.4) and f["kind"] == "airline"
    assert all(f[k] for k in ("moved", "up", "down", "learned", "hedged"))
    assert find._moved(1.2, {"up": True}) and not find._moved(-1.2, {"up": True})
    assert find._moved(-1.2, {"down": True}) and not find._moved(0.5, {})


def test_words_and_why(built):
    out = q(built, "the fuel cost")
    assert out["words"] == ["cost", "fuel"] and out["hits"]
    top = out["hits"][0]
    assert top["why"] and top["score"] >= out["hits"][-1]["score"]
    assert q(built, "zzzqqq")["hits"] == []


def test_open_and_kind_filters(built):
    wide = q(built, "open>0")
    assert wide["filters"]["open"] == [">", 0.0] and all(h["kind"] != "interaction" for h in wide["hits"])
    assert q(built, "open<0")["hits"] == []
    kinds = q(built, "kind:airline")
    assert kinds["hits"] and {h["kind"] for h in kinds["hits"]} <= {"entity", "subentity", "interaction"}


def test_edge_filters(built):
    learned = q(built, "learned")
    assert all(h["kind"] == "interaction" for h in learned["hits"])
    hedged = q(built, "hedged")
    assert all(h["kind"] == "interaction" for h in hedged["hits"])
    for f in ("moved", "up", "down"):
        out = q(built, f)
        assert all(h["kind"] in ("entity", "subentity", "interaction") for h in out["hits"]), f


def test_link_filters_skip_construction_links_unhedged_links_and_missing_ends(monkeypatch):
    from types import SimpleNamespace as NS

    from axelrod_wm.api import views

    tax = NS(nodes={})
    a = NS(id="x.a", entity_id="x", name="fuel cost", z=0.0, open=0.0, attribute_kind="cost", unit="usd")
    b = NS(id="y.b", entity_id="y", name="fuel price", z=0.0, open=0.0, attribute_kind="price", unit="usd")
    links = [NS(id="l0", source="x.a", target="gone.z", origin="learned", hedge=None, label="raises",
                generalization_id=None, effect=0.1),
             NS(id="l1", source="x.a", target="y.b", origin="construction", hedge=None, label="raises",
                generalization_id=None, effect=0.1),
             NS(id="l2", source="y.b", target="x.a", origin="learned", hedge="pending:E:0", label="raises",
                generalization_id=None, effect=0.1)]
    view = NS(entities=[], subentities=[a, b], links=links, hulls=[])
    monkeypatch.setattr(views, "build_graph_view", lambda *args: view)
    ctl = NS(engine=NS(wm=NS(graph=NS(entities={})), version=1,
                       ltm=NS(object_generalizations=NS(taxonomy=tax), interaction_generalizations=NS(taxonomy=tax))))
    assert [h["id"] for h in find.find(ctl, "learned")["hits"]] == ["l2"]
    assert [h["id"] for h in find.find(ctl, "hedged fuel")["hits"]] == ["l2"]
    assert {h["id"] for h in find.find(ctl, "fuel")["hits"]} == {"l1", "l2"}


def test_checks_view_lists_fading_groups_and_unverified_pairs(built):
    ctl = built.app_state.runner.controller
    ltm = ctl.engine.ltm
    pid, p = next((k, v) for k, v in ltm.object_generalizations.patterns.items() if str(v.status) == "admitted")
    old_support, old_day = p.support, p.last_counted_day
    co = next(v for v in ltm.correlation_frontier.entries.values() if str(v.status) == "holding")
    old_verified = co.last_verified_day
    try:
        p.support, p.last_counted_day = 0.0, None
        co.last_verified_day = None
        view = checks.checks_view(ctl)
    finally:
        p.support, p.last_counted_day, co.last_verified_day = old_support, old_day, old_verified
    fading = next(x for x in view["live"] if x["id"] == pid)
    assert fading["status"] == "fading" and fading["last"] is None and fading["progress"][0]["below"] is True
    pair = next(x for x in view["live"] if x["id"] == co.id)
    assert pair["last"] is None and pair["next"].startswith(f"from {view['today']}")
