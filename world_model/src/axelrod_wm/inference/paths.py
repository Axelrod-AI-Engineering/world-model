"""Transmission paths, isolated (Oct 11): what of a shock's ripple is relevant, laid out as a grid.

The grid's columns are the input (the shocked values), the first, second, and third (or later) order, and the output
(the values the question or the review is about). Its rows are entities, so one entity's values sit in one row, each in
the column of its order. Every value carries its median effect by day, with a 10–90% band, so the grid can animate the
shock arriving.

Which values are relevant is a choice, and there are five ways to make it (`METHODS`):

- `relevant` (the default): what carries the most effect, with each further order discounted by `ORDER_BIAS`, so a
  distant effect shows only if it is strong enough to matter, and (Oct 17) the values that lie between those, up to
  `RELEVANT_MAX`, with the interactions among them. Orders go as deep as the effects do (up to six), and the outputs
  are where the kept chains end.

- `orders`: every material value, at its breadth-first order, joined by its one most significant shortest path. This is
  what the review and the forecast list today.
- `largest`: the largest effects in each column (at most `per_column`), plus whatever their paths pass through, so
  every chain stays connected.
- `outputs`: only what lies on some path from an input to an output, with every interaction among those values. Several
  routes to the same value show at once.
- `strongest`: the strongest simple paths from the inputs to each output, by path gain (the product of each
  interaction's belief that it exists and its mean effect), keeping the paths that carry at least `min_share` of an
  output's total gain. A value's column is its position on its strongest path, so a large second-hand effect is not
  hidden behind a weak direct one.

DECISION: all four read the same simulated effects (common random numbers), so they differ only in what they show,
never in the numbers. `strongest` uses analytic path gains to choose paths, as `shared/explain.top_paths` does; it is
the cheap first step of the roadmap's path-specific effects (world_model/docs/ml/roadmap.md, R12)."""
from __future__ import annotations

from typing import Any

import numpy as np

ORDER_BIAS = 0.6        # each order further from the input counts this much less when choosing what is relevant
RELEVANT_SHARE = 0.12   # a value is relevant if its discounted effect is at least this share of the largest one
RELEVANT_MAX = 28       # values shown in all, inputs included, once the values between and after relevant ones are in
FILL_FLOOR = 0.02       # a value filled in after the relevant ones moves at least this share of the largest move
LINK_SHARE = 0.1        # an interaction among shown values is drawn if it carries this share of its target's effect
METHODS = {
    "relevant": "What carries the most effect; each further order counts 40% less, so a distant effect shows only if it is strong",
    "orders": "Every material value at its order, along its most significant shortest path",
    "largest": "The largest effects in each column, and what their paths pass through",
    "outputs": "Only what lies between the inputs and the outputs, by every route",
    "strongest": "The strongest paths to each output, by path gain",
}
SERIES_POINTS = 46          # days sampled for animation, evenly over the horizon
MAX_VALUES = 80


def effect_series(paths: np.ndarray, horizon: int, points: int = SERIES_POINTS) -> dict:
    """Median and 10–90% band of one value's effect paths [samples, horizon + 1], at evenly spaced days."""
    if paths.size == 0:
        return {"days": [], "q10": [], "q50": [], "q90": []}
    n = paths.shape[1]
    days = sorted({int(round(x)) for x in np.linspace(0, n - 1, min(points, n))})
    q = np.quantile(paths[:, days], [0.1, 0.5, 0.9], axis=0)
    return {"days": days, "q10": [round(float(x), 4) for x in q[0]], "q50": [round(float(x), 4) for x in q[1]],
            "q90": [round(float(x), 4) for x in q[2]]}


