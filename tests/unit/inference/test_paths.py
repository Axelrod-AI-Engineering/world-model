"""The transmission grid's ways of isolating what matters (inference/paths.py)."""
import numpy as np
import pytest

from axelrod_wm.inference.paths import METHODS, default_outputs, effect_series, isolate


def _v(order, peak, path=(), shock="oil.price"):
    days = [0, 10, 20]
    return {"order": order, "peak": peak, "peak_day": 10, "effect": peak, "arrives_day": 5 * order, "shock_id": shock,
            "path": list(path), "days": days, "q10": [0, peak * 0.5, peak * 0.5], "q50": [0, peak, peak],
            "q90": [0, peak * 1.5, peak * 1.5]}


def _e(s, t, eff, key=None, exists=0.9):
    return {"key": key or f"{s}>{t}", "source": s, "target": t, "effect": eff, "exists": exists,
            "sig": exists * abs(eff), "delay_days": 5}


@pytest.fixture
def src():
    # oil -> fuel -> margin -> shares; oil -> demand -> shares (a second route); oil -> rates (a weak side branch)
    values = {
        "oil.price": _v(0, 1.0),
        "delta.fuel": _v(1, 0.8, ["oil.price>delta.fuel"]),
        "air.demand": _v(1, -0.3, ["oil.price>air.demand"]),
        "fed.rate": _v(1, 0.06, ["oil.price>fed.rate"]),
        "delta.margin": _v(2, -0.5, ["oil.price>delta.fuel", "delta.fuel>delta.margin"]),
        "delta.shares": _v(3, -0.4, ["oil.price>delta.fuel", "delta.fuel>delta.margin", "delta.margin>delta.shares"]),
    }
    edges = [_e("oil.price", "delta.fuel", 0.8), _e("oil.price", "air.demand", -0.3), _e("oil.price", "fed.rate", 0.06),
             _e("delta.fuel", "delta.margin", -0.6), _e("delta.margin", "delta.shares", 0.7),
             _e("air.demand", "delta.shares", 0.5)]
    return {"horizon": 20, "values": values, "edges": edges}


def test_effect_series_is_quantiles_on_spaced_days():
    paths = np.tile(np.arange(31, dtype=float), (100, 1)) + np.linspace(-1, 1, 100)[:, None]
    s = effect_series(paths, 30, points=4)
    assert s["days"] == [0, 10, 20, 30]
    assert s["q50"] == pytest.approx([0, 10, 20, 30], abs=0.02)
    assert all(lo < mid < hi for lo, mid, hi in zip(s["q10"], s["q50"], s["q90"]))


def test_default_outputs_are_the_ends_of_chains(src):
    assert default_outputs(src) == ["delta.shares", "fed.rate"]


@pytest.mark.parametrize("method", sorted(METHODS))
def test_every_method_keeps_the_grid_joined(src, method):
    g = isolate(src, method, outputs=["delta.shares"])
    cols = {sid: v["column"] for sid, v in g["values"].items()}
    assert cols["oil.price"] == "input" and cols["delta.shares"] == "output"
    # every shown value other than an input has an edge into it, and every edge joins shown values
    targets = {e["target"] for e in g["edges"]}
    assert all(sid in targets for sid, c in cols.items() if c != "input")
    assert all(e["source"] in cols and e["target"] in cols for e in g["edges"])


def test_outputs_method_drops_what_does_not_lead_to_an_output(src):
    g = isolate(src, "outputs", outputs=["delta.shares"])
    assert "fed.rate" not in g["values"]                     # a side branch that reaches no output
    assert {("air.demand", "delta.shares"), ("delta.margin", "delta.shares")} <= {(e["source"], e["target"]) for e in g["edges"]}


def test_strongest_places_values_by_their_position_on_the_path(src):
    g = isolate(src, "strongest", outputs=["delta.shares"])
    assert g["values"]["delta.fuel"]["column"] == "1"
    assert g["values"]["delta.margin"]["column"] == "2"
    # the weak two-hop route through demand carries enough gain to show
    assert "air.demand" in g["values"]


