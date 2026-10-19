"""Evaluation against history (Figure 6, "against history"; §8.14)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.engine.registry import register, registry
from axelrod_wm.evaluation.metrics import covered, crps_quantiles, finite, prob_positive
from axelrod_wm.events.thesis import Thesis

if TYPE_CHECKING:
    from axelrod_wm.inference.records import Forecast


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    freeze_at: datetime
    market_event_ids: list[str] = []
    theses: list[Thesis] = []
    horizon_days: int


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    freeze_at: datetime
    thesis_ids: list[str]
    omission_rate: float
    commission_rate: float
    coverage: dict[str, float]                   # {"50": ..., "80": ..., "90": ...}
    crps: float
    per_target: dict[str, dict[str, float]]
    pattern_hits: dict[str, tuple[int, int]]     # pattern id -> (hits, trials) added
    frozen_version: int = 0
    forecast_ids: list[str] = []


class Scorer(ABC):
    @abstractmethod
    def score(self, forecast: Forecast, realized: dict[str, list[float]], cfg: dict) -> dict[str, Any]: ...


registry("scorer", Scorer)


@register("scorer", "omission_commission_calibration")
class OmissionCommissionCalibrationScorer(Scorer):
    """Omission and commission rates (TRELLIS; Langley & Stromsten, 2000), interval coverage, and CRPS.
    `realized` holds standardized deviations for days 0..H: day 0 is the freeze day, and later days
    hold a value only when the subentity was observed that day (None otherwise). Significance is
    judged on changes from the freeze day, at the last observed day up to the horizon."""

    def __init__(self, config: Any = None) -> None:
        self.config = config

    def score(self, forecast: Forecast, realized: dict[str, list[float]], cfg: dict) -> dict[str, Any]:
        sig = float(cfg.get("significant_effect", 0.5))
        sign_p = float(cfg.get("sign_probability", 0.7))
        H = forecast.horizon_days
        R: set[tuple[str, int]] = set()
        P: set[tuple[str, int]] = set()
        cover = {"50": [0, 0], "80": [0, 0], "90": [0, 0]}
        crps_all: list[float] = []
        per_target: dict[str, dict[str, float]] = {}
        for sid in forecast.targets:
            zs = forecast.z_summary.get(sid)
            real = realized.get(sid)
            if not zs or not real:
                continue
            t_last = last_observed(real, H)
            if t_last is None:
                continue                      # no observation in the window: left out
            z0 = real[0] if real[0] is not None else zs[0].q50
            yh = real[t_last]
            change = yh - z0
            if abs(change) >= sig:
                R.add((sid, 1 if change > 0 else -1))
            pred = zs[t_last].map(lambda q, z0=z0: q - z0)
            if abs(pred.q50) >= sig:
                s = 1 if pred.q50 > 0 else -1
                p_sign = prob_positive(pred) if s > 0 else 1.0 - prob_positive(pred)
                if p_sign >= sign_p:
                    P.add((sid, s))
            crps_t = []
            for t in range(1, min(H, len(real) - 1) + 1):
                y = real[t]
                if y is None:
                    continue
                for band in cover:
                    cover[band][1] += 1
                    if covered(zs[t], y, band):
                        cover[band][0] += 1
                c = crps_quantiles(zs[t], y)
                if finite(c):
                    crps_t.append(c)
            if crps_t:
                crps_all.extend(crps_t)
                per_target[sid] = {"crps": float(np.mean(crps_t)), "realized_change": float(change),
                                   "predicted_change": float(pred.q50), "observed_days": float(len(crps_t))}
        omission = len(R - P) / len(R) if R else 0.0
        commission = len(P - R) / len(P) if P else 0.0
        coverage = {b: (v[0] / v[1] if v[1] else 0.0) for b, v in cover.items()}
        return {"omission_rate": omission, "commission_rate": commission, "coverage": coverage,
                "crps": float(np.mean(crps_all)) if crps_all else 0.0, "per_target": per_target,
                "realized": sorted(f"{s}:{d:+d}" for s, d in R), "predicted": sorted(f"{s}:{d:+d}" for s, d in P)}


def last_observed(real: list[float | None], H: int) -> int | None:
    for t in range(min(H, len(real) - 1), 0, -1):
        if real[t] is not None:
            return t
    return None


def realized_series(dev: Any, sid: str, start_day: int, horizon_days: int) -> list[float | None]:
    """Realized standardized deviations for days 0..H after the freeze day. Day 0 is the point at the
    freeze day; later days only where the subentity was observed (predicted points are the model's own
    output and are never scored)."""
    out: list[float | None] = [dev.z_at(sid, start_day)]
    for k in range(1, horizon_days + 1):
        p = dev.point(sid, start_day + k)
        out.append(p.z if p is not None and p.observed else None)
    return out


def pattern_hit(network_subs: list[str], forecast: Forecast, realized: dict[str, list[float]],
                sig: float) -> bool | None:
    """Hit if predicted signs matched realized signs for at least 70% of the members that moved."""
    H = forecast.horizon_days
    moved, matched = 0, 0
    for sid in network_subs:
        real = realized.get(sid)
        zs = forecast.z_summary.get(sid)
        if not real or not zs or real[0] is None:
            continue
        t_last = last_observed(real, H)
        if t_last is None:
            continue
        change = real[t_last] - real[0]
        if abs(change) < sig:
            continue
        moved += 1
        pred = zs[t_last].q50 - real[0]
        if pred * change > 0:
            matched += 1
    if moved == 0:
        return None
    return matched / moved >= 0.7


def apply_track_records(engine: Any, hits: dict[str, tuple[int, int]], cause: str, at: datetime) -> None:
    """Add (hits, trials) to the live patterns' track records and pool them into their configuration
    generalizations, through the mutator (§8.14 step 6)."""
    patterns = engine.ltm.object_generalizations.patterns
    updater = engine.components.get("generalization_updater")
    ctx = engine.context(learn=True, now=at)
    with engine.mutator.begin(cause=cause, at=at) as txn:
        for pid, (h, n) in sorted(hits.items()):
            p = patterns.get(pid)
            if p is None or n <= 0:
                continue
            txn.update("ltm.object_generalizations.patterns", pid, track_record=p.track_record.plus(h, n - h))
            if updater is not None and hasattr(updater, "update_pattern"):
                updater.update_pattern(pid, engine.ltm, ctx, txn, count_support=False, hits=float(h),
                                       misses=float(n - h))


class Backtester:
    """Freeze at a past recorded time, pose what later happened, compare with the outcome, score."""

    def __init__(self, controller: Any) -> None:
        self.controller = controller

    def run(self, request: EvaluationRequest) -> EvaluationReport:
        from axelrod_wm.engine.engine import build_engine
        from axelrod_wm.events.graph_update import ChangeValue
        from axelrod_wm.repo.ledger import LedgerKind
        from axelrod_wm.repo.snapshots import MemoryBackend
        from axelrod_wm.trace import NullTracer, Phase

        c = self.controller
        eng = c.engine
        cfg = eng.config
        rid = c.ids.next("EVAL")
        # 1. freeze: restore the state as of recorded time in a separate engine
        wm, ltm, version = eng.snapshots.as_of(request.freeze_at)
        frozen = build_engine(cfg, MemoryBackend(), NullTracer(), vocab=eng.vocab)
        frozen.load_state(wm, ltm, version)
        start_day = int(wm.last_processed_day)
        # 2. pose what later happened
        theses: list[Thesis] = []
        for me_id in request.market_event_ids:
            applied = [e for e in c.applied_events if e.market_event_id == me_id]
            ops = [op for e in applied for op in e.ops if isinstance(op, ChangeValue)]
            if not ops:
                continue
            headline = c.market_events[me_id].headline if me_id in c.market_events else me_id
            at = min(op.at for op in ops)
            theses.append(Thesis.model_validate({
                "id": f"{rid}-{me_id}", "question": f"Backtest: {headline}", "mode": "scaffolded",
                "horizon_days": request.horizon_days, "posed_by": "evaluator", "posed_at": request.freeze_at.isoformat(),
                "event": {"id": f"GUE-{rid}-{me_id}", "kind": "hypothetical", "event_type": applied[0].event_type,
                          "occurred_at": at.isoformat(), "recorded_at": request.freeze_at.isoformat(),
                          "produced_by": "engine", "ops": [op.model_dump(mode="json") for op in ops]}}))
        theses.extend(request.theses)
        scorer = eng.components["scorer"]
        sig = float(cfg.evaluation.significant_effect)
        scfg = {"significant_effect": sig, "sign_probability": float(cfg.evaluation.sign_probability)}
        rows = []
        hits: dict[str, list[int]] = {}
        forecast_ids = []
        for th in theses:
            fc = frozen.inference.run(th, request.freeze_at)
            forecast_ids.append(fc.id)
            realized = {sid: realized_series(eng.wm.deviations, sid, start_day, fc.horizon_days)
                        for sid in sorted(set(fc.targets) | {s for n in fc.networks for s in n.subentity_ids})}
            rows.append(scorer.score(fc, realized, scfg))
            for n in fc.networks:
                if not n.pattern_id:
                    continue
                hit = pattern_hit([s for s in n.subentity_ids if s in fc.z_summary], fc, realized, sig)
                if hit is not None:
                    h = hits.setdefault(n.pattern_id, [0, 0])
                    h[0] += int(hit)
                    h[1] += 1
        def avg(key: str) -> float:
            vals = [r[key] for r in rows if r.get(key) is not None]
            return float(np.mean(vals)) if vals else 0.0

        coverage = {b: float(np.mean([r["coverage"][b] for r in rows])) if rows else 0.0 for b in ("50", "80", "90")}
        per_target: dict[str, dict[str, float]] = {}
        for r in rows:
            per_target.update(r["per_target"])
        report = EvaluationReport(id=rid, freeze_at=request.freeze_at, thesis_ids=[t.id for t in theses],
                                  omission_rate=avg("omission_rate"), commission_rate=avg("commission_rate"),
                                  coverage=coverage, crps=avg("crps"), per_target=per_target,
                                  pattern_hits={k: (v[0], v[1]) for k, v in sorted(hits.items())},
                                  frozen_version=version, forecast_ids=forecast_ids)
        # 6. track records, through the live mutator
        if hits:
            apply_track_records(eng, {k: (v[0], v[1]) for k, v in hits.items()}, f"evaluation:{rid}", c.now)
        eng.ledger.append(LedgerKind.EVALUATION, report, recorded_at=c.now)
        eng.tracer.emit(Phase.EVALUATE, "evaluation.done", refs=[rid] + report.thesis_ids,
                        report=report.model_dump(mode="json"))
        return report