def source_of(shocked: list[str], channels: list[Any], effect_of: Any, horizon: int, entries: list[Any],
              min_delay: int = 1, asked: set[str] | frozenset[str] = frozenset()) -> dict:
    """What the grid is built from: the inputs and the reached values with their series, and the interactions among
    them. Kept small (material values only, at most MAX_VALUES), except that a value the question asks about is kept
    whenever the shock reaches it: "barely moves" is an answer, and an output that vanishes from the path is not."""
    from axelrod_wm.dynamics.kernels import mean_kernel_days
    from axelrod_wm.model.interaction import abs_mean

    values: dict[str, dict] = {}
    for sid in shocked:
        values[sid] = {"order": 0, "shock_id": sid, "path": [], "arrives_day": 0,
                       **_summary(effect_of(sid), horizon)}
    # an asked value brings the values on its path, so it stays joined to the shock however small the steps are
    on_asked = {h.target_id for e in entries if e.subentity_id in asked for h in e.path}
    for e in entries:
        wanted = e.subentity_id in asked or e.subentity_id in on_asked
        if e.subentity_id in values or not (wanted or (e.material and len(values) < MAX_VALUES)):
            continue
        values[e.subentity_id] = {"order": int(e.order), "shock_id": e.shock_id, "arrives_day": int(e.arrives_day),
                                  "path": [h.interaction_id for h in e.path],
                                  **_summary(effect_of(e.subentity_id), horizon)}
    edges = {}
    for ch in channels:
        if ch.forced is False or ch.source_id not in values or ch.target_id not in values:
            continue
        sig = float(ch.existence.mean()) * float(abs_mean(ch.dynamics.effect))
        key = (ch.source_id, ch.target_id)
        if key in edges and edges[key]["sig"] >= sig:
            continue
        d, _l, _lam = mean_kernel_days(ch.dynamics.kernel, min_delay)
        edges[key] = {"key": ch.channel_key, "source": ch.source_id, "target": ch.target_id,
                      "effect": round(float(ch.dynamics.effect.mean()), 4), "exists": round(float(ch.existence.mean()), 4),
                      "sig": round(sig, 5), "delay_days": int(d)}
    return {"horizon": int(horizon), "values": values, "edges": sorted(edges.values(), key=lambda x: (x["source"], x["target"]))}


def _summary(paths: np.ndarray, horizon: int) -> dict:
    s = effect_series(paths, horizon)
    med = np.median(paths, axis=0) if paths.size else np.zeros(horizon + 1)
    k = int(np.argmax(np.abs(med))) if med.size else 0
    return {"peak": round(float(med[k]), 4) if med.size else 0.0, "peak_day": k,
            "effect": round(float(med[min(horizon, med.size - 1)]), 4) if med.size else 0.0, **s}


def default_outputs(src: dict, n: int = 4) -> list[str]:
    """For a review, which has no question: the material values nothing else in the ripple depends on (the ends of the
    chains), largest first."""
    vals = src["values"]
    has_out = {e["source"] for e in src["edges"] if e["target"] in vals and vals[e["target"]]["order"] > 0}
    ends = [sid for sid, v in vals.items() if v["order"] > 0 and sid not in has_out]
    pool = ends or [sid for sid, v in vals.items() if v["order"] > 0]
    return sorted(pool, key=lambda s: -abs(vals[s]["peak"]))[:n]