def test_largest_caps_each_column(src):
    g = isolate(src, "largest", outputs=["delta.shares"], per_column=1)
    first = [sid for sid, v in g["values"].items() if v["column"] == "1"]
    assert first == ["delta.fuel"]
    assert g["hidden"] >= 1


def test_unknown_method_is_an_error(src):
    with pytest.raises(ValueError):
        isolate(src, "nope")


def test_relevant_is_the_default_and_discounts_far_orders(src):
    g = isolate(src)
    assert g["method"] == "relevant"
    # the weak first-order side branch (0.06) is not relevant; the strong third-order effect still is
    assert "fed.rate" not in g["values"]
    assert g["values"]["delta.shares"]["column"] == "output"
    assert g["columns"][0] == "input" and g["columns"][-1] == "output"


def test_orders_beyond_the_third_get_their_own_columns(src):
    src["values"]["delta.bonds"] = {**src["values"]["delta.shares"], "order": 4, "peak": 0.9,
                                    "path": src["values"]["delta.shares"]["path"] + ["delta.shares>delta.bonds"]}
    src["edges"].append({"key": "delta.shares>delta.bonds", "source": "delta.shares", "target": "delta.bonds",
                         "effect": 0.9, "exists": 0.9, "sig": 0.81, "delay_days": 5})
    g = isolate(src, "relevant")
    # strong enough at the fourth order to count, it is an output, and the third order keeps its own column
    assert "delta.bonds" in g["outputs"]
    assert g["values"]["delta.shares"]["column"] == "3"
    g2 = isolate(src, "orders", outputs=["delta.bonds"])
    assert "3" in g2["columns"]


@pytest.mark.parametrize("method", ["orders", "largest"])
def test_an_output_the_chain_carries_past_stays_at_its_order(src, method):
    # asking about the margin, while the shares (shown by these methods) depend on it: no edge may run back from the
    # output column, so the margin stays in its order's column and is still listed as an output
    g = isolate(src, method, outputs=["delta.margin"])
    cols = {sid: v["column"] for sid, v in g["values"].items()}
    assert cols["delta.margin"] == "2" and "delta.margin" in g["outputs"]
    assert not any(cols[e["source"]] == "output" for e in g["edges"])
    assert all(c in g["columns"] for c in cols.values())


def test_relevant_fills_in_values_between_and_after_with_their_links():
    # Oct 17 ("transmission paths need more subentities and relationships between subentities"): a weak second route
    # into a kept value (d) and where a kept chain carries on (e) are shown, with the interactions among them; a weak
    # direct side effect of the shock (f) still is not
    values = {
        "in.x": _v(0, 1.0, shock="in.x"),
        "a.x": _v(1, 0.9, ["in>a"], shock="in.x"),
        "b.x": _v(2, 0.5, ["in>a", "a>b"], shock="in.x"),
        "c.x": _v(3, 0.8, ["in>a", "a>b", "b>c"], shock="in.x"),
        "d.x": _v(2, 0.15, ["in>a", "a>d"], shock="in.x"),
        "e.x": _v(4, 0.1, ["in>a", "a>b", "b>c", "c>e"], shock="in.x"),
        "f.x": _v(1, 0.05, ["in>f"], shock="in.x"),
    }
    edges = [_e("in.x", "a.x", 0.9, "in>a"), _e("a.x", "b.x", 0.6, "a>b"), _e("b.x", "c.x", 0.9, "b>c"),
             _e("a.x", "d.x", 0.2, "a>d"), _e("d.x", "c.x", 0.9, "d>c"), _e("c.x", "e.x", 0.3, "c>e"),
             _e("in.x", "f.x", 0.05, "in>f")]
    g = isolate({"horizon": 20, "values": values, "edges": edges}, "relevant")
    assert {"d.x", "e.x"} <= set(g["values"]) and "f.x" not in g["values"]
    pairs = {(e["source"], e["target"]) for e in g["edges"]}
    assert {("a.x", "d.x"), ("d.x", "c.x"), ("c.x", "e.x")} <= pairs
    assert g["values"]["d.x"]["column"] == "2"
    # still joined: every shown value but the input has an interaction into it
    assert all(sid in {t for _, t in pairs} for sid, v in g["values"].items() if v["column"] != "input")


