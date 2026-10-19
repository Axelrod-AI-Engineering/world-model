"""Rendering a small hand-built flow that uses every shape and edge route, and the flow helpers."""

from __future__ import annotations

from axelrod_wm.flows import Flow, _flow, flow_path
from axelrod_wm.flows.render import _wrap, flow_markdown, layout, render_svg


def _tiny(terms=True, optional=True, decision=True, store=True, writes=True) -> Flow:
    nodes = [
        dict(id="s", label="Start", kind="start", phase="p1", trace=["t.start"]),
        dict(id="d", label="Is it new?", kind="decision" if decision else "step", phase="p1"),
        dict(id="side", label="Side step", side=True, phase="p1", mandatory=not optional,
             when="it is new" if optional else "", writes="working" if writes else ""),
        dict(id="loop", label="Re-stage", side=True, phase="p1", mandatory=not optional),
        dict(id="m", label="Main step", phase="p2", cadence="per day", trace=["t.main"]),
        dict(id="c", label="Commit", kind="store" if store else "step", phase="p2"),
        dict(id="l", label="Continue in inference", kind="link", link="inference", phase="p2"),
        dict(id="e", label="End", kind="end", phase="p2"),
    ]
    edges = [("s", "d"), ("d", "side", "yes"), ("side", "m", "back"), ("d", "m", "no"), ("m", "c"),
             ("m", "loop", ""), ("loop", "s", "again"), ("loop", "d"), ("c", "l"), ("l", "e"), ("d", "e", "skip", False),
             ("s", "c", "fast")]
    phases = [dict(id="p1", title="First", input="in", output="out"), dict(id="p2", title="Second"),
              dict(id="p3", title="Unused")]
    return _flow("tiny", "Tiny", "A small flow.", phases, nodes, edges,
                 [("Term", "What it means here.")] if terms else None)


def test_flow_lookups_and_path():
    f = _tiny()
    assert f.node("m").cadence == "per day" and f.phase("p2").title == "Second"
    assert flow_path(f, {"t.main", "t.start", "other"}) == ["s", "m"]
    assert flow_path(f, set()) == []
    assert f.edges[-2].drawn is False and f.edges[1].label == "yes"


def test_render_svg_draws_every_kind_and_route():
    svg = render_svg(_tiny())
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    for kind in ("start", "decision", "store", "link", "end"):
        assert f'data-kind="{kind}"' in svg
    assert 'data-link="inference"' in svg and "Continue in inference →" in svg
    assert "(optional: runs only if it is new)" in svg and "(optional)</title>" in svg
    assert "if it is new" in svg and "per day" in svg
    assert "Writes working memory" in svg
    assert 'data-src="d" data-dst="e"' not in svg                     # not drawn
    assert 'class="fl-edge side"' in svg                              # side routes
    assert ">again</text>" in svg and ">back</text>" in svg and ">fast</text>" in svg and ">yes</text>" in svg
    assert "optional step" in svg and "check (yes / no)" in svg and ">commit</text>" in svg and "WM / LTM" in svg
    assert ">Terms</text>" in svg and "What it means here." in svg
    bare = render_svg(_tiny(), bare=True)
    assert ">Terms</text>" not in bare and "fl-legend-g" not in bare and 'class="fl-title"' not in bare


def test_render_svg_minimal_legend():
    svg = render_svg(_tiny(terms=False, optional=False, decision=False, store=False, writes=False))
    assert "optional step" not in svg and "check (yes / no)" not in svg and ">commit</text>" not in svg
    assert "WM / LTM" not in svg and ">Terms</text>" not in svg


def test_side_node_level_with_its_parent_gets_a_straight_edge():
    nodes = [dict(id="a", label="A", phase="p"), dict(id="b", label="B", side=True, phase="p"),
             dict(id="z", label="Z", kind="end", phase="p")]
    f = _flow("level", "Level", "s", [dict(id="p", title="P")], nodes, [("a", "b", "out"), ("a", "z"), ("b", "z")])
    boxes, _meta, _w, _h = layout(f)
    assert abs(boxes["b"].cy - boxes["a"].cy) < 1
    svg = render_svg(f)
    a = boxes["a"]
    assert f'd="M{a.right},{a.cy} H{boxes["b"].x - 1}"' in svg


def test_layout_lanes_share_when_they_do_not_overlap():
    nodes = [dict(id=k, label=k.upper(), phase="p") for k in "abcdef"] + [dict(id="z", label="Z", kind="end", phase="p")]
    edges = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "f"), ("f", "z"), ("a", "c"), ("d", "f"),
             ("a", "f")]
    f = _flow("lanes", "Lanes", "s", [dict(id="p", title="P")], nodes, edges)
    _boxes, meta, _w, _h = layout(f)
    assert meta["lanes"][("a", "c")] == meta["lanes"][("d", "f")] == 0
    assert meta["lanes"][("a", "f")] == 1


def test_flow_markdown_lists_stages_steps_and_terms():
    md = flow_markdown(_tiny())
    assert md.startswith("# Tiny\n\nA small flow.")
    assert "- **Input:** in" in md and "## Second" in md
    assert "1. ◆ Is it new?" in md and "1. ▣ Commit" in md and "1. ▶ Start" in md and "1. ■ End" in md
    assert "1. Side step (if it is new; WM)" in md
    assert "1. Main step (per day)" in md
    assert "## Terms" in md and "- **Term:** What it means here." in md
    assert "## Terms" not in flow_markdown(_tiny(terms=False))


def test_wrap():
    assert _wrap("", 100) == [""]
    assert _wrap("one two three four five six", 8 * 13.0 * 0.53 + 0.01) == ["one two", "three", "four", "five six"]
