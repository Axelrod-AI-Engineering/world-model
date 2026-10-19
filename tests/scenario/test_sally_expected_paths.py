"""Sally's theses against what her research expects (data/scenarios/sally_demo/expected_paths.yaml, Oct 17).

Each ready thesis is posed on the loaded world and its transmission path (the canvas's default "relevant" grid) is
read against the spec: every output moves the way the research expects, every channel the research states plainly
(`must`) is drawn with its sign, the expected chains run step by step, and every output is read at the end of the
path (in the output column, or echoed there when the chain carries on past it)."""

from __future__ import annotations

import pytest
import yaml

from axelrod_wm.inference.paths import isolate

SPEC = yaml.safe_load(open("data/scenarios/sally_demo/expected_paths.yaml"))["theses"]
TARGETS = {t["id"]: t["targets"] for t in yaml.safe_load(open("data/scenarios/sally_demo/theses.yaml"))["theses"]}
MOVES = 0.02          # an expected direction must show at least this many sd at the horizon


@pytest.fixture(scope="module")
def posed():
    from axelrod_wm.repo.snapshots import MemoryBackend
    from axelrod_wm.sim.runner import build_runner
    from axelrod_wm.sim.scenario import load_theses, thesis_from_spec

    r = build_runner("sally_demo", interactive=True, storage=MemoryBackend(), record_checklist=False)
    r.load()
    ctl = r.controller
    specs, _ = load_theses(ctl.scenario_dir)
    out = {}
    for tid in SPEC:
        fc = ctl.pose_thesis(thesis_from_spec(specs[tid], ctl.now))
        out[tid] = (fc.paths, isolate(fc.paths, "relevant", TARGETS[tid]))
    return out


def test_the_spec_names_only_what_the_model_has():
    from axelrod_wm.repo.snapshots import MemoryBackend
    from axelrod_wm.sim.runner import build_runner

    r = build_runner("sally_demo", interactive=True, storage=MemoryBackend(), record_checklist=False)
    r.load()
    g = r.controller.engine.wm.graph
    links = {(i.source_id, i.target_id) for i in g.active_interactions()}
    for tid, t in SPEC.items():
        assert set(t["outputs"]) == set(TARGETS[tid]), tid
        for c in t["channels"]:
            assert (c["source"], c["target"]) in links, (tid, c)
        for c in t.get("missing_links") or []:
            assert c["source"] in g.subentities and c["target"] in g.subentities, (tid, c)
        assert all(v in g.subentities for chain in t["chains"] for v in chain), tid


@pytest.mark.parametrize("tid", list(SPEC))
def test_outputs_move_the_way_the_research_expects(posed, tid):
    src, _grid = posed[tid]
    for out, want in SPEC[tid]["outputs"].items():
        if want == "?":
            continue
        v = src["values"].get(out)
        assert v is not None, f"{tid}: {out} is not reached"
        assert (v["effect"] > 0) == (want == "up") and abs(v["effect"]) >= MOVES, (tid, out, want, v["effect"])


@pytest.mark.parametrize("tid", list(SPEC))
def test_every_must_channel_is_drawn_with_its_sign(posed, tid):
    _src, grid = posed[tid]
    edges = {(e["source"], e["target"]): e for e in grid["edges"]}
    for c in SPEC[tid]["channels"]:
        if c["level"] != "must":
            continue
        e = edges.get((c["source"], c["target"]))
        assert e is not None, (tid, c)
        assert (e["effect"] >= 0) == (c["sign"] == "+"), (tid, c, e["effect"])


def test_most_softer_channels_and_chain_steps_are_drawn_too(posed):
    should = steps = drawn_should = drawn_steps = 0
    for tid, (_src, grid) in posed.items():
        edges = {(e["source"], e["target"]) for e in grid["edges"]}
        for c in SPEC[tid]["channels"]:
            if c["level"] == "should":
                should += 1
                drawn_should += (c["source"], c["target"]) in edges
        for chain in SPEC[tid]["chains"]:
            for a, b in zip(chain, chain[1:]):
                steps += 1
                drawn_steps += (a, b) in edges
    assert drawn_should / should >= 0.9 and drawn_steps / steps >= 0.95, (drawn_should, should, drawn_steps, steps)


@pytest.mark.parametrize("tid", list(SPEC))
def test_every_output_is_read_at_the_end_of_the_path(posed, tid):
    src, grid = posed[tid]
    for out in TARGETS[tid]:
        if out not in src["values"]:
            continue                                  # not reached at all: nothing to show
        v = grid["values"].get(out)
        assert v is not None, (tid, out)
        assert v["column"] == "output" or out in grid["echoes"], (tid, out, v["column"])
    assert grid["columns"][-1] == "output"
