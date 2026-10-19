"""Forecast briefs (api/brief.py) on a built small demo: a shocked thesis, a policy what-if, and a baseline, and the
helpers for scoring news, tracking, and the timeline on edge cases."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from axelrod_wm.api import brief
from tests.integration.test_cov_api_routes import QUESTION, demo


@pytest.fixture(scope="module")
def built():
    with demo(build=True) as c:
        yield c


def test_a_shocked_thesis_brief(built):
    fid = built.post("/api/theses", json={"question": QUESTION}).json()["forecast"]["id"]
    b = built.get(f"/api/forecasts/{fid}/brief").json()
    assert b["forecast_id"] == fid and b["bottom_line"].startswith("By ")
    assert b["why"] and b["watch"] and b["timeline"]
    assert any("synthetic" in c for c in b["caveats"])


def test_a_baseline_brief_has_nothing_material(built):
    fc = built.post("/api/theses", json={"id": "T-b", "question": "baseline", "mode": "open_ended", "horizon_days": 20,
                                         "targets": ["delta.avg_fare"],
                                         "event": {"occurred_at": "2026-05-20T00:00:00Z", "ops": []}}).json()["forecast"]
    b = built.get(f"/api/forecasts/{fc['id']}/brief").json()
    assert "no target is expected to move" in b["bottom_line"]
    assert b["why"] == [] and b["watch"] == [] and b["transmission"]["steps"] == []


def test_name_helpers_fall_back_to_ids():
    g = NS(subentities={}, entities={}, interactions={"i1": NS(label="")})
    ltm = NS(object_generalizations=NS(patterns={"P1": NS(name="Group")}))
    sub, ent_of, ent, link, pattern = brief._name_fns(g, ltm)
    assert sub("delta.avg_fare") == "avg fare" and ent_of("delta.avg_fare") == "delta" and ent("x") == "x"
    assert link("i1") == "i1" and link("i2") == "i2"
    assert pattern("P1") == "P1 · Group" and pattern("P2") == "P2"


def test_onset():
    assert brief._onset([0, 5, 10], [0.0, 0.3, 1.0], 1.0) == 10
    assert brief._onset([0, 5], [0.0, 0.0], 0.0) == 5
    assert brief._onset([], [], 0.0) == 0


def test_tracking_edges():
    q = NS(q05=-1.0, q25=-0.5, q50=0.0, q75=0.5, q95=1.0)
    zs = {"a": [q] * 10, "b": [q], "c": [q] * 10, "d": [q] * 10, "e": [q] * 10}
    z = {"a": 0.2, "c": 0.8, "d": 2.0, "e": None}
    dev = NS(z_at=lambda sid, d: z.get(sid, -2.0) if sid != "e" else None)
    ctl = NS(engine=NS(wm=NS(deviations=dev, last_processed_day=5)))
    fc = NS(start_day=0, targets=["a", "b", "c", "d", "e", "f"], z_summary={**zs, "f": [q] * 10})
    rows = {r["id"]: r["where"] for r in brief._tracking(ctl, fc, lambda s: s)}
    assert rows == {"a": "inside the 50% band", "c": "inside the 90% band", "d": "above the 90% band",
                    "f": "below the 90% band"}
    assert brief._tracking(ctl, NS(start_day=None), str) == []
    assert brief._tracking(ctl, NS(start_day=9), str) == []


def test_event_footprints_and_scores():
    def op(kind, **kw):
        return NS(op=kind, **kw)

    conc = NS(kind="concrete", subentity_id="x.a")
    proposals = {
        "p1": NS(market_event_id="ME-1", status="approved", event=NS(ops=[
            op("change_value", target=conc), op("reweight_interaction", interaction_id="i1"),
            op("retire_interaction", interaction_id="i9")])),
        "p2": NS(market_event_id="ME-D-1", status="approved", event=NS(ops=[])),        # routine data
        "p3": NS(market_event_id="ME-2", status="rejected", event=NS(ops=[])),
        "p4": NS(market_event_id=None, status="approved", event=NS(ops=[])),
        "p5": NS(market_event_id="ME-3", status="approved", event=NS(ops=[op("change_value", target=NS(kind="abstract"))])),
        "p6": NS(market_event_id="ME-gone", status="approved", event=NS(ops=[op("change_value", target=conc)]))}
    trace = [NS(kind="fold.posterior", scope="ME-1", payload={"subentity_id": "x.a", "z": 1.0}),
             NS(kind="fold.posterior", scope="ME-1", payload={"subentity_id": "x.b", "z": None}),
             NS(kind="fold.posterior", scope="ME-other", payload={}),
             NS(kind="other", scope="ME-1", payload={}),
             NS(kind="fold.posterior", scope=None, payload={})]
    ctl = NS(proposals=proposals, engine=NS(tracer=NS(events=trace)),
             market_events={"ME-1": NS(headline="h1", source="s", channel="scraper", published_at=None, occurred_at=None),
                            "ME-3": NS(headline="h3", published_at=None, occurred_at=None)})
    fp = brief._event_footprints(ctl)
    assert set(fp) == {"ME-1", "ME-3", "ME-gone"} and fp["ME-1"]["moves"] == {"x.a": 1.0}
    assert fp["ME-1"]["ints"] == {"i1"}
    graph = NS(interactions={"i1": NS(label="raises", source_id="x.s", target_id="x.a")})
    ex = NS(top_paths=[NS(shock_id="x.s", interaction_ids=["i1"], share=1.0, target_id="x.a")])
    thesis = NS(event=NS(ops=[op("change_value", target=NS(kind="abstract")), op("change_value", target=conc)]))
    fc = NS(effect_summary={"x.a": [NS(q50=0.5)], "x.z": []}, movers=None, created_at=None, targets=["x.a"],
            networks=[NS(subentity_ids=["x.a", "x.n"]), NS()])
    rows = brief._score_events(ctl, fc, ex, thesis, graph, lambda s: s)
    assert [r["id"] for r in rows] == ["ME-1"]
    r = rows[0]
    assert r["stance"] == "supports" and r["relevance"] == 1.0 and r["after"] is False and r["published_at"] is None
    assert any("principal channel" in x for x in r["reasons"])


def test_a_brief_with_parts_missing(monkeypatch):
    """Targets with no effects, paths with no links or links since retired, and a scenario without a watchlist."""
    with demo(build=True) as c:
        ctl = c.app_state.runner.controller
        fc = ctl.pose_thesis(ctl.thesis_from_question(QUESTION))
        ex = ctl.explanation(fc.explanation_id)
        fc.targets.append("zzz.none")
        ex.top_paths[:0] = [NS(shock_id="resources_energy.oil_price", target_id="delta.avg_fare", share=0.1,
                               interaction_ids=[]),
                            NS(shock_id="resources_energy.oil_price", target_id="delta.avg_fare", share=0.1,
                               interaction_ids=["int-gone"])]
        monkeypatch.setattr(ctl, "watchlist", lambda: None)
        b = brief.brief_view(ctl, fc.id)
        assert "zzz.none" not in {e["id"] for e in b["effects"]}
        assert b["transmission"]["watchlist"] is None
        assert b["why"][1]["text"].endswith("int-gone ?")


def test_timeline_rows_for_groups():
    q = NS(q05=-0.2, q50=0.3, q95=0.6)
    groups = [NS(id="g0", effect_summary=[]),
              NS(id="g1", effect_summary=[NS(q05=0, q50=0.01, q95=0.02)]),
              NS(id="g2", name="Airlines", kind="sector", members=["a", "b"], effect_summary=[NS(q05=0, q50=0.0, q95=0), q])]
    rows = brief._timeline_rows(NS(effect_summary={}), str, str, str, ["d0", "d1"], groups, {}, {"values": []})
    assert [r["ref"] for r in rows] == ["g2"] and rows[0]["onset"] == "d1" and rows[0]["members"] == 2