def isolate(src: dict, method: str = "relevant", outputs: list[str] | None = None, per_column: int = 4,
            min_share: float = 0.1, max_hops: int = 4) -> dict:
    """The grid for one way of isolating what matters. `src` comes from `source_of`."""
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; one of {sorted(METHODS)}")
    vals = src["values"]
    inputs = [sid for sid, v in vals.items() if v["order"] == 0]
    if method == "relevant":
        return _relevant(src, inputs, outputs)
    outs = [o for o in (outputs or default_outputs(src)) if o in vals and vals[o]["order"] > 0]
    edge_by_key = {e["key"]: e for e in src["edges"]}
    by_pair = {(e["source"], e["target"]): e for e in src["edges"]}

    def path_edges(sid: str) -> list[dict]:
        return [edge_by_key[k] for k in vals[sid]["path"] if k in edge_by_key]

    col: dict[str, int] = {}
    keep_edges: dict[tuple[str, str], dict] = {}
    if method in ("orders", "largest"):
        reached = [sid for sid, v in vals.items() if v["order"] > 0]
        if method == "largest":
            chosen: set[str] = set(outs)
            for o in sorted({vals[s]["order"] for s in reached}):
                inc = [s for s in reached if vals[s]["order"] == o]
                chosen |= set(sorted(inc, key=lambda s: -abs(vals[s]["peak"]))[:per_column])
            # what their paths pass through, so every chain stays joined to an input
            for sid in list(chosen):
                for e in path_edges(sid):
                    chosen.add(e["source"])
            reached = [s for s in reached if s in chosen]
        for sid in reached:
            col[sid] = vals[sid]["order"]
            for e in path_edges(sid):
                keep_edges[(e["source"], e["target"])] = e
    elif method == "outputs":
        fwd = _reach(inputs, src["edges"], forward=True)
        bwd = _reach(outs, src["edges"], forward=False)
        on = (fwd & bwd) | set(outs)
        for sid in sorted(on):
            if vals[sid]["order"] > 0:
                col[sid] = vals[sid]["order"]
        for (s, t), e in by_pair.items():
            if s in on and t in on and (vals[t]["order"] > vals[s]["order"] or t in outs):
                keep_edges[(s, t)] = e
    else:   # strongest
        adj: dict[str, list[dict]] = {}
        for e in src["edges"]:
            adj.setdefault(e["source"], []).append(e)
        for o in outs:
            paths = []
            for i in inputs:
                for p in _simple_paths(i, o, adj, max_hops):
                    gain = float(np.prod([e["exists"] * e["effect"] for e in p]))
                    paths.append((abs(gain), p))
            total = sum(g for g, _ in paths) or 1.0
            for g, p in sorted(paths, key=lambda x: -x[0])[:3]:
                if g / total < min_share:
                    continue
                for pos, e in enumerate(p, start=1):
                    t = e["target"]
                    col[t] = min(col.get(t, 99), pos)
                    keep_edges[(e["source"], t)] = e
    # the outputs sit in their own column at the end
    for o in outs:
        if o in col or method in ("orders", "largest"):
            col[o] = 99
    shown = set(col) | set(inputs)
    edges = [e for (s, t), e in keep_edges.items() if s in shown and t in shown]
    return _grid(src, method, inputs, outs, col, edges)


def _relevant(src: dict, inputs: list[str], outputs: list[str] | None) -> dict:
    """Keep what carries the most effect, discounting each order by ORDER_BIAS; join every kept value to an input by its
    path; then fill in the values that lie between kept ones (Oct 17: "transmission paths need more subentities and
    relationships between subentities"), up to RELEVANT_MAX, and show the interactions among everything shown that run
    forward in order and carry a real share of their target's effect."""
    vals = src["values"]
    edge_by_key = {e["key"]: e for e in src["edges"]}
    reached = [sid for sid, v in vals.items() if v["order"] > 0]
    score = {sid: abs(vals[sid]["peak"]) * ORDER_BIAS ** (vals[sid]["order"] - 1) for sid in reached}
    top = max(score.values(), default=0.0)
    keep = {sid for sid in reached if top and score[sid] >= RELEVANT_SHARE * top}
    asked = [o for o in (outputs or []) if o in vals and vals[o]["order"] > 0]
    keep |= set(asked)
    for sid in list(keep):                       # every chain stays joined to an input
        for k in vals[sid]["path"]:
            e = edge_by_key.get(k)
            if e is not None and vals.get(e["source"], {}).get("order", 0) > 0:
                keep.add(e["source"])
    # the values in between (Oct 17): on some forward route from what is shown to a kept value, so a chain shows its
    # intermediate steps and a second route shows beside the first. A side branch that leads to nothing kept stays out.
    # The most relevant come first, up to RELEVANT_MAX values in all.
    onward = [e for e in src["edges"] if e["source"] in vals and e["target"] in vals
              and vals[e["target"]]["order"] > vals[e["source"]]["order"]]
    after = _reach(sorted(keep | set(inputs)), onward, forward=True)
    before = _reach(sorted(keep), onward, forward=False)
    between = sorted((sid for sid in reached if sid not in keep and sid in after and sid in before),
                     key=lambda sid: (-score[sid], sid))
    room = max(0, RELEVANT_MAX - len(keep) - len(inputs))
    keep |= set(between[:room])
    # then where the kept chains carry on: a value one interaction on from a kept value (never from an input alone, so a
    # weak direct side effect of the shock stays out), the most relevant first, until RELEVANT_MAX. An asked output the
    # chain carries on past stays at its order's column, and is echoed in the output column (_grid)
    peak_max = max((abs(vals[s]["peak"]) for s in reached), default=0.0)
    while len(keep) + len(inputs) < RELEVANT_MAX:
        nxt = sorted({e["target"] for e in onward if e["source"] in keep
                      and e["target"] not in keep and e["target"] not in inputs
                      and abs(vals[e["target"]]["peak"]) >= FILL_FLOOR * peak_max}, key=lambda s: (-score[s], s))
        if not nxt:
            break
        keep.add(nxt[0])
    shown = keep | set(inputs)
    edges = {}
    for sid in sorted(keep):
        for k in vals[sid]["path"]:
            e = edge_by_key.get(k)
            if e is not None and e["source"] in shown:
                edges[(e["source"], e["target"])] = e
    # and the interactions among what is shown that carry a real share of their target's effect: forward in order, or
    # within one order (Oct 17: carry -> USD/JPY, both first-order under a BoJ hike), unless the reverse is drawn
    for e in src["edges"]:
        s, t = e["source"], e["target"]
        if s in shown and t in keep and s != t and vals[t]["order"] >= vals[s]["order"] and (t, s) not in edges \
                and abs(e["exists"] * e["effect"] * vals[s]["peak"]) >= LINK_SHARE * abs(vals[t]["peak"]):
            edges[(s, t)] = e
    # the outputs: those asked for, else where the kept chains end, strongest first
    if asked:
        # a shocked value the question also asks about (USD/JPY in a carry unwind) is an output as well, echoed at the end
        outs = [o for o in outputs if o in asked or o in inputs]
    else:
        feeds = {s for (s, t) in edges if t in keep}
        ends = [sid for sid in keep if sid not in feeds]
        outs = sorted(ends, key=lambda x: (-score[x], x))[:10]
    col = {sid: (99 if sid in outs else vals[sid]["order"]) for sid in sorted(keep)}
    return _grid(src, "relevant", inputs, outs, col, list(edges.values()))


