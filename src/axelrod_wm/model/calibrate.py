"""Calibrate a link from a disclosed sensitivity (Oct 17).

A company or a broker discloses "a 1-unit move in X changes Y by Z", each in its native unit (a ¥1 move in USD/JPY
changes operating income by ¥45bn). A link's effect is in standard units: target sd per source sd. Each value's
`scale` is its sd in link space (the native unit for a Gaussian value, log units for a lognormal one), so the
disclosed changes convert at the values' construction levels:

    z_X = (link(level_X + dX) - link(level_X)) / scale_X        (dX / scale_X for an identity link)
    z_Y = (link(level_Y + dY) - link(level_Y)) / scale_Y
    effect = z_Y / z_X

The spread (sigma) comes from a range when one is given, read as plus or minus two sigma (sigma = (hi - lo) / 4), either
in sd/sd (`sd_range`) or as the target change's native range (`target_range`, converted like dY); otherwise it is a
stated fraction of the effect (DEFAULT_SIGMA_FRACTION). The link becomes calibrated: it gets the effect, loses
`calibration: uncalibrated`, and its transition records the magnitude's support and the source.

It refuses: an unknown link; an accounting, identity or stock-flow link (a fixed weight, never sized from a
sensitivity); a link without a transition (the evidence is recorded there); a zero source or target change; a level the
change would take outside the value's domain; and a sign that contradicts the transition's (or, without one, the current
effect's) unless the flip is explicitly allowed with a reason, which is recorded on the link.

Oct 18, state-dependent responses (model/construction.ResponseState): `side` ("rises" or "falls") sizes one side of an
asymmetric link (a deposit beta in hikes, or in cuts); the other side keeps its size (the link's current effect, when it
had none). `stop_when` and `flip_when` write the condition a disclosure states with the size: a threshold that stops the
response, or the level at which its sign flips.

Oct 18, scenario disclosures (`calibrate_from_scenarios`): several disclosed scenarios ("+100bp parallel: +2.9bn; steeper
curve: +0.9bn"), each moving one or more sources, reported as one change of one target, size one or more links into that
target jointly. Each scenario is one equation, z_Y = sum_l effect_l x z_X(l): a disclosed net sensitivity spread over
parallel links is solved with them. The sizes are the least-squares solution; the method refuses when the scenarios
cannot separate the links (fewer scenarios than sizes, or a rank-deficient design), and records the scenarios on each
link. A link split into rises and falls has two sizes, each scenario using the side its source moves to.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from axelrod_wm.model.distributions import Link, family_link, from_link, to_link
from axelrod_wm.model.interaction import FIXED_EDGE_TYPES, Calibration, Direction

SIDES = ("rises", "falls")

DEFAULT_SIGMA_FRACTION = 0.25        # without a range: sigma is a quarter of the effect
PEER_SIGMA_FRACTION = 0.5            # a size borrowed from a comparable company: half the effect (Oct 18)
SUPPORTS = ("documented", "guidance", "broker", "peer", "model", "inferred")
# model: a documented total placed on a part by our own split; inferred: a remainder after netting represented channels
# (R13). Both, like peer, are wider than a direct disclosure (Oct 18, Toyota pack round)
WIDE_SUPPORTS = ("peer", "model", "inferred")
LARGE_EFFECT = 3.0                   # sd/sd; a larger effect usually means a change in the wrong unit


class CalibrationError(ValueError):
    """A calibration the method refuses, with the reason."""


@dataclass(frozen=True)
class LinkCalibration:
    interaction_id: str
    source_id: str
    target_id: str
    source_change: float | None      # native units of the source (None for a scenario calibration)
    target_change: float | None      # native units of the target
    source_z: float | None           # the same changes in standard units
    target_z: float | None
    effect: float                    # sd/sd, rounded
    sigma: float
    sigma_rule: str
    support: str                     # the magnitude's support: documented, guidance or broker
    evidence: str                    # the source id
    sign: str                        # "+" or "-"
    before: dict                     # the interaction as it was (calibration, effect, sign, magnitude support)
    flip_reason: str | None = None   # set when the sign contradicts the transition and the flip was allowed
    notes: list[str] = field(default_factory=list)
    side: str | None = None          # "rises" or "falls" when one side of an asymmetric link was sized
    asymmetry: dict | None = None    # the link's sizes by side after the calibration ({rises: {mu, sigma}, falls: ...})
    state: dict = field(default_factory=dict)   # conditions written with the size: {threshold: ..., sign_flip: ...}
    scenarios: list[str] = field(default_factory=list)   # the disclosed scenarios a scenario calibration solved over
    scenario_note: str | None = None


@dataclass(frozen=True)
class Scenario:
    """One disclosed scenario: the sources' moves (native units) and the target's reported change."""

    id: str
    changes: dict[str, float]
    target_change: float


@dataclass(frozen=True)
class ScenarioCalibration:
    target_id: str
    links: list[LinkCalibration]
    scenarios: list[str]
    unknowns: list[str]              # "<link>" or "<link>:<side>"
    design: list[list[float]]        # scenario x unknown: the source's move in sd (0 where the unknown does not act)
    observed: list[float]            # each scenario's target change in sd
    fitted: list[float]
    residual_sd: float | None        # the residual standard error, when the scenarios over-determine the sizes
    notes: list[str] = field(default_factory=list)


def _value(spec: Any, vocab: Any, sid: str) -> tuple[float, float, Link, str]:
    """(native level, link-space scale, link, unit) of a construction value."""
    from axelrod_wm.engine.initialize import _native_prior

    s = next(s for e in spec.entities for s in e.subentities if s.id == sid)
    family = s.family or (s.prior or {}).get("family") or vocab.family(s.attribute_kind)
    prior, scale = _native_prior(s, family, vocab)
    link = family_link(family)
    return float(from_link(prior.link_moments()[0], link)), scale, link, s.unit


def standardized_change(level: float, change: float, scale: float, link: Link, what: str) -> float:
    """A native change at `level`, in standard units of a value with link-space sd `scale`."""
    new = level + change
    if (link == Link.LOG and new <= 0) or (link == Link.LOGIT and not 0 < new < 1):
        raise CalibrationError(f"{what}: a change of {change:g} from {level:g} leaves the value's domain ({link} link)")
    return (to_link(new, link) - to_link(level, link)) / scale


def default_fraction(support: str) -> float:
    """Sigma as a fraction of the effect without a range: wider for a size borrowed from a peer, split by us, or
    solved as a remainder."""
    return PEER_SIGMA_FRACTION if support in WIDE_SUPPORTS else DEFAULT_SIGMA_FRACTION


def _round(x: float) -> float:
    return round(float(x), 4)


def _check_link(spec: Any, interaction_id: str) -> Any:
    inter = {i.id: i for i in spec.interactions}
    if interaction_id not in inter:
        raise CalibrationError(f"no interaction {interaction_id!r}")
    i = inter[interaction_id]
    if i.edge_type in FIXED_EDGE_TYPES:
        raise CalibrationError(f"{interaction_id} is an {i.edge_type} link: its weight is an identity, not a sensitivity")
    if i.transition is None:
        raise CalibrationError(f"{interaction_id} has no transition to record the evidence on; add one first")
    return i


def _stated_sign(i: Any) -> str | None:
    a = i.state.asymmetry if i.state is not None else None
    mu = (i.effect or {}).get("mu") if a is None else (a.rises.get("mu") or a.falls.get("mu"))
    return i.transition.sign or (None if not mu else ("+" if mu > 0 else "-"))


def _sides_after(i: Any, side: str, mu: float, sigma: float) -> dict:
    """The link's asymmetry after sizing one side: the other side keeps its size (its asymmetry's, else the link's
    current effect); refused when it has none."""
    other = "falls" if side == "rises" else "rises"
    a = i.state.asymmetry if i.state is not None else None
    if a is not None:
        kept = dict(getattr(a, other))
    elif i.calibration == Calibration.CALIBRATED and i.effect is not None:
        kept = {k: v for k, v in i.effect.items() if k in ("mu", "sigma")}
    else:
        raise CalibrationError(f"{i.id}: sizing only its {side} needs the {other} size; calibrate the link first, or "
                               "solve both sides from scenarios")
    return {side: {"mu": mu, "sigma": sigma}, other: kept}


def _conditions(spec: Any, stop_when: tuple[str, str, float] | None,
                flip_when: tuple[str, str, float] | None) -> dict:
    known = spec.subentity_ids()
    out: dict = {}
    for name, cond in (("threshold", stop_when), ("sign_flip", flip_when)):
        if cond is None:
            continue
        value, side, level = cond
        if value not in known:
            raise CalibrationError(f"{name}: no value {value!r}")
        if side not in ("above", "below"):
            raise CalibrationError(f"{name}: the side is 'above' or 'below', not {side!r}")
        out[name] = {"value": value, side: float(level)} if name == "threshold" else \
            {"value": value, "at": float(level), "positive": side}
    return out


def calibrate_from_sensitivity(spec: Any, vocab: Any, interaction_id: str, *, source_change: float,
                               target_change: float, evidence: str, support: str = "documented",
                               sd_range: tuple[float, float] | None = None,
                               target_range: tuple[float, float] | None = None,
                               sigma_fraction: float | None = None,
                               allow_sign_flip: bool = False, reason: str | None = None, side: str | None = None,
                               stop_when: tuple[str, str, float] | None = None,
                               flip_when: tuple[str, str, float] | None = None) -> LinkCalibration:
    """The calibration a disclosed sensitivity gives a link of `spec` (a loaded ConstructionSpec); see the module."""
    i = _check_link(spec, interaction_id)
    if side is not None and side not in SIDES:
        raise CalibrationError(f"side must be one of {', '.join(SIDES)}")
    if support not in SUPPORTS:
        raise CalibrationError(f"support must be one of {', '.join(SUPPORTS)}")
    if source_change == 0:
        raise CalibrationError("a source change of zero says nothing about the link")
    if target_change == 0:
        raise CalibrationError("a target change of zero gives no effect and no direction; the link stays uncalibrated")
    if sd_range is not None and target_range is not None:
        raise CalibrationError("give one range: in sd/sd or as the target's native range")
    sigma_fraction = default_fraction(support) if sigma_fraction is None else sigma_fraction
    if not 0 < sigma_fraction:
        raise CalibrationError("the sigma fraction must be positive")
    lx, sx, kx, ux = _value(spec, vocab, i.source)
    ly, sy, ky, uy = _value(spec, vocab, i.target)
    zx = standardized_change(lx, source_change, sx, kx, i.source)
    zy = standardized_change(ly, target_change, sy, ky, i.target)
    effect = zy / zx
    sign = "+" if effect > 0 else "-"
    flip = _flip(i, sign, allow_sign_flip, reason)
    if target_range is not None:
        sd_range = tuple(standardized_change(ly, t, sy, ky, i.target) / zx for t in target_range)
    if sd_range is not None:
        lo, hi = sorted(sd_range)
        if hi == lo:
            raise CalibrationError("a range needs two different ends")
        if not lo <= effect <= hi:
            raise CalibrationError(f"the effect {effect:.4f} lies outside its range {lo:.4f} to {hi:.4f}")
        sigma, rule = (hi - lo) / 4, f"the range {lo:.4f} to {hi:.4f} sd/sd read as plus or minus two sigma"
    else:
        sigma, rule = abs(effect) * sigma_fraction, f"{sigma_fraction:g} of the effect (no range given)"
    notes = [f"units: the source in {ux} (level {lx:g}, scale {sx:g} {kx}), the target in {uy} (level {ly:g}, "
             f"scale {sy:g} {ky})"]
    if abs(effect) > LARGE_EFFECT:
        notes.append(f"the effect is over {LARGE_EFFECT:g} sd/sd: check that both changes are in these units")
    if i.kernel is None:
        notes.append("no kernel is set: the default timing applies (14-day delay, 30-day lag, permanent); add a "
                     "`kernel:` if the disclosure states timing")
    if i.direction == Direction.BIDIRECTIONAL:
        notes.append("the link is bidirectional: only its forward effect is calibrated")
    sig = max(_round(sigma), 0.0001)
    asym = _sides_after(i, side, _round(effect), sig) if side is not None else None
    if side is not None:
        notes.append(f"sized its {side}: the link's sizes are now rises {asym['rises']} and falls {asym['falls']}")
    return LinkCalibration(interaction_id=interaction_id, source_id=i.source, target_id=i.target,
                           source_change=source_change, target_change=target_change, source_z=zx, target_z=zy,
                           effect=_round(effect), sigma=sig, sigma_rule=rule, support=support,
                           evidence=evidence, sign=sign, before=_before(i), flip_reason=flip, notes=notes, side=side,
                           asymmetry=asym, state=_conditions(spec, stop_when, flip_when))


def _before(i: Any) -> dict:
    return {"calibration": str(i.calibration), "effect": i.effect, "sign": i.transition.sign,
            "magnitude": i.transition.evidence.magnitude, "sources": list(i.transition.evidence.sources),
            "state": i.state.model_dump(mode="json", exclude_none=True) if i.state is not None else None}


def _flip(i: Any, sign: str, allow_sign_flip: bool, reason: str | None) -> str | None:
    stated = _stated_sign(i)
    if stated is None or stated == sign:
        return None
    if not allow_sign_flip or not (reason or "").strip():
        raise CalibrationError(f"the disclosure gives {sign} but {i.id} states {stated}; pass "
                               "--allow-sign-flip with a --reason to change the link's direction")
    return reason.strip()


def calibrate_from_scenarios(spec: Any, vocab: Any, *, target: str, links: list[str], scenarios: list[Scenario],
                             evidence: str, support: str = "documented", split: list[str] | None = None,
                             sigma_fraction: float | None = None, allow_sign_flip: bool = False,
                             reason: str | None = None) -> ScenarioCalibration:
    """Size `links` (each into `target`) from several disclosed scenarios by least squares; see the module. A link in
    `split`, or one that already has an asymmetry, gets a size for rises and one for falls."""
    if support not in SUPPORTS:
        raise CalibrationError(f"support must be one of {', '.join(SUPPORTS)}")
    sigma_fraction = default_fraction(support) if sigma_fraction is None else sigma_fraction
    if not 0 < sigma_fraction:
        raise CalibrationError("the sigma fraction must be positive")
    if not links or len(set(links)) < len(links):
        raise CalibrationError("give each link to size once")
    inter = [_check_link(spec, lid) for lid in links]
    for i in inter:
        if i.target != target:
            raise CalibrationError(f"{i.id} points at {i.target}, not at the scenarios' target {target}")
    split = set(split or [])
    if split - set(links):
        raise CalibrationError(f"split names links that are not sized here: {', '.join(sorted(split - set(links)))}")
    ids = [sc.id for sc in scenarios]
    if len(set(ids)) < len(ids):
        raise CalibrationError("scenario ids must be distinct")
    sources = {i.source for i in inter}
    for sc in scenarios:
        stray = sorted(set(sc.changes) - sources)
        if stray:
            raise CalibrationError(f"scenario {sc.id} moves {', '.join(stray)}, which none of the links carries into "
                                   f"{target}; add the link or leave the move out")
    ly, sy, ky, uy = _value(spec, vocab, target)
    unknowns: list[tuple[Any, str | None]] = []
    for i in inter:
        two = i.id in split or (i.state is not None and i.state.asymmetry is not None)
        unknowns += [(i, "rises"), (i, "falls")] if two else [(i, None)]
    vals = {src: _value(spec, vocab, src) for src in sources}
    X = np.zeros((len(scenarios), len(unknowns)))
    y = np.zeros(len(scenarios))
    for r, sc in enumerate(scenarios):
        y[r] = standardized_change(ly, sc.target_change, sy, ky, f"scenario {sc.id}: {target}")
        for c, (i, side) in enumerate(unknowns):
            dx = sc.changes.get(i.source, 0.0)
            if dx == 0:
                continue
            lx, sx, kx, _ = vals[i.source]
            a = i.state.asymmetry if i.state is not None else None
            at = lx if a is None or a.at is None else a.at
            if side is None or side == ("rises" if lx + dx > at else "falls"):
                X[r, c] = standardized_change(lx, dx, sx, kx, f"scenario {sc.id}: {i.source}")
    names = [i.id if side is None else f"{i.id}:{side}" for i, side in unknowns]
    empty = [names[c] for c in range(len(unknowns)) if not np.any(X[:, c])]
    if empty:
        raise CalibrationError(f"underdetermined: no scenario moves {', '.join(empty)}")
    rank = int(np.linalg.matrix_rank(X))
    if len(scenarios) < len(unknowns) or rank < len(unknowns):
        raise CalibrationError(f"underdetermined: {len(scenarios)} scenario(s) of rank {rank} cannot separate "
                               f"{len(unknowns)} size(s) ({', '.join(names)}); disclose a scenario that moves them apart")
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    fitted = X @ beta
    dof = len(scenarios) - len(unknowns)
    rss = float(np.sum((y - fitted) ** 2))
    resid = (rss / dof) ** 0.5 if dof > 0 else None
    cov = np.linalg.inv(X.T @ X)
    sizes: dict[str, dict[str | None, tuple[float, float, str]]] = {}
    for c, (i, side) in enumerate(unknowns):
        b = float(beta[c])
        if b == 0:
            raise CalibrationError(f"{names[c]}: the scenarios give it no size and no direction")
        se = (rss / dof * float(cov[c, c])) ** 0.5 if dof > 0 and rss > 0 else 0.0
        sig, rule = ((se, f"the least-squares standard error over {dof} spare scenario(s)") if se > 0 else
                     (abs(b) * sigma_fraction, f"{sigma_fraction:g} of the effect (the scenarios fit exactly)"))
        sizes.setdefault(i.id, {})[side] = (b, sig, rule)
    out = []
    for i in inter:
        got = sizes[i.id]
        first = got.get(None) or got["rises"]
        b, sig, rule = first
        sign = "+" if b > 0 else "-"
        flips = {_flip(i, "+" if v[0] > 0 else "-", allow_sign_flip, reason) for v in got.values()}
        flip = next((f for f in flips if f is not None), None)
        asym = None
        if None not in got:
            asym = {sd: {"mu": _round(v[0]), "sigma": max(_round(v[1]), 0.0001)} for sd, v in got.items()}
        used = [sc.id for sc in scenarios if sc.changes.get(i.source, 0.0) != 0]
        others = [x for x in links if x != i.id]
        note = (f"sized by least squares over the disclosed scenarios {', '.join(used)} ({evidence})"
                + (f", jointly with {', '.join(others)}" if others else ""))
        out.append(LinkCalibration(
            interaction_id=i.id, source_id=i.source, target_id=i.target, source_change=None, target_change=None,
            source_z=None, target_z=None, effect=_round(b), sigma=max(_round(sig), 0.0001), sigma_rule=rule,
            support=support, evidence=evidence, sign=sign, before=_before(i), flip_reason=flip,
            notes=[note], side=None, asymmetry=asym, scenarios=used, scenario_note=note))
    notes = [f"units: the target in {uy} (level {ly:g}, scale {sy:g} {ky})"]
    if resid is not None:
        notes.append(f"residual standard error {resid:.4f} sd over {dof} spare scenario(s)")
    return ScenarioCalibration(target_id=target, links=out, scenarios=ids, unknowns=names, design=X.round(6).tolist(),
                               observed=y.round(6).tolist(), fitted=fitted.round(6).tolist(), residual_sd=resid,
                               notes=notes)


def calibrated_entry(raw: dict, cal: LinkCalibration) -> dict:
    """The interaction's construction entry (a parsed YAML mapping) after the calibration."""
    out = copy.deepcopy(raw)
    out.pop("calibration", None)
    state = new_state(raw, cal)
    if cal.asymmetry is not None:
        out.pop("effect", None)
    else:
        out["effect"] = {"mu": cal.effect, "sigma": cal.sigma}
    if state is not None:
        out["state"] = state
    if cal.scenario_note is not None:
        out["note"] = f"{raw['note']} | {cal.scenario_note}" if raw.get("note") else cal.scenario_note
    t = out["transition"]
    ev = t.setdefault("evidence", {})
    ev["magnitude"] = cal.support
    sources = ev.setdefault("sources", [])
    if cal.evidence not in sources:
        sources.append(cal.evidence)
    if cal.flip_reason is not None:
        t["sign"] = cal.sign
        ev["direction"] = cal.support
        out["note"] = flip_note(out.get("note"), cal)
    return out