def test_relevant_caps_what_it_fills_in():
    from axelrod_wm.inference.paths import RELEVANT_MAX

    # one strong value, and a long tail behind it that would all be filled in without the cap
    values = {"in.x": _v(0, 1.0, shock="in.x"), "a.x": _v(1, 0.9, ["in>a"], shock="in.x")}
    edges = [_e("in.x", "a.x", 0.9, "in>a")]
    for k in range(60):
        values[f"t{k}.x"] = _v(2, 0.1, ["in>a", f"a>t{k}"], shock="in.x")
        edges.append(_e("a.x", f"t{k}.x", 0.3, f"a>t{k}"))
    g = isolate({"horizon": 20, "values": values, "edges": edges}, "relevant")
    assert len(g["values"]) == RELEVANT_MAX


# -- Oct 17: outputs sit on the end -------------------------------------------------------------------------------------
def _chain():
    # in -> a -> b; a also feeds c; asked: a (which the chain carries past), b, and the input itself
    values = {"in.x": _v(0, 1.0, shock="in.x"), "a.x": _v(1, 0.9, ["in>a"], shock="in.x"),
              "b.x": _v(2, 0.7, ["in>a", "a>b"], shock="in.x"), "c.x": _v(2, 0.6, ["in>a", "a>c"], shock="in.x")}
    edges = [_e("in.x", "a.x", 0.9, "in>a"), _e("a.x", "b.x", 0.8, "a>b"), _e("a.x", "c.x", 0.7, "a>c")]
    return {"horizon": 20, "values": values, "edges": edges}


def test_every_asked_output_is_read_at_the_end_echoed_when_the_chain_carries_on():
    g = isolate(_chain(), "relevant", outputs=["a.x", "b.x", "in.x"])
    cols = {sid: v["column"] for sid, v in g["values"].items()}
    assert cols["a.x"] == "1" and cols["b.x"] == "output" and cols["in.x"] == "input"
    assert g["outputs"] == ["a.x", "b.x", "in.x"] and g["echoes"] == ["a.x", "in.x"]
    assert g["columns"] == ["input", "1", "2", "output"]


def test_an_echo_alone_still_opens_the_output_column():
    g = isolate(_chain(), "relevant", outputs=["a.x"])
    assert g["echoes"] == ["a.x"] and g["columns"][-1] == "output"
    assert all(v["column"] != "output" for v in g["values"].values())


def test_interactions_within_one_order_are_drawn_once():
    # carry and the currency are both first-order under a hike, and carry drives the currency: drawn, but never both ways
    values = {"in.x": _v(0, 1.0, shock="in.x"), "carry.x": _v(1, -0.8, ["in>carry"], shock="in.x"),
              "fx.x": _v(1, -0.6, ["in>fx"], shock="in.x")}
    edges = [_e("in.x", "carry.x", -0.8, "in>carry"), _e("in.x", "fx.x", -0.3, "in>fx"),
             _e("carry.x", "fx.x", 0.5, "carry>fx"), _e("fx.x", "carry.x", 0.5, "fx>carry"),
             _e("fx.x", "fx.x", 0.5, "fx>fx")]
    g = isolate({"horizon": 20, "values": values, "edges": edges}, "relevant", outputs=["fx.x", "carry.x"])
    pairs = {(e["source"], e["target"]) for e in g["edges"]}
    assert ("carry.x", "fx.x") in pairs and ("fx.x", "carry.x") not in pairs and ("fx.x", "fx.x") not in pairs


def test_a_path_step_that_is_not_shown_is_not_drawn():
    src = _chain()
    src["values"]["b.x"]["path"] = ["gone", "in>a", "a>b"]          # an interaction no longer in the source
    g = isolate(src, "relevant", outputs=["b.x"])
    assert ("in.x", "a.x") in {(e["source"], e["target"]) for e in g["edges"]}


