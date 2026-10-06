"""Forecast briefs (addition). DECISION: the user asked to see the aftermath of a forecast concretely, as
a mock-up: a one-page reading of a forecast for a person, built only from what the model already holds.

A brief has the bottom line, what moves and when, who is affected, why (the top paths in words), the
news that shaped the forecast and the news since it was made that bears on it (scored by how much each
event touched the forecast's drivers), how the realized values track the forecast's bands so far, what to
watch, and what would change the view. Nothing here computes a model result: it reads the forecast, its
explanation, the proposals and folds of past market events, and the deviation history.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

ROUTINE_PREFIX = "ME-D-"


def _name_fns(graph: Any, ltm: Any):
    def sub(sid: str) -> str:
        s = graph.subentities.get(sid)
        return s.name if s is not None else str(sid).split(".")[-1].replace("_", " ")

    def ent_of(sid: str) -> str:
        s = graph.subentities.get(sid)
        return s.entity_id if s is not None else str(sid).split(".")[0]

    def ent(eid: str) -> str:
        e = graph.entities.get(eid)
        return e.name if e is not None else eid

    def link(iid: str) -> str:
        i = graph.interactions.get(iid)
        return i.label if i is not None and getattr(i, "label", None) else iid

    def pattern(pid: str) -> str:
        p = ltm.object_generalizations.patterns.get(pid)
        return f"{pid} · {p.name}" if p is not None else pid

    return sub, ent_of, ent, link, pattern


def _op_refs(op: Any) -> tuple[set[str], set[str]]:
    """Subentities and interactions an op touches (concrete ends only)."""
    subs: set[str] = set()
    ints: set[str] = set()
    kind = getattr(op, "op", "")
    for end in ("target", "source", "subject"):
        t = getattr(op, end, None)
        if t is not None and getattr(t, "kind", "") == "concrete":
            subs.add(t.subentity_id)
    iid = getattr(op, "interaction_id", None)
    if iid and kind in ("reweight_interaction", "annotate_interaction"):
        ints.add(iid)
    return subs, ints


def _event_footprints(ctl: Any) -> dict[str, dict]:
    """For each non-routine market event: the subentities and interactions its applied ops touched, and
    how far its fold moved each subentity (from the trace, when the tracer still holds it)."""
    out: dict[str, dict] = {}
    for p in ctl.proposals.values():
        me = p.market_event_id
        if not me or me.startswith(ROUTINE_PREFIX) or str(p.status) not in ("approved", "auto_applied", "edited"):
            continue
        fp = out.setdefault(me, {"subs": set(), "ints": set(), "moves": {}})
        for op in p.event.ops:
            s, i = _op_refs(op)
            fp["subs"] |= s
            fp["ints"] |= i
    tracer = ctl.engine.tracer
    for ev in getattr(tracer, "events", []) or []:
        if ev.kind != "fold.posterior" or not ev.scope or ev.scope not in out:
            continue
        sid = ev.payload.get("subentity_id")
        z = ev.payload.get("z")
        if sid and z is not None:
            out[ev.scope]["moves"][sid] = float(z)
            out[ev.scope]["subs"].add(sid)
    return out


def _weights(fc: Any, ex: Any, thesis: Any, graph: Any) -> tuple[dict[str, float], dict[str, float], dict[str, str]]:
    """How much each subentity and link matters to this forecast, and why (for the reasons)."""
    w: dict[str, float] = {}
    iw: dict[str, float] = {}
    why: dict[str, str] = {}

    def put(sid: str, v: float, reason: str) -> None:
        if v > w.get(sid, 0.0):
            w[sid] = v
            why[sid] = reason

    for op in getattr(thesis.event, "ops", []) if thesis is not None else []:
        t = getattr(op, "target", None)
        if t is not None and getattr(t, "kind", "") == "concrete":
            put(t.subentity_id, 1.0, "the shock in this question")
    for p in (ex.top_paths if ex is not None else []):
        put(p.shock_id, 1.0, "the shock in this question")
        for iid in p.interaction_ids:
            iw[iid] = max(iw.get(iid, 0.0), 0.45 + 0.55 * p.share)
            inter = graph.interactions.get(iid)
            if inter is not None:
                for sid in (inter.source_id, inter.target_id):
                    put(sid, 0.25 + 0.6 * p.share, "on a main path of the forecast")
        put(p.target_id, 0.45, "a target of the forecast")
    for sid in fc.targets:
        put(sid, 0.35, "a target of the forecast")
    for n in fc.networks:
        for sid in getattr(n, "subentity_ids", []) or []:
            put(sid, 0.1, "inside a network the forecast ran")
    return w, iw, why


def _score_events(ctl: Any, fc: Any, ex: Any, thesis: Any, graph: Any, sub: Any) -> list[dict]:
    w, iw, why = _weights(fc, ex, thesis, graph)
    effect_at_h = {sid: (v[-1].q50 if v else 0.0) for sid, v in fc.effect_summary.items()}
    effect_at_h.update(fc.movers or {})
    posed = fc.created_at
    rows = []
    for me_id, fp in _event_footprints(ctl).items():
        ev = ctl.market_events.get(me_id)
        if ev is None:
            continue
        parts = []
        score = 0.0
        for sid in fp["subs"]:
            base = w.get(sid, 0.0)
            if base <= 0:
                continue
            z = fp["moves"].get(sid)
            mag = min(1.5, 0.5 + abs(z) / 2) if z is not None else 1.0
            score += base * mag
            parts.append((base * mag, sid, z))
        for iid in fp["ints"]:
            if iid in iw:
                score += iw[iid]
                parts.append((iw[iid], iid, None))
        if score <= 0:
            continue
        parts.sort(key=lambda x: -x[0])
        reasons = []
        stance = 0
        for _v, ref, z in parts[:3]:
            if ref in graph.interactions:
                reasons.append(f"reweighs a link on a main path ({graph.interactions[ref].label})")
                continue
            moved = f" {'▲' if z > 0 else '▼'} {abs(z):.1f} sd" if z is not None and abs(z) >= 0.05 else ""
            reasons.append(f"moved {sub(ref)}{moved}: {why.get(ref, 'part of the forecast')}")
            fx = effect_at_h.get(ref)
            if z is not None and fx is not None and abs(fx) >= 0.02 and abs(z) >= 0.05:
                stance += 1 if (z > 0) == (fx > 0) else -1
        at = getattr(ev, "published_at", None) or getattr(ev, "occurred_at", None)
        rows.append({"id": me_id, "headline": ev.headline, "source": getattr(ev, "source", ""),
                     "channel": str(getattr(ev, "channel", "")), "published_at": at.isoformat() if at else None,
                     "after": bool(at and posed and at > posed), "score": score, "reasons": reasons,
                     "stance": "supports" if stance > 0 else "pushes against" if stance < 0 else "touches"})
    top = max((r["score"] for r in rows), default=0.0) or 1.0
    for r in rows:
        r["relevance"] = round(r.pop("score") / top, 3)
    rows.sort(key=lambda r: (-r["relevance"], r["id"]))
    return [r for r in rows if r["relevance"] >= 0.12]


def _timeline(fc: Any, sub: Any, dates: list[str], groups: list[Any]) -> list[dict]:
    items = []
    series = [(sid, sub(sid), fc.effect_summary.get(sid, [])) for sid in fc.targets]
    series += [(g.id, g.name, g.effect_summary) for g in groups]
    for ref, name, es in series:
        if not es:
            continue
        med = [p.q50 for p in es]
        k_peak = max(range(len(med)), key=lambda k: abs(med[k]))
        peak = med[k_peak]
        if abs(peak) < 0.1:
            continue
        onset = next(k for k, v in enumerate(med) if abs(v) >= 0.5 * abs(peak))
        items.append({"ref": ref, "name": name, "onset": dates[min(onset, len(dates) - 1)],
                      "peak_date": dates[min(k_peak, len(dates) - 1)], "peak": round(peak, 3),
                      "direction": "up" if peak > 0 else "down", "onset_day": onset})
    items.sort(key=lambda x: (x["onset_day"], -abs(x["peak"])))
    return items


def _tracking(ctl: Any, fc: Any, sub: Any) -> list[dict]:
    """How the realized values have tracked the forecast since it was made (standardized units)."""
    dev = ctl.engine.wm.deviations
    start = fc.start_day
    last = ctl.engine.wm.last_processed_day
    if start is None or last is None or last <= start:
        return []
    out = []
    for sid in fc.targets:
        zs = fc.z_summary.get(sid) or []
        k = min(last - start, len(zs) - 1)
        if k < 1:
            continue
        z = dev.z_at(sid, start + k)
        if z is None:
            continue
        band = zs[k]
        where = ("inside the 50% band" if band.q25 <= z <= band.q75 else
                 "inside the 90% band" if band.q05 <= z <= band.q95 else
                 "above the 90% band" if z > band.q95 else "below the 90% band")
        out.append({"id": sid, "name": sub(sid), "days": k, "realized": round(z, 3), "median": round(band.q50, 3),
                    "q05": round(band.q05, 3), "q95": round(band.q95, 3), "where": where})
    return out


def brief_view(ctl: Any, forecast_id: str) -> dict:
    fc = ctl.forecast(forecast_id)
    if fc is None:
        raise KeyError(forecast_id)
    eng = ctl.engine
    g = eng.wm.graph
    sub, ent_of, ent, link, pattern = _name_fns(g, eng.ltm)
    thesis = ctl.theses.get(fc.thesis_id)
    ex = ctl.explanation(fc.explanation_id) if fc.explanation_id else None
    start = fc.created_at
    dates = [(start + timedelta(days=k)).date().isoformat() for k in range(fc.horizon_days + 1)]
    horizon = dates[-1]

    # the bottom line: the largest effects at the horizon, with their 90% ranges
    effects = []
    for sid in fc.targets:
        es = fc.effect_summary.get(sid) or []
        if es:
            last = es[-1]
            effects.append({"id": sid, "name": sub(sid), "entity": ent(ent_of(sid)), "q50": round(last.q50, 3),
                            "q05": round(last.q05, 3), "q95": round(last.q95, 3)})
    effects.sort(key=lambda x: -abs(x["q50"]))
    scen = sorted(fc.scenarios, key=lambda s: -s.weight)
    lead = scen[0] if scen else None
    moved = [e for e in effects if abs(e["q50"]) >= 0.05][:3]
    if moved:
        parts = [f"{e['name']} {'rises' if e['q50'] > 0 else 'falls'} by about {abs(e['q50']):.2f} sd "
                 f"(90%: {e['q05']:+.2f} to {e['q95']:+.2f})" for e in moved]
        bottom = f"By {horizon}, " + "; ".join(parts) + "."
    else:
        bottom = f"By {horizon}, no target moves by more than 0.05 sd: the shock does not reach them through the graph."
    if lead is not None and len(scen) > 1:
        bottom += (f" The leading scenario, {lead.name} ({lead.weight:.0%}), is one of {len(scen)}; "
                   f"the others are {', '.join(f'{s.name} ({s.weight:.0%})' for s in scen[1:])}.")

    groups = list(fc.groups or [])
    affected = [{"id": gr.id, "kind": gr.kind, "name": gr.name, "effect": round(gr.effect_summary[-1].q50, 3) if gr.effect_summary else 0.0,
                 "top": [{"id": sid, "name": sub(sid), "effect": round(v, 3)} for sid, v in gr.top[:3]]} for gr in groups]
    by_entity: dict[str, tuple[str, float]] = {}
    for sid, v in (fc.movers or {}).items():
        e = ent_of(sid)
        if e not in by_entity or abs(v) > abs(by_entity[e][1]):
            by_entity[e] = (sid, v)
    movers = [{"entity": e, "entity_name": ent(e), "id": sid, "name": sub(sid), "effect": round(v, 3)}
              for e, (sid, v) in sorted(by_entity.items(), key=lambda kv: -abs(kv[1][1]))][:8]

    why = []
    for p in (ex.top_paths if ex is not None else [])[:4]:
        steps = [sub(p.shock_id)]
        for iid in p.interaction_ids:
            inter = g.interactions.get(iid)
            steps.append(f"{link(iid)} {sub(inter.target_id) if inter is not None else '?'}")
        why.append({"text": " → ".join(steps), "share": round(p.share, 3), "interaction_ids": list(p.interaction_ids),
                    "shock": p.shock_id, "target": p.target_id})

    # what to watch: the first value each main path moves, in order
    watch = []
    seen = set()
    for p in (ex.top_paths if ex is not None else []):
        if not p.interaction_ids:
            continue
        first = g.interactions.get(p.interaction_ids[0])
        if first is None or first.target_id in seen:
            continue
        seen.add(first.target_id)
        fx = (fc.movers or {}).get(first.target_id)
        if fx is None and first.target_id in fc.effect_summary:
            fx = fc.effect_summary[first.target_id][-1].q50
        watch.append({"id": first.target_id, "name": sub(first.target_id), "entity": ent(ent_of(first.target_id)),
                      "direction": None if fx is None else ("up" if fx > 0 else "down"),
                      "why": f"first in line after {sub(p.shock_id)} on a main path ({link(first.id)})"})
        if len(watch) >= 4:
            break

    # what would change the view: the other scenarios, and open hypotheses on the main paths
    path_ents = {ent_of(s) for p in (ex.top_paths if ex is not None else []) for s in (p.shock_id, p.target_id)}
    for p in (ex.top_paths if ex is not None else []):
        for iid in p.interaction_ids:
            inter = g.interactions.get(iid)
            if inter is not None:
                path_ents |= {ent_of(inter.source_id), ent_of(inter.target_id)}
    hyps = []
    for h in eng.wm.hypotheses.values():
        if str(h.status) != "open" or not set(h.subject_entity_ids) & path_ents:
            continue
        hyps.append({"id": h.id, "statement": h.statement, "probability": round(h.probability, 3),
                     "voi": round(h.current_value(ctl.now), 4)})
    hyps.sort(key=lambda x: -x["voi"])
    change = [{"kind": "scenario", "text": f"If {s.name} is right instead ({s.weight:.0%} now)", "weight": round(s.weight, 3)}
              for s in scen[1:3]]
    change += [{"kind": "hypothesis", "text": h["statement"], "probability": h["probability"], "voi": h["voi"], "id": h["id"]}
               for h in hyps[:3]]

    events = _score_events(ctl, fc, ex, thesis, g, sub)
    caveats = list(ex.assumptions) if ex is not None else []
    caveats.append(f"Computed at state version v{fc.based_on_version} from {len(fc.scenarios)} scenario(s); "
                   f"{len(fc.networks)} network(s) were run.")
    caveats.append("All news and data in this demo are synthetic; real company names make the graph concrete, not "
                   "claims about those companies.")
    return {
        "forecast_id": fc.id, "thesis_id": fc.thesis_id, "question": fc.question or (thesis.question if thesis else ""),
        "posed_at": start.isoformat(), "horizon": horizon, "horizon_days": fc.horizon_days, "version": fc.based_on_version,
        "bottom_line": bottom, "effects": effects[:6],
        "scenarios": [{"name": s.name, "weight": round(s.weight, 3)} for s in scen],
        "timeline": _timeline(fc, sub, dates, groups)[:8],
        "affected": affected, "movers": movers, "why": why,
        "shaped_by": [e for e in events if not e["after"]][:5],
        "since": [e for e in events if e["after"]][:5],
        "tracking": _tracking(ctl, fc, sub),
        "watch": watch, "change": change, "caveats": caveats,
        "explanation": ex.text if ex is not None else "",
    }
