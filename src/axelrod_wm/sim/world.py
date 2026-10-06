"""The synthetic world: ground truth for the demo and tests (§11.1).

It steps the same daily equations as `mc_impulse` with one draw of true parameters, plus hidden
subentities and interactions, AR(1) noise, and decision rules. It knows the scenario's scripted
world shocks in advance and applies each one when its clock passes the shock's occurred_at. The
`synthetic_data_feed` source polls it for data releases.

# DECISION: day 0 is the history's first day, as in the model. A day is simulated as a whole once
# the clock reaches it; a shock that occurs during day k moves z from day k on, and channels read
# their sources through day k - 1 (the minimum delay of one day), so a change reaches its children
# from day k + 1, exactly as in the model.
# DECISION: decision variables change only through decisions at meetings (19:00 UTC); channels into
# them are replaced by the decision rules. A rule reads its source's window change over the
# `window_days` days ending `lag_days` before the meeting (defaults 42 and 0), on 7-day averages.
# DECISION: the history is re-centered so each decision variable ends the history at its
# construction anchor (decisions depend on inflation, not on the stance's level, so the paths are
# otherwise unchanged). That keeps ME-01 ("to 4.75%") consistent with the world.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.distributions import Link, family_link, from_link, parse_distribution, to_link
from axelrod_wm.core.temporal import kernel_days
from axelrod_wm.engine.registry import register
from axelrod_wm.engine.rng import make_rng
from axelrod_wm.events.market import MarketEvent, MarketEventChannel, MarketEventKind
from axelrod_wm.ingest.sources import MarketEventSource, in_window

if TYPE_CHECKING:
    from axelrod_wm.core.taxonomy import AttributeVocabulary
    from axelrod_wm.engine.initialize import ConstructionSpec

RELEASE_TIME = time(21, 0)
MEETING_TIME = time(19, 0)
REGIME_TIME = time(12, 0)
DEFAULT_RULE_WINDOW_DAYS = 42
# DECISION: a rule compares 7-day averages, as a central bank reacts to smoothed inflation rather than to
# one day's noise.
DEFAULT_RULE_SMOOTH_DAYS = 7


class TruthSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effect_multiplier_sd: float = 0.2      # true effect = model prior mean * N(1, sd), drawn once
    ar_coefficient: float = 0.5            # per day
    noise_sd: dict[str, float] = {}        # subentity -> standardized observation noise; default: the model's obs_noise for its kind
    history_noise_sd: float = 0.3          # noise used by generate_history
    hidden_subentities: list[dict] = []    # exist in the world before the model knows them
    hidden_interactions: list[dict] = []   # same fields as interactions.yaml, plus "active_from"
    decision_rules: list[dict] = []        # e.g. the Fed reaction rule (§14.9)
    release_calendar: dict[str, Any] = {}  # "daily" | "weekly" | "monthly" | "never" -> subentity ids;
                                           # "default" names the frequency for all others
    meetings: dict[str, list[date]] = {}   # decision variable -> meeting dates in the demo window
    history_meeting_every_days: int = 42   # meeting spacing used by generate_history
    effect_overrides: dict[str, float] = {}      # interaction id -> true effect (tuning)
    kernel_overrides: dict[str, dict] = {}       # interaction id -> {delay_days, lag_days, duration_days} (tuning)

    @classmethod
    def load(cls, path: str) -> TruthSpec:
        import yaml

        from axelrod_wm.engine.initialize import resolve_path

        return cls.model_validate(yaml.safe_load(resolve_path(path).read_text()) or {})


class _Sub:
    def __init__(self, sid: str, anchor: float, scale: float, link: Link, decision: bool, noise: float) -> None:
        self.id = sid
        self.anchor = anchor
        self.scale = scale
        self.link = link
        self.decision = decision
        self.noise = noise


class _Chan:
    def __init__(self, cid: str, src: int, tgt: int, beta: float, d: int, l: int, lam: float,
                 mods: list[tuple[int, str, float, float | None]], active_from: int = -10**9) -> None:
        self.id = cid
        self.src = src
        self.tgt = tgt
        self.beta = beta
        self.d = d
        self.l = l
        self.lam = lam
        self.mods = mods
        self.active_from = active_from
        self.S = 0.0
        self.T = 0.0


def default_noise(attribute_kind: str | None, vocab: AttributeVocabulary | None) -> float:
    from axelrod_wm.core.taxonomy import default_obs_noise

    return default_obs_noise(attribute_kind or "", vocab)


class SyntheticWorld:
    """Ground truth for the demo and tests (see the module docstring)."""

    def __init__(self, construction: ConstructionSpec, truth: TruthSpec, seed: int,
                 scripted_shocks: list[tuple[datetime, list[dict]]] | None = None, *,
                 origin: date | None = None, vocab: AttributeVocabulary | None = None,
                 clip: tuple[float, float] = (0.0, 3.0), min_delay_days: int = 1) -> None:
        self.truth = truth
        self.seed = int(seed)
        self.clip = clip
        self.origin = origin or date(2023, 1, 2)
        self.decision_vars = set(construction.decision_variables)
        self.subs: dict[str, _Sub] = {}
        for e in construction.entities:
            for s in e.subentities:
                fam = s.family or (s.prior or {}).get("family") or (vocab.family(s.attribute_kind) if vocab else "gaussian")
                link = family_link(fam)
                if s.prior is not None:
                    d = dict(s.prior)
                    d.setdefault("family", fam)
                    anchor = parse_distribution(d).link_moments()[0]
                else:
                    anchor = float(to_link(s.mean, link)) if s.mean is not None else 0.0
                noise = float(truth.noise_sd.get(s.id, truth.noise_sd.get("default", default_noise(s.attribute_kind, vocab))))
                self.subs[s.id] = _Sub(s.id, anchor, float(s.scale or 1.0), link, s.id in self.decision_vars, noise)
        for h in truth.hidden_subentities:
            link = family_link(h.get("family", "gaussian"))
            noise = float(truth.noise_sd.get(h["id"], truth.noise_sd.get("default",
                                                                          default_noise(h.get("attribute_kind"), vocab))))
            self.subs[h["id"]] = _Sub(h["id"], float(to_link(h.get("anchor_value", 0.0), link)), float(h["scale"]),
                                      link, False, noise)
        self.sids = sorted(self.subs)
        self.idx = {s: i for i, s in enumerate(self.sids)}
        # DECISION: each random draw of the world comes from a stream keyed by what it is for (one
        # interaction's true effect, one series' noise), so adding an actor or a link never re-deals the
        # draws of the others and the demo's story stays put as the world grows.
        self.channels: list[_Chan] = []
        for i in construction.interactions:
            if i.target in self.decision_vars:
                continue
            rng = make_rng(self.seed, "world", "parameters", i.id)
            mu = float((i.effect or {}).get("mu", 0.0))
            beta = float(truth.effect_overrides.get(i.id, mu * float(rng.normal(1.0, truth.effect_multiplier_sd))))
            d, l, lam = self._kernel(truth.kernel_overrides.get(i.id, i.kernel or {}), min_delay_days)
            mods = [(self.idx[p.moderator], str(p.form), float(p.coefficient.get("mu", 0.0)), p.threshold)
                    for p in i.parameters if p.moderator in self.idx]
            self.channels.append(_Chan(i.id, self.idx[i.source], self.idx[i.target], beta, d, l, lam, mods))
            if i.reverse is not None and i.source not in self.decision_vars:
                rmu = float(i.reverse.effect.get("mu", 0.0))
                rbeta = rmu * float(rng.normal(1.0, truth.effect_multiplier_sd))
                rd, rl, rlam = self._kernel(i.reverse.kernel, min_delay_days)
                self.channels.append(_Chan(i.id + ":rev", self.idx[i.target], self.idx[i.source], rbeta, rd, rl, rlam, []))
        for h in truth.hidden_interactions:
            d, l, lam = self._kernel({"delay_days": h.get("delay_days", 7), "lag_days": h.get("lag_days", 14),
                                      "duration_days": h.get("duration_days")}, min_delay_days)
            af = h.get("active_from")
            start = self.day_of_date(af if isinstance(af, date) else date.fromisoformat(str(af))) if af else -10**9
            self.channels.append(_Chan(h["id"], self.idx[h["source"]], self.idx[h["target"]], float(h["effect"]),
                                       d, l, lam, [], start))
        self.scripted: list[tuple[datetime, list[dict]]] = sorted(scripted_shocks or [], key=lambda x: x[0])
        self.reset_state()

    # -- set-up --------------------------------------------------------------------------------
    @staticmethod
    def _kernel(k: dict, min_delay_days: int) -> tuple[int, int, float]:
        d = float(k.get("delay_days", 0.0) or 0.0)
        lag = float(k.get("lag_days", 0.0) or 0.0)
        dur = k.get("duration_days")
        return kernel_days(d, lag, float(dur) if dur is not None else None, min_delay_days)

    def reset_state(self) -> None:
        n = len(self.sids)
        self._buf = np.zeros((256, n))                 # [capacity, subentities]; z is its first days_done rows
        self.ar = np.zeros(n)                          # AR(1) noise state
        self.u = np.zeros(n)                           # accumulated step shocks
        self.decided_offset = np.zeros(n)              # accumulated decisions (decision variables)
        self.offsets = np.zeros(n)                     # history re-centering
        for ch in self.channels:
            ch.S = ch.T = 0.0
        self.days_done = 0
        self.history_mode = False
        self.noise_streams = [make_rng(self.seed, "world", "noise", sid) for sid in self.sids]
        self._eps = np.zeros((0, len(self.sids)))     # pre-drawn noise, one column per series' own stream
        self._eps_from = 0                             # the day of the buffer's first row
        self.decision_rng = make_rng(self.seed, "world", "decisions")
        self.meetings: dict[str, list[date]] = {k: sorted(v) for k, v in self.truth.meetings.items()}
        self.scripted_decisions: dict[tuple[str, date], float] = {}
        self.decision_log: list[tuple[str, date, float]] = []
        self.pending: dict[int, list[dict]] = {}        # day -> native shocks
        for at, shocks in self.scripted:
            self._schedule(at, shocks)

    def _schedule(self, at: datetime, shocks: list[dict]) -> None:
        day = self.day_of(at)
        for sh in shocks:
            sid = sh["subentity"]
            if sid in self.decision_vars:
                self.scripted_decisions[(sid, at.date())] = float(sh["delta"])
            else:
                self.pending.setdefault(day, []).append(dict(sh))

    # -- days ----------------------------------------------------------------------------------
    def day_of(self, t: datetime) -> int:
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        return (t.astimezone(UTC).date() - self.origin).days

    def day_of_date(self, d: date) -> int:
        return (d - self.origin).days

    def date_of(self, day: int) -> date:
        return self.origin + timedelta(days=int(day))

    @property
    def z(self) -> np.ndarray:
        """[days simulated, subentities]"""
        return self._buf[: self.days_done]

    # -- values --------------------------------------------------------------------------------
    def z_at(self, sid: str, day: int) -> float:
        i = self.idx[sid]
        if self.days_done == 0 or day < 0:
            return float(self.offsets[i])
        return float(self.z[min(day, self.days_done - 1), i])

    def native(self, sid: str, z: float) -> float:
        s = self.subs[sid]
        return float(from_link(s.anchor + s.scale * z, s.link))

    def size_of(self, sid: str, mode: str, delta: float, day: int) -> float:
        s = self.subs[sid]
        eta = s.anchor + s.scale * self.z_at(sid, day)
        x = float(from_link(eta, s.link))
        if mode == "absolute":
            return (float(to_link(x + delta, s.link)) - eta) / s.scale
        if mode == "relative":
            return (float(to_link(x * (1.0 + delta), s.link)) - eta) / s.scale
        return float(delta)

    # -- simulation ----------------------------------------------------------------------------
    def _decide(self, var: str, d: date) -> float:
        """The decision (native change) at a meeting, from days before the meeting only."""
        if (var, d) in self.scripted_decisions:
            return self.scripted_decisions[(var, d)]
        day = self.day_of_date(d)
        change = 0.0
        for rule in self.truth.decision_rules:
            if rule["decision"] != var:
                continue
            cond = rule.get("condition", {})
            src = cond.get("subentity")
            w = int(cond.get("window_days", DEFAULT_RULE_WINDOW_DAYS))
            lag = int(cond.get("lag_days", 0))
            sm = max(1, int(cond.get("smooth_days", DEFAULT_RULE_SMOOTH_DAYS)))
            end = day - 1 - lag
            wc = self._smoothed(src, end, sm) - self._smoothed(src, end - w, sm) if src else 0.0
            fire = ("window_change_gt" in cond and wc > float(cond["window_change_gt"])) or \
                   ("window_change_lt" in cond and wc < float(cond["window_change_lt"]))
            if fire and self.decision_rng.random() < float(rule.get("probability", 1.0)):
                change += float(rule.get("change", 0.0))
        return change

    def _smoothed(self, sid: str, day: int, days: int) -> float:
        """Mean of z over the `days` days ending on `day`."""
        return float(np.mean([self.z_at(sid, d) for d in range(day - days + 1, day + 1)]))

    def _step(self) -> None:
        """Simulate day k = days_done."""
        k = self.days_done
        n = len(self.sids)
        buf = self._buf
        z_prev = buf[k - 1] if k > 0 else self.offsets.copy()
        # channels: advance each running sum from day k - 1 to day k, reading z through day k - 1
        # (z is 0 before the history; channels read decision variables without their re-centering
        # offset, so re-centering never changes what the world does)
        contrib = np.zeros(n)
        add = np.zeros(n)
        for ch in self.channels:
            if k > 0:
                a = k - ch.d
                b = k - ch.d - ch.l
                za = buf[a, ch.src] - self.offsets[ch.src] if 0 <= a < k else 0.0
                zb = buf[b, ch.src] - self.offsets[ch.src] if 0 <= b < k else 0.0
                ch.S += za - zb
                ch.T = ch.lam * ch.T - (1.0 - ch.lam) * zb
            if k < ch.active_from:
                continue
            m = 1.0
            for mi, form, gam, thr in ch.mods:
                zm = z_prev[mi]
                if form == "multiplicative":
                    m *= min(max(1.0 + gam * zm, self.clip[0]), self.clip[1])
                elif form == "threshold":
                    m *= 1.0 if zm > (thr or 0.0) else 0.0
                else:
                    add[ch.tgt] += gam * zm
            contrib[ch.tgt] += ch.beta * m * (ch.S / ch.l + ch.T)
        # shocks that occur today
        for sh in self.pending.pop(k, []):
            sid = sh["subentity"]
            self.u[self.idx[sid]] += self.size_of(sid, sh.get("mode", "standardized"), float(sh["delta"]), k - 1)
        # decisions at today's meetings
        d = self.date_of(k)
        for var, dates in sorted(self.meetings.items()):
            if d in dates:
                change = self._decide(var, d)
                self.decision_log.append((var, d, change))
                self.decided_offset[self.idx[var]] += change / self.subs[var].scale
        rho = float(self.truth.ar_coefficient)
        sd = (np.full(n, float(self.truth.history_noise_sd)) if self.history_mode
              else np.array([self.subs[s].noise for s in self.sids]))
        self.ar = rho * self.ar + sd * self._noise(k)
        znew = self.offsets + self.ar + self.u + contrib + add
        dec = self._decision_mask()
        znew[dec] = self.offsets[dec] + self.decided_offset[dec]
        if k >= buf.shape[0]:
            grown = np.zeros((buf.shape[0] * 2, n))
            grown[: buf.shape[0]] = buf
            self._buf = buf = grown
        buf[k] = znew
        self.days_done = k + 1

    def _noise(self, k: int) -> np.ndarray:
        """Day k's standard normal draw for every series, each from the series' own stream (drawn in
        blocks; a stream's values do not depend on the block size)."""
        if k - self._eps_from >= self._eps.shape[0]:
            self._eps_from += self._eps.shape[0]
            self._eps = np.stack([g.standard_normal(512) for g in self.noise_streams], axis=1)
        return self._eps[k - self._eps_from]

    def _decision_mask(self) -> np.ndarray:
        if not hasattr(self, "_dec_mask"):
            self._dec_mask = np.array([self.subs[s].decision for s in self.sids], dtype=bool)
        return self._dec_mask

    def advance(self, to: datetime) -> None:
        """Simulate every day up to and including the day of `to`."""
        last = self.day_of(to)
        while self.days_done <= last:
            self._step()

    # -- releases ------------------------------------------------------------------------------
    def _calendar(self) -> dict[str, str]:
        """subentity -> frequency ("daily", "weekly", "monthly", or "never"); decision variables are
        released at their meetings instead."""
        cal = self.truth.release_calendar
        default = cal.get("default", "monthly")
        if isinstance(default, list):
            default = default[0] if default else "monthly"
        out: dict[str, str] = {}
        for freq in ("daily", "weekly", "monthly", "never"):
            for sid in cal.get(freq, []) or []:
                if sid in self.subs:
                    out[sid] = freq
        for sid in self.sids:
            if sid not in out and sid not in self.decision_vars:
                out[sid] = str(default)
        return out

    @staticmethod
    def released_on(freq: str, d: date) -> bool:
        if freq == "daily":
            return d.weekday() < 5
        if freq == "weekly":
            return d.weekday() == 4
        if freq == "monthly":
            return d.day == 15
        return False

    def releases(self, since: datetime | None, until: datetime) -> list[MarketEvent]:
        """Scheduled data releases (21:00 UTC) and decisions (19:00 UTC on meeting days) published in
        (since, until]. Requires the days simulated."""
        cal = self._calendar()
        out: list[MarketEvent] = []
        first = 0 if since is None else max(0, self.day_of(since))
        last = min(self.day_of(until), self.days_done - 1)
        for k in range(first, last + 1):
            d = self.date_of(k)
            t = datetime.combine(d, RELEASE_TIME, tzinfo=UTC)
            if in_window(t, since, until):
                data = {sid: round(self.native(sid, float(self.z[k, self.idx[sid]])), 10)
                        for sid in self.sids if sid in cal and self.released_on(cal[sid], d)}
                if data:
                    out.append(MarketEvent(id=f"ME-D-{d.strftime('%Y%m%d')}", kind=MarketEventKind.DATA,
                                           channel=MarketEventChannel.DATA_FEED, source="Synthetic statistics office",
                                           headline=f"Scheduled data release ({len(data)} series)",
                                           published_at=t, occurred_at=t, data=data, event_type="data_release",
                                           synthetic=True))
        for var, d, change in self.decision_log:
            t = datetime.combine(d, MEETING_TIME, tzinfo=UTC)
            if not in_window(t, since, until):
                continue
            k = self.day_of_date(d)
            ent = var.split(".")[0]
            value = self.native(var, float(self.z[k, self.idx[var]]))
            verb = "raises" if change > 0 else ("cuts" if change < 0 else "holds")
            out.append(MarketEvent(id=f"ME-D-{d.strftime('%Y%m%d')}-{ent}", kind=MarketEventKind.DATA,
                                   channel=MarketEventChannel.DATA_FEED, source="Synthetic central bank feed",
                                   event_type="policy_decision",
                                   headline=f"{ent.replace('_', ' ').title()} {verb} its policy rate ({value:.2f}%)",
                                   published_at=t, occurred_at=t, data={var: round(value, 10)}, synthetic=True))
        return sorted(out, key=lambda e: (e.published_at, e.id))

    def realized(self, subentity_id: str, start: datetime, end: datetime) -> list[float]:
        self.advance(end)
        k0, k1 = max(self.day_of(start), 0), self.day_of(end)
        return [self.native(subentity_id, float(self.z[k, self.idx[subentity_id]])) for k in range(k0, k1 + 1)]

    # -- history -------------------------------------------------------------------------------
    def _history_meetings(self, start: date, end: date) -> dict[str, list[date]]:
        # DECISION: history meetings fall on Wednesdays (the demo's meeting weekday), one week apart
        # per decision variable, every history_meeting_every_days.
        first = start + timedelta(days=(2 - start.weekday()) % 7)
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
        regime events). Leaves the world positioned at the end of `end`, ready for the demo."""
        until = datetime.combine(end, time(23, 59, 59), tzinfo=UTC)
        offsets = np.zeros(len(self.sids))
        regime_at: list[tuple[datetime, dict]] = []
        for attempt in range(2):
            self.reset_state()
            self.offsets = offsets.copy()
            self.history_mode = True
            demo_meetings = self.meetings
            self.meetings = self._history_meetings(start, end)
            regime_at = []
            for r in regimes:
                at = datetime.combine(r["at"] if isinstance(r["at"], date) else date.fromisoformat(str(r["at"])),
                                      REGIME_TIME, tzinfo=UTC)
                self._schedule(at, r.get("shocks", []))
                regime_at.append((at, r))
            self.advance(until)
            self.meetings = demo_meetings
            if attempt == 0:
                last = self.days_done - 1
                offsets = np.zeros(len(self.sids))
                for var in self.decision_vars:
                    offsets[self.idx[var]] = -float(self.z[last, self.idx[var]])
        events = self.releases(None, until)
        for at, r in regime_at:
            k = self.day_of(at)
            data = {sh["subentity"]: round(self.native(sh["subentity"], float(self.z[k, self.idx[sh["subentity"]]])), 10)
                    for sh in r.get("shocks", []) if sh["subentity"] in self.idx}
            events.append(MarketEvent(id=f"ME-H-{at.strftime('%Y%m%d')}", kind=MarketEventKind.DATA,
                                      channel=MarketEventChannel.DATA_FEED, source="Synthetic history",
                                      headline=r.get("headline", "Synthetic regime shift"), published_at=at,
                                      occurred_at=at, data=data, tags=list(r.get("tags", [])),
                                      event_type=r.get("event_type"), synthetic=True))
        self.history_mode = False
        self.decision_log = []
        return sorted(events, key=lambda e: (e.published_at, e.id))


@register("source", "synthetic_data_feed")
class SyntheticDataFeed(MarketEventSource):
    """Registered as `synthetic_data_feed`. poll(since, until) advances the world to `until` and
    returns its data releases in the window: one DATA market event per day with releases
    (id ME-D-<YYYYMMDD>, channel DATA_FEED, published 21:00 UTC), keyed by subentity id, following
    the release calendar. A decision variable's release on a meeting day is its own event,
    published 19:00 UTC. A scripted data event (such as ME-01) replaces that event's id and adds
    its headline."""

    name = "synthetic_data_feed"

    def __init__(self, world: SyntheticWorld | None = None, scripted: list[MarketEvent] | None = None,
                 config: Any = None, **_: Any) -> None:
        if world is None:
            raise ValueError("synthetic_data_feed needs a SyntheticWorld (the scenario runner registers it)")
        self.world = world
        self.scripted = sorted(scripted or [], key=lambda e: (e.published_at, e.id))

    def poll(self, since: datetime | None, until: datetime) -> list[MarketEvent]:
        self.world.advance(until)
        events = self.world.releases(since, until)
        by_slot = {}
        for e in self.scripted:
            if in_window(e.published_at, since, until):
                by_slot[(e.published_at.date(), tuple(sorted(e.data)))] = e
        out = []
        for e in events:
            sc = by_slot.pop((e.published_at.date(), tuple(sorted(e.data))), None)
            if sc is not None:
                out.append(e.model_copy(update={"id": sc.id, "headline": sc.headline, "body": sc.body,
                                                "mentions": list(sc.mentions), "tags": list(sc.tags),
                                                "event_type": sc.event_type or e.event_type,
                                                "published_at": sc.published_at, "occurred_at": sc.occurred_at}))
            else:
                out.append(e)
        out.extend(by_slot.values())       # scripted data events with no matching release
        return sorted(out, key=lambda e: (e.published_at, e.id))