def new_state(raw: dict, cal: LinkCalibration) -> dict | None:
    """The entry's `state` after the calibration (None when it neither had nor gains one)."""
    if cal.asymmetry is None and not cal.state:
        return None
    state = copy.deepcopy(raw.get("state") or {})
    if cal.asymmetry is not None:
        state["asymmetry"] = {**(state.get("asymmetry") or {}), **cal.asymmetry}
    state.update(copy.deepcopy(cal.state))
    return state


def flip_note(existing: str | None, cal: LinkCalibration) -> str:
    new = f"sign set to {cal.sign} by calibration from {cal.evidence}: {cal.flip_reason}"
    return f"{existing} | {new}" if existing else new


def _reach(spec: Any, starts: set[str], also: str | None = None) -> set[str]:
    """Values a shock to `starts` reaches through quantified links (and `also`, as if it were)."""
    out: dict[str, list[str]] = {}
    for i in spec.interactions:
        if i.calibration == Calibration.UNCALIBRATED and i.id != also:
            continue
        out.setdefault(i.source, []).append(i.target)
        if i.direction == Direction.BIDIRECTIONAL:
            out.setdefault(i.target, []).append(i.source)
    seen, stack = set(), list(starts)
    while stack:
        v = stack.pop()
        if v not in seen:
            seen.add(v)
            stack.extend(out.get(v, []))
    return seen