def test_an_output_no_route_reaches_is_left_off_the_strongest_paths():
    src = _chain()
    src["values"]["z.x"] = _v(1, 0.5, ["in>z"], shock="in.x")      # reached, but by no edge in the source
    g = isolate(src, "strongest", outputs=["z.x", "b.x"])
    assert "z.x" not in g["values"] and g["values"]["b.x"]["column"] == "output"


def test_strongest_skips_a_negligible_route_and_stops_at_its_hop_limit():
    from axelrod_wm.inference.paths import _simple_paths

    adj = {"a": [_e("a", "b", 1.0), _e("a", "c", 1.0)], "b": [_e("b", "a", 1.0), _e("b", "d", 1.0)],
           "c": [_e("c", "d", 1.0)]}
    assert [[e["target"] for e in p] for p in _simple_paths("a", "d", adj, 2)] == [["b", "d"], ["c", "d"]]
    assert _simple_paths("a", "d", adj, 1) == []                    # two hops needed, one allowed
    many = {"s": [_e("s", f"m{k}", 1.0) for k in range(300)], **{f"m{k}": [_e(f"m{k}", "t", 1.0)] for k in range(300)}}
    assert len(_simple_paths("s", "t", many, 3)) == 201                # it stops looking past 200
    values = {"in.x": _v(0, 1.0, shock="in.x"), "big.x": _v(1, 0.9, ["in>big"], shock="in.x"),
              "tiny.x": _v(1, 0.001, ["in>tiny"], shock="in.x"), "out.x": _v(2, 0.9, ["in>big", "big>out"], shock="in.x")}
    edges = [_e("in.x", "big.x", 0.9, "in>big"), _e("big.x", "out.x", 0.9, "big>out"),
             _e("in.x", "tiny.x", 0.001, "in>tiny"), _e("tiny.x", "out.x", 0.001, "tiny>out")]
    g = isolate({"horizon": 20, "values": values, "edges": edges}, "strongest", outputs=["out.x"])
    assert "big.x" in g["values"] and "tiny.x" not in g["values"]


def test_an_empty_effect_series():
    assert effect_series(np.zeros((0, 0)), 10) == {"days": [], "q10": [], "q50": [], "q90": []}


def test_the_source_keeps_asked_values_and_the_strongest_of_twin_channels():
    from types import SimpleNamespace as NS

    from axelrod_wm.inference.paths import source_of
    from axelrod_wm.model.distributions import Gaussian

    def entry(sid, material, via=()):
        return NS(subentity_id=sid, material=material, order=1, shock_id="in.x", arrives_day=3,
                  path=[NS(interaction_id=f"{v}>", target_id=v) for v in via])

    def chan(key, s, t, eff, forced=True):
        kern = NS(means=lambda: (3.0, 10.0, None))
        return NS(forced=forced, source_id=s, target_id=t, channel_key=key, existence=NS(mean=lambda: 1.0),
                  dynamics=NS(effect=Gaussian(mu=eff, sigma=0.1), kernel=kern))

    effect = lambda sid: np.full((4, 11), 0.5)                       # noqa: E731
    entries = [entry("a.x", True), entry("small.x", False), entry("mid.x", False),
               entry("asked.x", False, via=("mid.x", "asked.x"))]
    chans = [chan("k1", "in.x", "a.x", 0.2), chan("k2", "in.x", "a.x", 0.6), chan("k3", "in.x", "a.x", 0.1),
             chan("k4", "a.x", "asked.x", 0.3, forced=False)]
    src = source_of(["in.x"], chans, effect, 10, entries, asked={"asked.x"})
    assert set(src["values"]) == {"in.x", "a.x", "mid.x", "asked.x"}  # immaterial values stay out unless asked or on its path
    assert [e["key"] for e in src["edges"]] == ["k2"]               # the strongest of three; an unforced one is not drawn
