"""The flowchart is well formed, states every stage's input and output, names real components, and points at
trace kinds the engine emits; docs/flowchart.svg is current."""

from __future__ import annotations

import pytest

from axelrod_wm.engine.contracts import CONTRACTS
from axelrod_wm.flows import FLOWS, INFERENCE, WORLD_MODEL
from axelrod_wm.flows.overview import render_overview_svg
from axelrod_wm.flows.render import flow_markdown, render_svg
from axelrod_wm.sim.examples.small import SMALL
from tests.where import FLOWCHART
from tests.where import SRC as _SRC

SRC = _SRC


def _source_text() -> str:
    return "\n".join(p.read_text() for p in SRC.rglob("*.py") if "flows" not in p.parts)


def test_learning_ends_in_review_and_commit_and_inference_stands_apart():
    assert list(FLOWS)[0] == "world-model" and len(FLOWS) == 14
    phases = [p.id for p in WORLD_MODEL.phases]
    assert phases == ["intake", "working", "long_term", "review", "commit"]
    # the person checks at the end of learning: review comes after both memories and before any commit
    assert phases.index("review") > phases.index("long_term") and phases.index("review") < phases.index("commit")
    for p in WORLD_MODEL.phases:
        assert p.input and p.output, f"{p.id} must state its input and output"
        for ex in p.examples:
            assert SMALL.example(ex).stage == p.id, (p.id, ex)
        assert p.flow in FLOWS, f"{p.id} has no flowchart of its own"
    # inference has its own overview and a flowchart per stage, and nothing in it writes either memory
    assert [p.id for p in INFERENCE.phases] == ["pose", "isolate", "isolated", "distributed", "unify", "read_out",
                                                "evaluate"]   # MECE, in the naming guide's terms
    for p in INFERENCE.phases:
        assert p.input and p.output and p.flow in FLOWS
        assert not any(n.writes for n in FLOWS[p.flow].nodes), p.flow
    assert not any(n.writes for n in INFERENCE.nodes)


@pytest.mark.parametrize("flow_id", sorted(FLOWS))
def test_flow_is_well_formed(flow_id):
    f = FLOWS[flow_id]
    ids = [n.id for n in f.nodes]
    assert len(ids) == len(set(ids)), "node ids are unique"
    phases = {p.id for p in f.phases}
    out = {i: [e for e in f.edges if e.src == i] for i in ids}
    into = {i: [e for e in f.edges if e.dst == i] for i in ids}
    for e in f.edges:
        assert e.src in ids and e.dst in ids, (e.src, e.dst)
    for n in f.nodes:
        assert n.phase in phases, n.id
        if n.kind == "end":
            assert not out[n.id], n.id
        else:
            assert out[n.id], f"{n.id} leads nowhere"
        if n.kind != "start":
            assert into[n.id], f"nothing leads to {n.id}"
        if n.kind == "decision":
            labels = [e.label for e in out[n.id]]
            assert len(labels) >= 2 and all(labels), f"decision {n.id} needs labeled answers"
        if not n.mandatory:
            assert n.when, f"optional step {n.id} must say when it runs"
            # the event can go around it: some step that leads to it also leads past it (a step that only follows
            # another optional step shares that step's condition)
            if not all(not f.node(e.src).mandatory for e in into[n.id]):
                assert any(e.dst != n.id for p in into[n.id] for e in out[p.src]), f"nothing skips {n.id}"


def test_flow_components_have_contracts():
    for f in FLOWS.values():
        for n in f.nodes:
            if n.component:
                assert n.component in CONTRACTS, f"{f.id}:{n.id} names unknown slot {n.component}"


def test_trace_kinds_exist_in_the_engine():
    text = _source_text()
    for f in FLOWS.values():
        for n in f.nodes:
            for k in n.trace:
                assert f'"{k}"' in text, f"{f.id}:{n.id} names trace kind {k}, which nothing emits"


def test_stage_flowcharts_render_with_their_loops_labeled():
    for f in FLOWS.values():
        svg = render_svg(f, bare=True)
        assert svg.startswith("<svg") and all(f'data-node="{n.id}"' in svg for n in f.nodes)
        index = {n.id: i for i, n in enumerate(f.nodes)}
        for e in f.edges:
            if index[e.dst] < index[e.src] and not f.node(e.dst).side:
                assert e.label, f"{f.id}: the loop {e.src} → {e.dst} needs a label"


def test_render_marks_every_node_and_the_text_lists_every_stage():
    svg = render_svg(WORLD_MODEL)
    assert svg.startswith("<svg")
    for n in WORLD_MODEL.nodes:
        assert f'data-node="{n.id}"' in svg
    optional = [n for n in WORLD_MODEL.nodes if not n.mandatory]
    assert svg.count(" optional\"") + svg.count(" optional ") >= len(optional)
    md = flow_markdown(WORLD_MODEL)
    for p in WORLD_MODEL.phases:
        assert f"## {p.title}" in md and p.input in md and p.output in md


def test_docs_flowchart_is_current():
    path = FLOWCHART
    assert path.exists(), "run `axelrod flows --svg docs/flowchart.svg`"
    assert path.read_text() == render_overview_svg(), "docs/flowchart.svg is stale: run `axelrod flows --svg docs/flowchart.svg`"


def test_overview_follows_the_flows():
    """The README picture draws every stage of learning and of inference, by its title."""
    svg = render_overview_svg()
    for p in (*WORLD_MODEL.phases, *INFERENCE.phases):
        assert p.title.replace("&", "&amp;") in svg
