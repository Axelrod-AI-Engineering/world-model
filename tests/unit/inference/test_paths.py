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