def unquantified_change(spec: Any, shocks: dict[str, list[str]], interaction_id: str) -> dict[str, dict]:
    """For each forecast (thesis id -> the values it shocks) whose `unquantified` list holds the link (its shock reaches
    the link's source through quantified links): the link leaves the list, and the uncalibrated links its calibration
    newly lets the shock reach enter it. Reach ignores the horizon and the size of each step, as an upper bound."""
    i = next(x for x in spec.interactions if x.id == interaction_id)
    uncal = [x for x in spec.interactions if x.calibration == Calibration.UNCALIBRATED and x.id != interaction_id]
    out = {}
    for tid, starts in sorted(shocks.items()):
        before = _reach(spec, set(starts))
        if i.source not in before:
            continue
        after = _reach(spec, set(starts), also=interaction_id)
        out[tid] = {"leaves": interaction_id,
                    "enters": sorted(x.id for x in uncal if x.source in after and x.source not in before)}
    return out


__all__ = ["DEFAULT_SIGMA_FRACTION", "PEER_SIGMA_FRACTION", "SIDES", "SUPPORTS", "WIDE_SUPPORTS", "CalibrationError", "LinkCalibration", "Scenario",
           "ScenarioCalibration", "calibrate_from_scenarios", "calibrate_from_sensitivity", "calibrated_entry",
           "flip_note", "new_state", "standardized_change", "unquantified_change"]
