"""The synthetic world: ground truth for the demo and tests (§11.1).

It runs the same equations as ``mc_impulse`` with one draw of true parameters, plus hidden
interactions, AR(1) noise, and decision rules. It is a MarketEventSource: it emits DATA events on
its release calendar and applies NEWS events' scripted shocks.

# DECISION: the world uses the model's kernel window (104 steps) so it runs exactly the model's
# equations. Steps run Monday to Sunday from the history start; weekly and monthly releases are
# published at the end of each step (Sunday 23:00 UTC), so a release reflects everything that
# happened during its step and nothing later. Decision variables change only through decisions
# at meetings (19:00 UTC); channels into them (e43, e49) are replaced by the decision rules.
# DECISION: the history is re-centered so each decision variable ends the history at its
# construction anchor (decisions depend on inflation, not on the stance's level, so the paths are
# otherwise unchanged). That keeps ME-01 ("to 4.75%") consistent with the world.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.distributions import Link, family_link, from_link, to_link
from axelrod_wm.core.temporal import step_response
from axelrod_wm.engine.propagation import ShockInput
from axelrod_wm.engine.rng import make_rng
from axelrod_wm.events.market import MarketEvent, MarketEventKind
from axelrod_wm.ingest.sources import MarketEventSource

if TYPE_CHECKING:
    from axelrod_wm.engine.initialize import ConstructionSpec

RELEASE_TIME = time(23, 0)
MEETING_TIME = time(19, 0)


class TruthSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effect_multiplier_sd: float = 0.2      # true effect = model prior mean * N(1, sd), drawn once
    ar_coefficient: float = 0.5
    noise_sd: dict[str, float] = {}        # subentity -> standardized noise sd per step; "default" key
    history_noise_sd: float = 0.3          # noise used by generate_history
    hidden_subentities: list[dict] = []    # exist in the world before the model knows them
    hidden_interactions: list[dict] = []   # same fields as interactions.yaml, plus "active_from"
    decision_rules: list[dict] = []        # e.g. the Fed reaction rule (§14.9)
    release_calendar: dict[str, list[str]] = {}   # "weekly" | "monthly" -> subentity ids; "default" = all others
    meetings: dict[str, list[date]] = {}   # decision variable -> meeting dates in the demo window
    history_meeting_every_days: int = 42   # meeting spacing used by generate_history
    effect_overrides: dict[str, float] = {}      # interaction id -> true effect (tuning)
    kernel_overrides: dict[str, dict] = {}       # interaction id -> {delay_days, lag_days, duration_days}
    decision_window_steps: int = 6               # window for a rule's window_change condition

    @classmethod
    def load(cls, path: str) -> TruthSpec:
        import yaml

        from axelrod_wm.engine.initialize import resolve_path

        return cls.model_validate(yaml.safe_load(resolve_path(path).read_text()) or {})


class _Sub:
    def __init__(self, sid: str, anchor: float, scale: float, link: Link, decision: bool) -> None:
        self.id = sid
        self.anchor = anchor
        self.scale = scale
        self.link = link
        self.decision = decision


class _Chan:
    def __init__(self, cid: str, src: str, tgt: str, beta: float, g: np.ndarray, mods: list[tuple[str, str, float, float | None]],
                 active_from: int = 0) -> None:
        self.id = cid
        self.src = src
        self.tgt = tgt
        self.beta = beta
        self.g_rev = g[1:][::-1]
        self.mods = mods
        self.active_from = active_from


class SyntheticWorld(MarketEventSource):
    def __init__(self, construction: ConstructionSpec, truth: TruthSpec, seed: int, *,
                 origin: datetime | None = None, step_days: float = 7.0, window: int = 104,
                 clip: tuple[float, float] = (0.0, 3.0)) -> None:
        self.truth = truth
        self.seed = int(seed)
        self.step_days = float(step_days)
        self.W = int(window)
        self.clip = clip
        self.origin = origin or datetime(2023, 1, 2, tzinfo=UTC)
        self.decision_vars = set(construction.decision_variables)
        self.subs: dict[str, _Sub] = {}
        for e in construction.entities:
            for s in e.subentities:
                fam = s.family or (s.prior or {}).get("family") or "gaussian"
                link = family_link(fam)
                if s.prior is not None:
                    from axelrod_wm.core.distributions import parse_distribution

                    d = dict(s.prior)
                    d.setdefault("family", fam)
                    anchor = parse_distribution(d).link_moments()[0]
                else:
                    anchor = float(to_link(s.mean, link)) if s.mean is not None else 0.0
                self.subs[s.id] = _Sub(s.id, anchor, float(s.scale or 1.0), link, s.id in self.decision_vars)
        for h in truth.hidden_subentities:
            link = family_link(h.get("family", "gaussian"))
            self.subs[h["id"]] = _Sub(h["id"], float(to_link(h.get("anchor_value", 0.0), link)), float(h["scale"]),
                                      link, False)
        rng = make_rng(self.seed, "world", "parameters")
        self.channels: list[_Chan] = []
        for i in construction.interactions:
            if i.target in self.decision_vars:
                continue
            mu = float((i.effect or {}).get("mu", 0.0))
            beta = truth.effect_overrides.get(i.id, mu * float(rng.normal(1.0, truth.effect_multiplier_sd)))
            k = truth.kernel_overrides.get(i.id, i.kernel or {})
            g = self._kernel(k)
            mods = [(p.moderator, str(p.form), float(p.coefficient.get("mu", 0.0)), p.threshold) for p in i.parameters]
            self.channels.append(_Chan(i.id, i.source, i.target, beta, g, mods))
            if i.reverse is not None:
                rmu = float(i.reverse.effect.get("mu", 0.0))
                rbeta = rmu * float(rng.normal(1.0, truth.effect_multiplier_sd))
                self.channels.append(_Chan(i.id + "~r", i.target, i.source, rbeta, self._kernel(i.reverse.kernel), []))
        for h in truth.hidden_interactions:
            g = self._kernel({"delay_days": h.get("delay_days", 7), "lag_days": h.get("lag_days", 14),
                              "duration_days": h.get("duration_days")})
            af = h.get("active_from")
            start = self.step_of(datetime.combine(af, time(0), tzinfo=UTC)) if af else -10**9
            self.channels.append(_Chan(h["id"], h["source"], h["target"], float(h["effect"]), g, [], start))
        self.sids = sorted(self.subs)
        self.reset_state()

    # -- set-up --------------------------------------------------------------------------------
    def _kernel(self, k: dict) -> np.ndarray:
        d = float(k.get("delay_days", 0.0) or 0.0)
        lag = float(k.get("lag_days", 0.0) or 0.0)
        dur = k.get("duration_days")
        d = max(d / self.step_days, 1.0) * self.step_days
        return step_response(d, lag, float(dur) if dur is not None else None, self.W, self.step_days)

    def reset_state(self) -> None:
        self.z: dict[str, list[float]] = {s: [] for s in self.sids}
        self.dz: dict[str, list[float]] = {s: [] for s in self.sids}
        self.level: dict[str, float] = {s: 0.0 for s in self.sids}
        self.u: dict[str, float] = {s: 0.0 for s in self.sids}
        self.offsets: dict[str, float] = {}
        self.steps_done = 0
        self.scheduled: list[tuple[datetime, ShockInput | dict]] = []
        self.pending_events: list[MarketEvent] = []
        self.emitted_until: datetime = self.origin - timedelta(seconds=1)
        self.noise_rng = make_rng(self.seed, "world", "noise")
        self.decision_rng = make_rng(self.seed, "world", "decisions")
        self.history_mode = False
        self.meetings: dict[str, list[date]] = {k: sorted(v) for k, v in self.truth.meetings.items()}
        self.scripted_decisions: dict[tuple[str, date], float] = {}
        self.decision_log: list[tuple[str, date, float]] = []
        self.decided: dict[tuple[str, date], float] = {}
        self.pending_decisions: dict[tuple[str, int], float] = {}

    def step_of(self, t: datetime) -> int:
        return int(math.floor((t - self.origin).total_seconds() / (self.step_days * 86400.0)))

    def step_end(self, k: int) -> datetime:
        start = self.origin + timedelta(days=self.step_days * k)
        return datetime.combine((start + timedelta(days=self.step_days - 1)).date(), RELEASE_TIME, tzinfo=UTC)

    # -- values --------------------------------------------------------------------------------
    def z_at(self, sid: str, k: int) -> float:
        zs = self.z[sid]
        if not zs:
            return self.offsets.get(sid, 0.0)
        return zs[min(max(k, 0), len(zs) - 1)]

    def native(self, sid: str, z: float) -> float:
        s = self.subs[sid]
        return float(from_link(s.anchor + s.scale * z, s.link))

    def size_of(self, sid: str, mode: str, delta: float, k: int) -> float:
        s = self.subs[sid]
        eta = s.anchor + s.scale * self.z_at(sid, k)
        x = float(from_link(eta, s.link))
        if mode == "absolute":
            return (float(to_link(x + delta, s.link)) - eta) / s.scale
        if mode == "relative":
            return (float(to_link(x * (1.0 + delta), s.link)) - eta) / s.scale
        return float(delta)

    # -- shocks --------------------------------------------------------------------------------
    def inject(self, shocks: list[ShockInput], at: datetime, market_event: MarketEvent | None = None) -> None:
        """Schedule world shocks (standardized sizes) at a time."""
        for sh in shocks:
            self.scheduled.append((at, sh))
        if market_event is not None:
            self.pending_events.append(market_event)

    def inject_native(self, shocks: list[dict], at: datetime) -> None:
        """Schedule world shocks given as {subentity, mode, delta}; sizes are fixed when applied."""
        for sh in shocks:
            sid = sh["subentity"]
            if sid in self.decision_vars:
                self.scripted_decisions[(sid, at.date())] = float(sh["delta"])
            self.scheduled.append((at, dict(sh)))

    # -- simulation ----------------------------------------------------------------------------
    def _meeting_time(self, d: date) -> datetime:
        if self.history_mode and d.weekday() == 6:
            return datetime.combine(d, RELEASE_TIME, tzinfo=UTC)
        return datetime.combine(d, MEETING_TIME, tzinfo=UTC)

    def _decide(self, var: str, d: date) -> float:
        """The decision (native change) at a meeting, from completed steps only."""
        if (var, d) in self.scripted_decisions:
            return self.scripted_decisions[(var, d)]
        k = self.step_of(self._meeting_time(d))
        change = 0.0
        for rule in self.truth.decision_rules:
            if rule["decision"] != var:
                continue
            cond = rule.get("condition", {})
            src = cond.get("subentity")
            w = int(cond.get("window_steps", self.truth.decision_window_steps))
            lag = int(cond.get("lag_steps", 0))        # read the source as an edge with this delay would
            end = k - 1 - lag
            wc = self.z_at(src, end) - self.z_at(src, end - w) if src else 0.0
            fire = ("window_change_gt" in cond and wc > float(cond["window_change_gt"])) or \
                   ("window_change_lt" in cond and wc < float(cond["window_change_lt"]))
            if fire and self.decision_rng.random() < float(rule.get("probability", 1.0)):
                change += float(rule.get("change", 0.0))
        return change

    def _ensure_decisions(self, until: datetime) -> None:
        for var, dates in sorted(self.meetings.items()):
            for d in dates:
                t = self._meeting_time(d)
                if t > until or (var, d) in self.decided:
                    continue
                change = self._decide(var, d)
                k = self.step_of(t)
                self.decided[(var, d)] = change
                self.pending_decisions[(var, k)] = self.pending_decisions.get((var, k), 0.0) + change
                self.decision_log.append((var, d, change))

    def _step(self, k: int) -> None:
        """Simulate step k (k == steps_done) once it has ended."""
        start = self.origin + timedelta(days=self.step_days * k)
        end = start + timedelta(days=self.step_days)
        due = [(t, sh) for t, sh in self.scheduled if start <= t < end]
        self.scheduled = [(t, sh) for t, sh in self.scheduled if not (start <= t < end)]
        rho = float(self.truth.ar_coefficient)
        default_sd = float(self.truth.noise_sd.get("default", 0.15))
        hist_sd = float(self.truth.history_noise_sd)
        shock_now: dict[str, float] = {}
        for _t, sh in sorted(due, key=lambda x: x[0]):
            if isinstance(sh, ShockInput):
                sid, size = sh.subentity_id, sh.size
            else:
                sid = sh["subentity"]
                if sid in self.decision_vars:
                    continue           # applied as a scripted decision
                size = self.size_of(sid, sh.get("mode", "standardized"), float(sh["delta"]), k - 1)
            shock_now[sid] = shock_now.get(sid, 0.0) + size
        decided: dict[str, float] = {}
        for sid in self.sids:
            sub = self.subs[sid]
            prev = self.z[sid][-1] if self.z[sid] else self.offsets.get(sid, 0.0)
            if sub.decision:
                decided[sid] = prev + self.pending_decisions.pop((sid, k), 0.0) / sub.scale
                continue
            sd = hist_sd if self.history_mode else float(self.truth.noise_sd.get(sid, default_sd))
            self.level[sid] = rho * self.level[sid] + float(self.noise_rng.normal(0.0, sd))
            self.u[sid] += shock_now.get(sid, 0.0)
        contrib: dict[str, float] = {}
        # every channel reads its source's increments through step k - 1 (the model's minimum delay of
        # one step); a decision taken in step k reaches its children from step k + 1
        for ch in self.channels:
            if k < ch.active_from:
                continue
            inc = self.dz[ch.src]
            n = min(self.W, len(inc))
            if n == 0:
                continue
            window = np.asarray(inc[-n:], dtype=float)
            val = float(np.dot(ch.g_rev[-n:], window))
            m, add = 1.0, 0.0
            for mod, form, gam, thr in ch.mods:
                zm = self.z_at(mod, k - 1)
                if form == "multiplicative":
                    m *= min(max(1.0 + gam * zm, self.clip[0]), self.clip[1])
                elif form == "threshold":
                    m *= 1.0 if zm > (thr or 0.0) else 0.0
                else:
                    add += gam * zm
            contrib[ch.tgt] = contrib.get(ch.tgt, 0.0) + ch.beta * m * val + add
        for sid in self.sids:
            sub = self.subs[sid]
            if sub.decision:
                prev = self.z[sid][-1] if self.z[sid] else None
                self.z[sid].append(decided[sid])
                self.dz[sid].append(decided[sid] - prev if prev is not None else 0.0)
                continue
            prev = self.z[sid][-1] if self.z[sid] else None
            znew = self.offsets.get(sid, 0.0) + self.level[sid] + self.u[sid] + contrib.get(sid, 0.0)
            self.z[sid].append(znew)
            self.dz[sid].append(znew - prev if prev is not None else 0.0)
        self.steps_done = k + 1

    def advance(self, to: datetime) -> None:
        """Simulate every step that has ended by `to`, and make the decisions of meetings held by `to`."""
        while self.step_end(self.steps_done) <= to:
            self._ensure_decisions(self.step_end(self.steps_done))
            self._step(self.steps_done)
        self._ensure_decisions(to)

    # -- releases ------------------------------------------------------------------------------
    def _release_sets(self, include: set[str]) -> tuple[list[str], list[str]]:
        cal = self.truth.release_calendar
        weekly = [s for s in cal.get("weekly", []) if s in include]
        monthly_spec = cal.get("monthly", ["default"])
        if "default" in monthly_spec:
            monthly = [s for s in self.sids if s in include and s not in weekly and s not in self.decision_vars]
        else:
            monthly = [s for s in monthly_spec if s in include]
        return weekly, monthly

    def _releases_between(self, a: datetime, b: datetime) -> list[MarketEvent]:
        """Scheduled data releases and decisions published in (a, b]; requires steps simulated."""
        out: list[MarketEvent] = []
        weekly, monthly = self._release_sets(set(self.sids))
        k0 = max(0, self.step_of(a) - 1)
        k1 = self.step_of(b)
        seen_months: set[tuple[int, int]] = set()
        for k in range(0, k1 + 1):
            t = self.step_end(k)
            ym = (t.year, t.month)
            first_of_month = ym not in seen_months
            seen_months.add(ym)
            if k < k0 or not (a < t <= b) or k >= self.steps_done:
                continue
            series = list(weekly) + (list(monthly) if first_of_month else [])
            data = {sid: round(self.native(sid, self.z[sid][k]), 10) for sid in series}
            out.append(MarketEvent(id=f"ME-D-{t.strftime('%Y%m%d')}", kind=MarketEventKind.DATA,
                                   source="Synthetic statistics office", headline=f"Scheduled data release ({len(data)} series)",
                                   published_at=t, occurred_at=t, data=data, synthetic=True))
        for var, d, change in self.decision_log:
            t = self._meeting_time(d)
            if not (a < t <= b) or (var, d) in self.scripted_decisions:
                continue
            k = self.step_of(t)
            ent = var.split(".")[0]
            z_before = self.z_at(var, k - 1) if k > 0 else self.offsets.get(var, 0.0)
            value = self.native(var, z_before + change / self.subs[var].scale)
            verb = "raises" if change > 0 else ("cuts" if change < 0 else "holds")
            out.append(MarketEvent(id=f"ME-D-{t.strftime('%Y%m%d')}-{ent}", kind=MarketEventKind.DATA,
                                   source="Synthetic central bank feed", event_type="policy_decision",
                                   headline=f"{ent.replace('_', ' ').title()} {verb} its policy rate ({value:.2f}%)",
                                   published_at=t, occurred_at=t, data={var: round(value, 10)}, synthetic=True))
        return sorted(out, key=lambda e: (e.published_at, e.id))

    def poll(self, until: datetime) -> list[MarketEvent]:
        self.advance(until)
        events = self._releases_between(self.emitted_until, until)
        events += [e for e in self.pending_events if e.published_at <= until]
        self.pending_events = [e for e in self.pending_events if e.published_at > until]
        self.emitted_until = max(self.emitted_until, until)
        return sorted(events, key=lambda e: (e.published_at, e.id))

    def realized(self, subentity_id: str, start: datetime, end: datetime) -> list[float]:
        k0, k1 = self.step_of(start), self.step_of(end)
        self.advance(end)
        return [self.native(subentity_id, self.z[subentity_id][k]) for k in range(max(k0, 0), k1 + 1)]

    # -- history -------------------------------------------------------------------------------
    def _history_meetings(self, start: date, end: date) -> dict[str, list[date]]:
        # DECISION: history meetings fall on the weekly release day (Sunday), so a decision and the
        # data it moves land in one daily episode and abduction can see them together.
        first = start + timedelta(days=(6 - start.weekday()) % 7)            # first Sunday
        out: dict[str, list[date]] = {}
        for i, var in enumerate(sorted(self.decision_vars)):
            d = first + timedelta(days=7 * i)
            dates = []
            while d <= end:
                dates.append(d)
                d += timedelta(days=int(self.truth.history_meeting_every_days))
            out[var] = dates
        return out

    def generate_history(self, start: date, end: date, regimes: list[dict]) -> list[MarketEvent]:
        """Simulate the history and return its dated market events (data releases, decisions, and
        regime events). Leaves the world positioned at `end`, ready for the demo."""
        demo_meetings = {k: list(v) for k, v in self.truth.meetings.items()}
        until = datetime.combine(end, time(23, 59, 59), tzinfo=UTC)
        offsets: dict[str, float] = {}
        regime_events: list[tuple[datetime, dict]] = []
        for attempt in range(2):
            self.reset_state()
            if attempt == 1:
                self.offsets = offsets
            self.history_mode = True
            self.meetings = self._history_meetings(start, end)
            regime_events = []
            for r in regimes:
                at = datetime.combine(r["at"] if isinstance(r["at"], date) else date.fromisoformat(str(r["at"])),
                                      time(12, 0), tzinfo=UTC)
                self.inject_native(r.get("shocks", []), at)
                regime_events.append((at, r))
            self.advance(until)
            if attempt == 0:
                offsets = {}
                for var in self.decision_vars:
                    if self.z[var]:
                        offsets[var] = -self.z[var][-1]
        events = self._releases_between(self.origin - timedelta(seconds=1), until)
        for at, r in regime_events:
            k = self.step_of(at)
            data = {sh["subentity"]: round(self.native(sh["subentity"], self.z[sh["subentity"]][k]), 10)
                    for sh in r.get("shocks", [])}
            events.append(MarketEvent(id=f"ME-H-{at.strftime('%Y%m%d')}", kind=MarketEventKind.DATA, source="Synthetic history",
                                      headline=r.get("headline", "Synthetic regime shift"), published_at=at, occurred_at=at,
                                      data=data, tags=list(r.get("tags", [])), event_type=r.get("event_type"),
                                      synthetic=True))
        self.history_mode = False
        self.meetings = {k: sorted(v) for k, v in demo_meetings.items()}
        self.scripted_decisions = {}
        self.decision_log = []
        self.decided = {}
        self.pending_decisions = {}
        self.emitted_until = until
        return sorted(events, key=lambda e: (e.published_at, e.id))