def _reach(seeds: list[str], edges: list[dict], forward: bool) -> set[str]:
    nxt: dict[str, list[str]] = {}
    for e in edges:
        a, b = (e["source"], e["target"]) if forward else (e["target"], e["source"])
        nxt.setdefault(a, []).append(b)
    seen = set(seeds)
    stack = list(seeds)
    while stack:
        u = stack.pop()
        for v in nxt.get(u, []):
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def _simple_paths(a: str, b: str, adj: dict[str, list[dict]], max_hops: int) -> list[list[dict]]:
    out: list[list[dict]] = []

    def walk(u: str, path: list[dict], seen: set[str]) -> None:
        if len(out) > 200:
            return
        for e in adj.get(u, []):
            v = e["target"]
            if v in seen:
                continue
            if v == b:
                out.append(path + [e])
            elif len(path) + 1 < max_hops:
                walk(v, path + [e], seen | {v})

    walk(a, [], {a})
    return out


def _grid(src: dict, method: str, inputs: list[str], outs: list[str], col: dict[str, int], edges: list[dict]) -> dict:
    vals = src["values"]
    column_of = {sid: "input" for sid in inputs}
    for sid, c in col.items():
        column_of[sid] = "output" if c == 99 else str(c)
    # an output the shown chain carries on past stays at its order, so no interaction runs back from the last column;
    # it is echoed in the output column as well (Oct 17: "outputs can sit on the end"), so every output is read there
    echoes = set()
    for e in edges:
        s, t = e["source"], e["target"]
        if column_of.get(s) == "output" and column_of.get(t) not in (None, "output", "input"):
            column_of[s] = str(vals[s]["order"])
            echoes.add(s)
    echoes |= {o for o in outs if column_of.get(o) == "input"}
    shown = list(column_of)
    inner = sorted({int(c) for c in column_of.values() if c not in ("input", "output")})
    has_out = echoes or "output" in column_of.values()
    return {
        "method": method,
        "methods": [{"id": k, "label": v} for k, v in METHODS.items()],
        "horizon": src["horizon"],
        "columns": ["input", *[str(c) for c in inner], *(["output"] if has_out else [])],
        "inputs": inputs, "outputs": outs, "echoes": [o for o in outs if o in echoes],
        "values": {sid: {**{k: vals[sid][k] for k in ("order", "peak", "peak_day", "effect", "arrives_day", "shock_id",
                                                      "days", "q10", "q50", "q90")},
                         "column": column_of[sid]} for sid in shown},
        "edges": [{k: e[k] for k in ("key", "source", "target", "effect", "exists", "delay_days")} for e in edges],
        "hidden": sum(1 for sid, v in vals.items() if v["order"] > 0 and sid not in column_of),
    }
