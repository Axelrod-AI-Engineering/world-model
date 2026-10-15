"""The scenario table (Oct 15): a forecast read the way a PM's decision engine reads scenarios.

A forecast is a set of joint draws: in each draw every value moves together, through the interactions. The table
sorts the draws by how the book moves, the average effect on the book's names (their share prices, or their main
earnings line), and reads three bands of them:

  Bear  the worst quarter of the draws for the book,
  Base  the middle half,
  Bull  the best quarter.

A band's probability is its share of the draws (25%, 50%, 25%); the chances that the book ends up or down at all are
given beside them, and those are the model's own. For each band: the names it favors and hurts (median move of each
name inside the band), the drivers that differ most between the bear and bull bands (the mechanism), and what would
change the read: the open hypothesis on the book with the most informational value, or else the driver that splits
the bands most. When long-term memory holds rival scenarios, their
weights are listed as well.

Everything here is computed from the forecast's draws; nothing is learned and no language model is involved.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

TAIL = 0.25              # the share of draws in each of the bull and bear bands
FLAT = 0.02              # a book move smaller than this (standard units) counts as flat
TOP_NAMES = 3
TOP_DRIVERS = 3
SMALL = 0.01             # a name moving less than this (sd) in a band is neither favored nor hurt
EARNINGS_SLOTS = ("operating_profit", "net_interest_income", "trading_revenue")


def _book_value(eid: str, graph: Any) -> str | None:
    """The value that stands for a name in the book: its share price, else its main earnings line."""
    for slot in ("share_price", *EARNINGS_SLOTS):
        sid = f"{eid}.{slot}"
        if sid in graph.subentities:
            return sid
    ent = graph.entities.get(eid)
    return ent.subentity_ids[0] if ent and ent.subentity_ids else None


def native(sid: str, z: float, graph: Any) -> dict:
    """A move in standard units, also in the value's own units: percent for a log-scaled value (prices, profits),
    a change in its unit for the rest (rates in percentage points)."""
    s = graph.subentities.get(sid)
    if s is None:
        return {"sd": round(z, 3)}
    family = getattr(s.posterior, "family", "gaussian")
    if family in ("lognormal", "gamma"):
        return {"sd": round(z, 3), "pct": round((math.exp(z * s.scale) - 1.0) * 100.0, 2)}
    return {"sd": round(z, 3), "change": round(z * s.scale, 4), "unit": s.unit}


def build_scenario_table(mix: Any, scenarios: list[Any], book: list[str], graph: Any, hypotheses: dict,
                         horizon: int) -> dict:
    """The bull, base, and bear bands of a forecast's draws, read for the book (entity ids)."""
    names = [(eid, _book_value(eid, graph)) for eid in book if eid in graph.entities]
    names = [(eid, sid) for eid, sid in names if sid]
    if not names:
        return {}
    H = horizon
    eff = {sid: mix.effect(sid)[:, H] for _, sid in names}
    n = min(len(v) for v in eff.values())
    if n < 4:
        return {}
    score = np.mean(np.stack([eff[sid][:n] for _, sid in names]), axis=0)
    if float(np.std(score)) < 1e-9:
        masks = {"Base": np.ones(n, dtype=bool)}
    else:
        lo, hi = np.quantile(score, [TAIL, 1.0 - TAIL])
        masks = {"Bull": score >= hi, "Base": (score > lo) & (score < hi), "Bear": score <= lo}

    book_ids = {eid for eid, _ in names}
    drivers = [sid for sid, s in graph.subentities.items() if s.entity_id not in book_ids]
    drv = {}
    for sid in drivers:
        e = mix.effect(sid)[:n, H]
        if float(np.std(e)) > 1e-6 or abs(float(np.median(e))) > 1e-6:
            drv[sid] = e

    def label(sid: str) -> str:
        s = graph.subentities[sid]
        ent = graph.entities.get(s.entity_id)
        own = s.name
        if ent and own.lower().startswith(ent.name.lower()):
            own = own[len(ent.name):].strip(" ·")
        return f"{ent.name} · {own}" if ent and own and own.lower() != ent.name.lower() else s.name

    # the drivers that tell the bear band from the bull band
    none = np.zeros(n, dtype=bool)
    bull, bear = masks.get("Bull", none), masks.get("Bear", none)
    spread = {}
    for sid, e in drv.items():
        hi = float(np.median(e[bull])) if bull.any() else float(np.median(e))
        lo = float(np.median(e[bear])) if bear.any() else float(np.median(e))
        spread[sid] = hi - lo
    key_drivers = sorted(spread, key=lambda s: -abs(spread[s]))[:TOP_DRIVERS]

    rows = []
    for band, m in masks.items():
        p = float(m.mean())
        row = {"band": band, "probability": round(p, 4), "draws": int(m.sum())}
        if m.any():
            moves = {eid: float(np.median(eff[sid][:n][m])) for eid, sid in names}
            ranked = sorted(moves.items(), key=lambda kv: -kv[1])
            row["book_move"] = round(float(np.median(score[m])), 3)
            row["favored"] = [{"entity": eid, "name": graph.entities[eid].name, "value": dict(names)[eid],
                               **native(dict(names)[eid], v, graph)} for eid, v in ranked[:TOP_NAMES] if v > SMALL]
            row["hurt"] = [{"entity": eid, "name": graph.entities[eid].name, "value": dict(names)[eid],
                            **native(dict(names)[eid], v, graph)} for eid, v in reversed(ranked[-TOP_NAMES:]) if v < -SMALL]
            row["mechanism"] = [{"value": sid, "name": label(sid), **native(sid, float(np.median(drv[sid][m])), graph)}
                                for sid in key_drivers]
        rows.append(row)

    # what would change the read: the open hypothesis on the book's names worth the most to learn (one worth nothing
    # to learn would change nothing, so the driver that splits the bands stands in)
    open_h = [h for h in hypotheses.values()
              if str(getattr(h, "status", "open")).endswith("open") and set(getattr(h, "subject_entity_ids", [])) & book_ids
              and (getattr(h, "informational_value", 0.0) or 0.0) > 0.0]
    open_h.sort(key=lambda h: -(getattr(h, "informational_value", 0.0) or 0.0))
    if open_h:
        h = open_h[0]
        changes = {"kind": "hypothesis", "id": h.id, "text": h.statement, "probability": round(h.probability, 3),
                   "informational_value": round(h.informational_value or 0.0, 4)}
    elif key_drivers:
        sid = key_drivers[0]
        changes = {"kind": "driver", "value": sid, "name": label(sid),
                   "text": f"Where {label(sid)} lands: it differs most between the bear and bull bands",
                   "spread": native(sid, spread[sid], graph)}
    else:
        changes = None

    rivals = [{"id": s.id, "name": s.name, "weight": round(s.weight, 4)} for s in scenarios] if len(scenarios) > 1 else []
    return {"tail": TAIL, "horizon_days": H,
            "p_book_up": round(float((score > FLAT).mean()), 4), "p_book_down": round(float((score < -FLAT).mean()), 4),
            "book_median": round(float(np.median(score)), 3), "book": [{"entity": eid, "value": sid, "name": graph.entities[eid].name}
                                                         for eid, sid in names],
            "rows": rows, "changes_the_read": changes, "rival_scenarios": rivals,
            "method": ("The forecast's draws sorted by the book's average move at the horizon (share prices, or "
                       "earnings where a name has no price): bear is the worst quarter, base the middle half, bull the "
                       "best quarter. Each band's moves are medians inside it. The chances of the book ending up or down "
                       "are the shares of all draws.")}
