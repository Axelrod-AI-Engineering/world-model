"""Nested superentities in the view the canvas reads, and the optional language-model names (api/hierarchy.py,
api/views.py, POST /api/clusters/relabel). A built small demo stands in for a large model: the thresholds under which a
model is shown flat, and the size of a group, are lowered for these tests."""

from __future__ import annotations

import json

import pytest

from axelrod_wm.api import hierarchy as H
from axelrod_wm.api import views
from tests.integration.test_cov_api_routes import demo
from tests.unit.api.test_hierarchy import FakeProvider


@pytest.fixture
def built(monkeypatch):
    monkeypatch.setattr(H, "MIN_ENTITIES", 3)
    monkeypatch.setattr(H, "LEAF_MAX", 3)          # the built small demo has eight entities: split them into groups of three
    monkeypatch.setattr(H, "MIN_CLUSTER", 2)
    monkeypatch.setattr(H, "_MEMO", H.OrderedDict())
    monkeypatch.setattr(H, "LABELS", None)
    with demo(build=True) as c:
        monkeypatch.setattr(H, "LABELS", H.ClusterLabels(c.app.state.lake, None))     # what create_app sets: off
        yield c


def test_the_state_carries_the_groups(built):
    state = built.get("/api/state").json()
    cs = state["clusters"]
    assert cs and cs[0]["parent"] is None
    ids = {e["id"] for e in state["entities"]}
    assert all(set(c["members"]) <= ids and c["label"] for c in cs)
    # the same model, asked twice, answers with the same bytes
    again = built.get("/api/state").json()["clusters"]
    assert json.dumps(again, sort_keys=True) == json.dumps(cs, sort_keys=True)
    # a model under the threshold is shown flat
    H._MEMO.clear()
    H.MIN_ENTITIES = 10_000
    try:
        assert built.get("/api/state").json()["clusters"] == []
    finally:
        H.MIN_ENTITIES = 3


def test_relabelling_with_no_provider_calls_nothing(built):
    r = built.post("/api/clusters/relabel")
    assert r.status_code == 501 and "no language model" in r.json()["detail"]
    H.LABELS = None
    assert built.post("/api/clusters/relabel").status_code == 501


def test_relabelling_names_each_group_once_and_keeps_the_names(built):
    prov = FakeProvider([f"Name {k}" for k in range(500)])
    H.LABELS = H.ClusterLabels(built.app.state.lake, prov)
    before = built.get("/api/state").json()["clusters"]
    assert all(c["source"] == "keywords" for c in before)
    out = built.post("/api/clusters/relabel").json()
    assert out == {"relabelled": len(before), "failed": 0, "provider": "fake"}
    named = built.get("/api/state").json()["clusters"]
    assert [c["label"] for c in named] == [f"Name {k}" for k in range(len(before))]
    assert all(c["source"] == "llm" and c["keywords"] for c in named)
    calls = len(prov.calls)
    # asking again changes nothing and calls nobody; a new process with the same cache reads the same names
    assert built.post("/api/clusters/relabel").json()["relabelled"] == 0 and len(prov.calls) == calls
    H.LABELS = H.ClusterLabels(built.app.state.lake, FakeProvider([]))
    assert [c["label"] for c in built.get("/api/state").json()["clusters"]] == [c["label"] for c in named]


def test_the_view_model_round_trips_a_cluster():
    c = views.ClusterView(id="cl-1", parent=None, depth=1, label="A · B", keywords=["a", "b"], source="keywords", size=3,
                          subentities=9, children=[], entity_ids=["x", "y", "z"], members=["x", "y", "z"])
    assert views.ClusterView(**c.model_dump()) == c
