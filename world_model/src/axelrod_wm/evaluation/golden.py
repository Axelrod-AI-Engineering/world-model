"""Golden test bank: ask the world model a question, answer from the world model alone, and grade the answer
(Oct 18, the reviewer's batch 2).

A case is a question, an optional controlled fixture, and a hidden grading spec. The responder sees only the question
and the fixture; it answers through world-model reads (search, the company's construction, its relationships with their
retrieval profiles, traces, attributes and observations), identity and stock-flow arithmetic, and the native slopes of
sized links. It never sees the grading. The grader scores four outcomes separately (evidence retrieval, mechanism,
calculation, timing and communication), each Pass, Partial, Fail or Not tested. No composite score is reported, and a
critical failure (a wrong sign, scope, unit or accounting) is listed on its own so nothing averages it away.

The fixture states its inputs in the model's ids, so the arithmetic comes from the model's objects:

    fixture:
      levels:  {value id: number}          # stipulated levels (identity terms, balances)
      deltas:  {value id: number}          # stipulated changes, native units (fixed: never recomputed)
      hold:    [value id]                  # held constant (a deliberate zero, labelled so)
      slopes:  {link id: number}           # a stipulated native coefficient (e.g. a controlled tax rate)
      clocks:  {rate id: {shock, reset_share, time}}   # repricing: only the share that resets, for the time active
      offsets: {link id: {gross, hedge, pass_through}} # gross exposure, hedge cover, then pass-through of the rest
      periods: [{label, deltas}]           # stock-flow periods, solved one by one and summed
      variants: [{label, ...overrides}]    # the same question again with some inputs changed
      convert: {factor, unit}              # a stated conversion of every result (e.g. a fixed exchange rate)
      outputs: [value id]                  # what the question asks about
      shock:   {value id: delta}           # a change to follow when the question is about coverage

Each calculation records its rule, formula, inputs and result, and what it rests on (the fixture or the model). Effects
the model cannot size are listed with a state - measured zero, held constant, not applicable, or unknown or
unimplemented - and never enter a sum as zero.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

OUTCOMES = ("Pass", "Partial", "Fail", "Not tested")
STATES = ("measured zero", "held constant", "not applicable", "unknown or unimplemented")
UNKNOWN = "unknown or unimplemented"


# -- reading the world model ----------------------------------------------------------------------------------------------
class Reader(Protocol):
    calls: list[str]

    def construction(self, entity_id: str) -> dict: ...
    def links(self, entity_id: str) -> dict[str, dict]: ...
    def trace(self, entity_id: str, start: str) -> dict: ...
    def search(self, q: str) -> list[dict]: ...
    def attribute(self, value_id: str) -> dict | None: ...


class V1Reader:
    """World-model reads through the v1 API (any client with `get`: a TestClient in process, or httpx)."""

    def __init__(self, client: Any, world_model_id: str | None = None) -> None:
        self.c = client
        wid = world_model_id or client.get("/v1/world-models").json()["data"][0]["id"]
        self.base = f"/v1/world-models/{wid}"
        self.calls: list[str] = []

    def _get(self, path: str, **params: Any) -> Any:
        self.calls.append(path + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else ""))
        r = self.c.get(self.base + path, params=params)
        return r.json().get("data") if r.status_code == 200 else None

    def construction(self, entity_id: str) -> dict:
        return self._get(f"/entities/{entity_id}/construction") or {}

    def links(self, entity_id: str) -> dict[str, dict]:
        """Every active relationship, with its transition and retrieval profile (paged): the entity's own and the market
        links its paths start from."""
        out: dict[str, dict] = {}
        cursor = None
        while True:
            params: dict[str, Any] = {"limit": 200, **({"cursor": cursor} if cursor else {})}
            self.calls.append("/relationships")
            r = self.c.get(self.base + "/relationships", params=params)
            if r.status_code != 200:
                return out
            body = r.json()
            out.update({x["id"]: x for x in body.get("data") or []})
            cursor = (body.get("meta") or {}).get("next_cursor")
            if not cursor:
                return out

    def trace(self, entity_id: str, start: str) -> dict:
        return self._get(f"/entities/{entity_id}/traces", **{"from": start, "through_totals": "true"}) or {}

    def search(self, q: str) -> list[dict]:
        """The model's names (graph mode), then passages (hybrid)."""
        return [*(self._get("/search", q=q[:500], mode="graph", limit=50) or []),
                *(self._get("/search", q=q[:500], mode="hybrid", limit=20) or [])]

    def attribute(self, value_id: str) -> dict | None:
        ent, _, key = value_id.partition(".")
        a = self._get(f"/entities/{ent}/attributes/{key}")
        if a is not None:
            a = {**a, "observations": self._get(f"/entities/{ent}/attributes/{key}/observations", limit=200) or []}
        return a


# -- cases ----------------------------------------------------------------------------------------------------------------
@dataclass
class Case:
    id: str
    category: str
    question: str
    fixture: dict = field(default_factory=dict)
    entity: str = "toyota"
    grading: dict = field(default_factory=dict)     # hidden from the responder

    def public(self) -> dict:
        """What the responder may see."""
        return {"id": self.id, "question": self.question, "fixture": self.fixture, "entity": self.entity}


def load_cases(path: Path, only: list[str] | None = None) -> list[Case]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    out = []
    for s in raw.get("seeds", []):
        if only and s["id"] not in only:
            continue
        out.append(Case(id=s["id"], category=str(s.get("category", "")), question=s["question"],
                        fixture=s.get("fixture") or {}, entity=s.get("entity", "toyota"), grading=s.get("grading") or {}))
    return out


# -- arithmetic on model objects -------------------------------------------------------------------------------------------
def eval_identity(ident: dict, levels: dict[str, float]) -> float | None:
    """An identity's target from its terms' levels (product, ratio, difference, weighted average)."""
    terms = ident.get("terms") or []
    if any(levels.get(t["value"]) is None for t in terms):
        return None
    v = {t["value"]: float(levels[t["value"]]) for t in terms}
    form, k = ident["form"], float(ident.get("coefficient") or 1.0)
    if form == "product":
        out = k
        for t in terms:
            out *= v[t["value"]]
        return out
    if form == "ratio":
        num, den = k, 1.0
        for t in terms:
            if t["role"] == "denominator":
                den *= v[t["value"]]
            else:
                num *= v[t["value"]]
        return None if den == 0 else num / den
    if form == "difference":
        return sum(v[t["value"]] * (1 if t["role"] == "total" else -1) for t in terms)
    if form == "weighted_average":
        return sum(v[t["value"]] * float(t.get("weight") or 0.0) for t in terms)
    return None


def _num(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@dataclass
class Answer:
    case_id: str
    retrieved_ids: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    calculations: list[dict] = field(default_factory=list)
    mechanisms: list[dict] = field(default_factory=list)
    unsized_steps: list[dict] = field(default_factory=list)
    states: dict[str, str] = field(default_factory=dict)
    timing: list[dict] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)

    def calc(self, key: str) -> dict | None:
        return next((c for c in self.calculations if c["key"] == key), None)

    def add_calc(self, **c: Any) -> None:
        if not self.calc(c["key"]):
            self.calculations.append(c)

    def note(self, s: str) -> None:
        if s not in self.notes:
            self.notes.append(s)

    def unsized(self, **s: Any) -> None:
        if not any(x.get("link") == s.get("link") and x.get("value") == s.get("value") for x in self.unsized_steps):
            self.unsized_steps.append(s)

    def mech(self, **m: Any) -> None:
        if not any(x["link"] == m["link"] for x in self.mechanisms):
            self.mechanisms.append(m)

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("case_id", "retrieved_ids", "sources", "calculations", "mechanisms",
                                               "unsized_steps", "states", "timing", "labels", "notes", "reads")}


def comp_parts(c: dict) -> list[str]:
    return [*c.get("member_attribute_ids", []), *([c["residual_attribute_id"]] if c.get("residual_attribute_id") else []),
            *([c["eliminations_attribute_id"]] if c.get("eliminations_attribute_id") else [])]


@dataclass
class Model:
    """One entity's construction in the responder's hands."""
    con: dict
    links: dict[str, dict]

    def __post_init__(self) -> None:
        self.idents = {x["target"]: x for x in self.con.get("identities") or []}
        self.sflows = {x["stock"]: x for x in self.con.get("stock_flows") or []}
        self.comps = self.con.get("compositions") or []
        self.attrs = {x["id"]: x for x in self.con.get("attributes") or []}
        self.reconciling_totals: dict[str, list[dict]] = defaultdict(list)
        self.reconciling_edges: set[tuple[str, str]] = set()
        driving_parts: dict[str, set[str]] = defaultdict(set)
        for c in self.comps:
            if c.get("role") == "driving":
                driving_parts[c["total_attribute_id"]] |= set(comp_parts(c))
            else:
                self.reconciling_totals[c["total_attribute_id"]].append(c)
        for c in self.comps:
            if c.get("role") != "driving":
                for p in comp_parts(c):
                    if p not in driving_parts[c["total_attribute_id"]]:
                        self.reconciling_edges.add((p, c["total_attribute_id"]))
        self.incoming: dict[str, list[dict]] = defaultdict(list)
        self.outgoing: dict[str, list[dict]] = defaultdict(list)
        for x in self.links.values():
            self.incoming[x["target_attribute_id"]].append(x)
            self.outgoing[x["source_attribute_id"]].append(x)

    def edge_kind(self, x: dict) -> str:
        """identity | stock_flow | view (a reconciling view: never summed) | slope."""
        if x.get("type") == "stock_flow":
            return "stock_flow"
        if x.get("type") == "identity" or (x.get("identity_id") and x["target_attribute_id"] in self.idents):
            return "identity"
        if (x["source_attribute_id"], x["target_attribute_id"]) in self.reconciling_edges:
            return "view"
        return "slope"

    @staticmethod
    def sign(x: dict) -> int:
        s = x.get("sign") or (x.get("transition") or {}).get("sign")
        return -1 if s in ("negative", "-") else 1


# -- the responder ------------------------------------------------------------------------------------------------------
class Responder:
    """Answers from the world model only: it never reads a case's grading."""

    def __init__(self, reader: Reader) -> None:
        self.r = reader
        self._m: dict[str, Model] = {}

    def model(self, entity: str) -> Model:
        if entity not in self._m:
            self._m[entity] = Model(self.r.construction(entity) or {}, self.r.links(entity))
        return self._m[entity]

    def answer(self, case: dict) -> Answer:
        fx = case.get("fixture") or {}
        ent = case.get("entity", "toyota")
        m = self.model(ent)
        a = Answer(case_id=case["id"])
        a.labels.append("controlled fixture: stipulated inputs, not a company disclosure, guidance or forecast" if fx
                        else "no fixture: the model's objects, its dated observations and its state")
        # retrieval: the question against the model's names, then every id the fixture names
        # (only the company's own names and the markets its links start from: other companies' hits are noise here)
        near = {x["source_attribute_id"] for x in m.links.values() if x["target_attribute_id"].startswith(ent + ".")}
        near |= {v.split(".")[0] for v in near}
        for h in self.r.search(case["question"]):
            ref = h.get("ref")
            if ref and (ref == ent or ref.startswith(ent + ".") or ref in near) and ref not in a.retrieved_ids:
                a.retrieved_ids.append(ref)
        for v in [*fx.get("outputs", []), *(fx.get("levels") or {}), *(fx.get("deltas") or {}), *(fx.get("shock") or {}),
                  *(fx.get("clocks") or {}), *(fx.get("hold") or []), *(fx.get("offsets") or {}), *(fx.get("slopes") or {}),
                  *[k for p in fx.get("periods") or [] for k in p.get("deltas", {})]]:
            if v not in a.retrieved_ids:
                a.retrieved_ids.append(v)
        if fx:
            self.solve(a, m, fx, "")
            for var in fx.get("variants") or []:
                merged = {**fx, **{k: v for k, v in var.items() if k != "label"}}
                for k in ("levels", "deltas", "clocks"):
                    if k in var and k in fx:
                        merged[k] = {**fx[k], **var[k]}
                self.solve(a, m, merged, f" [{var['label']}]")
        else:
            self._baseline(a, m)
        # mechanisms: traces from what changes
        starts = [*(fx.get("shock") or {}), *(fx.get("deltas") or {}), *(fx.get("clocks") or {})]
        for st in dict.fromkeys(starts):
            self._trace(a, m, self.r.trace(ent, st) or {}, fx)
        self._finish(a, m, fx)
        a.reads = list(getattr(self.r, "calls", []))
        return a

    # -- the delta engine ------------------------------------------------------------------------------------------------
    def solve(self, a: Answer, m: Model, fx: dict, sfx: str) -> None:
        self._clocks(a, m, fx, sfx)
        self._periods(a, m, fx, sfx)
        self._offsets(a, m, fx, sfx)
        if fx.get("deltas") or fx.get("shock"):
            self._propagate(a, m, fx, sfx)
        if fx.get("convert"):
            cv = fx["convert"]
            for c in [c for c in a.calculations if c["key"].endswith(sfx) and not c.get("converted") and c.get("result") is not None]:
                a.add_calc(key=c["key"] + " (converted)", rule="stated conversion", converted=True,
                           formula=f"result x {cv['factor']}", inputs={"amount": c["result"], **cv},
                           result=c["result"] * float(cv["factor"]), unit=cv.get("unit", ""), basis="fixture")

    def _propagate(self, a: Answer, m: Model, fx: dict, sfx: str) -> None:
        """Stipulated changes through the model, in dependency order: identities by their arithmetic, driving views and
        sized links by native slopes, reconciling views never summed. Unsized steps leave their target unknown."""
        lv = {k: float(v) for k, v in (fx.get("levels") or {}).items()}
        fixed = {k: float(v) for k, v in {**(fx.get("shock") or {}), **(fx.get("deltas") or {})}.items()}
        hold = set(fx.get("hold") or [])
        slopes = {k: float(v) for k, v in (fx.get("slopes") or {}).items()}
        outs = list(fx.get("outputs") or [])
        if not outs:
            return
        # the affected subgraph: reachable from the changes, and able to reach an output
        reach, frontier = set(fixed), list(fixed)
        while frontier:
            v = frontier.pop()
            if v in hold:
                continue
            for x in m.outgoing.get(v, []):
                t = x["target_attribute_id"]
                if m.edge_kind(x) not in ("stock_flow", "view") and t not in reach:
                    reach.add(t)
                    frontier.append(t)
        # an output total's reconciling views are solved too, so each can be checked against the driving one
        checked = {p for o in outs for c in m.reconciling_totals.get(o, []) for p in comp_parts(c)}
        anc, frontier = set(outs) | checked, [*outs, *checked]
        while frontier:
            v = frontier.pop()
            for x in m.incoming.get(v, []):
                s = x["source_attribute_id"]
                if m.edge_kind(x) not in ("stock_flow", "view") and s not in anc:
                    anc.add(s)
                    frontier.append(s)
        live = (reach & anc) | set(fixed)
        delta: dict[str, float] = dict(fixed)
        unknown: dict[str, list[str]] = {}
        done = set(fixed) | (hold & live)
        for h in sorted(hold & live):
            delta.setdefault(h, 0.0)
            a.states[h] = "held constant"
        # breadth-first distance from the changes: a loop is cut at the edge that returns to an earlier value
        dist, frontier = {v: 0 for v in fixed}, list(fixed)
        while frontier:
            v = frontier.pop(0)
            for x in m.outgoing.get(v, []):
                t = x["target_attribute_id"]
                if t in live and t not in dist and m.edge_kind(x) not in ("stock_flow", "view"):
                    dist[t] = dist[v] + 1
                    frontier.append(t)
        cut: set[str] = set()
        passes = 0
        while True:
            # each pass resolves a value, or cuts the stuck value's in-edges so it resolves on the next pass
            passes += 1
            assert passes <= 2 * len(live) + 2, "propagation did not converge"
            progressed = False
            for v in sorted(live - done, key=lambda z: (dist.get(z, 10**6), z)):
                ins = [x for x in m.incoming.get(v, []) if m.edge_kind(x) not in ("stock_flow", "view")
                       and x["source_attribute_id"] in live and x["id"] not in cut]
                if any(x["source_attribute_id"] not in done for x in ins):
                    continue
                done.add(v)
                progressed = True
                ident = m.idents.get(v)
                if ident is not None:
                    self._identity_delta(a, m, ident, lv, delta, unknown, sfx)
                    continue
                total, sized, gaps = 0.0, [], [x["id"] for x in m.incoming.get(v, []) if x["id"] in cut]
                for x in ins:
                    s = x["source_attribute_id"]
                    if s in unknown and s not in delta:
                        gaps.append(x["id"])
                        continue
                    if s not in delta:
                        continue              # resolved and unmoved (an identity none of whose terms changed)
                    slope = slopes.get(x["id"])
                    basis = "stipulated coefficient (fixture)"
                    if slope is None:
                        slope = (x.get("profile") or {}).get("native_slope")
                        basis = "model native slope"
                        if slope is not None and x.get("type") == "accounting":
                            slope, basis = float(m.sign(x)), "accounting (one for one, signed)"
                    if slope is None:
                        gaps.append(x["id"])
                        a.unsized(link=x["id"], source=s, target=v,
                                  why=f"uncalibrated: sign only ({'+' if m.sign(x) > 0 else '-'})", state=UNKNOWN)
                        a.states[x["id"]] = UNKNOWN
                        a.mech(link=x["id"], source=s, target=v, sized=False,
                               mechanism=(x.get("transition") or {}).get("mechanism", ""))
                        continue
                    d = slope * delta[s]
                    total += d
                    sized.append({"link": x["id"], "slope": slope, "basis": basis, "change_in": delta[s], "change": d})
                    a.states[x["id"]] = "measured zero" if slope == 0 else "sized"
                    a.mech(link=x["id"], source=s, target=v, sized=True, native_slope=slope,
                           mechanism=(x.get("transition") or {}).get("mechanism", ""))
                if sized:
                    delta[v] = total
                    if gaps:
                        unknown[v] = gaps
                    a.add_calc(key=f"delta {v}{sfx}", rule="sum of sized links into the value", formula="sum of slope x change",
                               inputs=sized, result=total, partial_excludes=gaps or None, links=[s["link"] for s in sized],
                               unit=m.attrs.get(v, {}).get("unit"), basis="fixture through the model's links")
                elif gaps:
                    unknown[v] = gaps
            if not progressed:
                stuck = sorted(live - done, key=lambda z: (dist.get(z, 10**6), z))
                if not stuck:
                    break
                v = stuck[0]
                for x in m.incoming.get(v, []):
                    if x["source_attribute_id"] in live - done and m.edge_kind(x) not in ("stock_flow", "view"):
                        cut.add(x["id"])
                        a.unsized(link=x["id"], source=x["source_attribute_id"], target=v,
                                  why="a feedback loop within the period: its second round is not solved", state=UNKNOWN)
                        a.states.setdefault(x["id"], UNKNOWN)
        for o in outs:
            if o in unknown and o not in delta:
                a.add_calc(key=f"delta {o}{sfx}", rule="no sized route", result=None, state=UNKNOWN, excludes=unknown[o],
                           unit=m.attrs.get(o, {}).get("unit"), basis="the model represents the route but cannot size it")
                a.note(f"{o}: represented but unsized; the missing coefficients are listed, and the change is unknown, not zero")
            elif o in unknown:
                a.note(f"{o}: the sized part only; excluded (unsized) steps are listed, never counted as zero")
        # reconciling views: checked, never added
        for t, cs in m.reconciling_totals.items():
            if t not in delta:
                continue
            for c in cs:
                moved = {p: delta[p] for p in comp_parts(c) if p in delta}
                if moved:
                    a.add_calc(key=f"check {c['id']}{sfx}", rule=f"reconciling view {c['id']} (checked, never added)",
                               inputs=moved, result=sum(moved.values()), basis="fixture through the model's links")
        priced = [x["target_attribute_id"] for v in [*outs, *fixed] for x in m.outgoing.get(v, [])
                  if m.attrs.get(x["target_attribute_id"], {}).get("concept") == "asset_price"]
        if priced:
            a.note(f"{', '.join(sorted(set(priced)))}: linked only by a model coefficient, not a valuation model; no return "
                   "is calculated from the earnings change")

    def _identity_delta(self, a: Answer, m: Model, ident: dict, lv: dict, delta: dict, unknown: dict, sfx: str) -> None:
        v = ident["target"]
        terms = [t["value"] for t in ident.get("terms") or []]
        miss = [t for t in terms if t in unknown and t not in delta]
        if miss:
            unknown[v] = miss
            return
        if not any(delta.get(t) for t in terms):
            return
        denoms = {t["value"] for t in ident.get("terms") or [] if t["role"] == "denominator"}
        lv0, need = {}, []
        for t in terms:
            if t in lv:
                lv0[t] = lv[t]
            elif t in delta and t not in denoms and (ident["form"] in ("difference", "weighted_average")
                                                     or sum(1 for x in terms if delta.get(x)) == 1):
                lv0[t] = 0.0          # the change is linear in this term: its base level drops out
            else:
                need.append(t)
        if need:
            unknown[v] = need
            for t in need:
                a.unsized(value=t, why=f"{ident['id']} needs the level of {t}", state=UNKNOWN)
            return
        lv1 = {t: lv0[t] + delta.get(t, 0.0) for t in terms}
        y0, y1 = eval_identity(ident, lv0), eval_identity(ident, lv1)
        if y0 is None or y1 is None:
            unknown[v] = terms
            return
        delta[v] = y1 - y0
        parts, cur = [], dict(lv0)
        if ident["form"] in ("product", "ratio") and sum(1 for t in terms if delta.get(t)) > 1:
            for t in terms:
                if not delta.get(t):
                    continue
                before = eval_identity(ident, cur)
                cur[t] = lv1[t]
                after = eval_identity(ident, cur)
                parts.append({"term": t, "change": after - before})
                a.add_calc(key=f"part {v} {t}{sfx}", rule=f"sequential decomposition of {ident['id']} (terms in the identity's order)",
                           result=after - before, basis="fixture")
        a.add_calc(key=f"delta {v}{sfx}", rule=f"identity {ident['id']}", formula=ident.get("formula"),
                   inputs={"before": lv0, "after": lv1}, parts=parts or None, result=y1 - y0, level_before=y0, level_after=y1,
                   unit_check=ident.get("unit_check", ""), unit=m.attrs.get(v, {}).get("unit"),
                   links=[t.get("interaction_id") for t in ident.get("terms") or []], basis="fixture")

    def _clocks(self, a: Answer, m: Model, fx: dict, sfx: str) -> None:
        """A rate shock reprices only the share of a balance that resets, for the time it is active: assets and funding
        run on their own clocks."""
        clocks = fx.get("clocks") or {}
        if not clocks:
            return
        lv = {k: float(v) for k, v in (fx.get("levels") or {}).items()}
        for out in fx.get("outputs", []):
            ident = m.idents.get(out)
            if ident is None or ident["form"] != "difference":
                continue
            total, parts = 0.0, []
            for t in ident["terms"]:
                sub = m.idents.get(t["value"])
                if sub is None or sub["form"] != "product":
                    continue
                rate = next((x["value"] for x in sub["terms"] if x["value"] in clocks), None)
                bal = next((x["value"] for x in sub["terms"] if x["value"] != rate), None)
                if rate is None or bal not in lv:
                    continue
                ck = clocks[rate]
                d_rate = float(ck["shock"]) * float(ck.get("reset_share", 1.0)) * float(ck.get("time", 1.0))
                d = float(sub.get("coefficient") or 1.0) * lv[bal] * d_rate
                a.add_calc(key=f"delta {t['value']}{sfx}", rule=f"identity {sub['id']} with a repricing clock",
                           formula="coefficient x balance x shock x reset share x time active",
                           inputs={"balance": lv[bal], "shock": ck["shock"], "reset_share": ck.get("reset_share", 1.0),
                                   "time": ck.get("time", 1.0), "coefficient": sub.get("coefficient")},
                           result=d, links=[x.get("interaction_id") for x in sub["terms"]], basis="fixture")
                signed = d if t["role"] == "total" else -d
                parts.append({"term": t["value"], "change": signed})
                total += signed
            if parts:
                a.add_calc(key=f"delta {out}{sfx}", rule=f"identity {ident['id']}", formula=ident.get("formula"), parts=parts,
                           result=total, links=[x.get("interaction_id") for x in ident["terms"]], basis="fixture")
                a.note("only the share of each balance that resets reprices, for the time it is active; assets and funding "
                       "run on separate clocks")

    def _periods(self, a: Answer, m: Model, fx: dict, sfx: str) -> None:
        """Stock-flow periods: each period's missing flow or stock change from the mass balance, then the totals."""
        periods = fx.get("periods") or []
        if not periods:
            return
        for out in fx.get("outputs", []):
            sf = m.sflows.get(out)
            if sf is None:
                continue
            cum: dict[str, float] = defaultdict(float)
            flows = sf.get("flows") or []
            ins = [f["value"] for f in flows if f["role"] == "inflow"]
            outs_ = [f["value"] for f in flows if f["role"] == "outflow"]
            ids = [f.get("interaction_id") for f in flows]
            for v in ins:                     # what supplies the stock: the operating route the units come from
                for x in m.incoming.get(v, []):
                    a.mech(link=x["id"], source=x["source_attribute_id"], target=v,
                           sized=(x.get("profile") or {}).get("native_slope") is not None,
                           mechanism=(x.get("transition") or {}).get("mechanism", ""), via="feeds a flow")
            for p in periods:
                d = {k: float(v) for k, v in p.get("deltas", {}).items()}
                unknown = [v for v in [*ins, *outs_, out] if v not in d]
                if len(unknown) != 1:
                    a.note(f"{p['label']}: the mass balance needs all but one of its terms")
                    continue
                u = unknown[0]
                net_in = sum(d.get(v, 0.0) for v in ins if v != u) - sum(d.get(v, 0.0) for v in outs_ if v != u)
                if u == out:
                    val = net_in
                elif u in ins:
                    val = d[out] - net_in
                else:
                    val = net_in - d[out]
                d[u] = val
                a.add_calc(key=f"delta {u} [{p['label']}]{sfx}", rule=f"stock-flow {sf['id']} (mass balance)",
                           formula="change in stock = inflows - outflows", inputs={k: v for k, v in d.items() if k != u},
                           result=val, links=ids, basis="fixture")
                for k, v in d.items():
                    cum[k] += v
            for k, v in cum.items():
                a.add_calc(key=f"cumulative delta {k}{sfx}", rule="sum over the periods", result=v, links=ids, basis="fixture")
            if cum:
                chk = sum(cum.get(v, 0.0) for v in ins) - sum(cum.get(v, 0.0) for v in outs_) - cum.get(out, 0.0)
                a.add_calc(key=f"balance check {sf['id']}{sfx}", rule="inflows - outflows - change in stock over all periods",
                           result=chk, basis="fixture")
                a.note("units only: no profit follows without contribution per unit and recovery costs; a later rebuild of "
                       "the stock is a further period")

    def _offsets(self, a: Answer, m: Model, fx: dict, sfx: str) -> None:
        for lid, o in (fx.get("offsets") or {}).items():
            x = m.links.get(lid)
            if x is None:
                a.note(f"{lid}: no such link in the model")
                continue
            prof = x.get("profile") or {}
            gross, hedge, pt = float(o["gross"]), float(o.get("hedge", 0.0)), float(o.get("pass_through", 0.0))
            exposed = gross * (1 - hedge)
            recovered = exposed * pt
            sg = m.sign(x)
            for k, v in (("gross", gross * sg), ("hedge offset", gross - exposed), ("exposed", exposed),
                         ("recovery", recovered)):
                a.add_calc(key=f"{k} {lid}{sfx}", rule="gross exposure, hedge cover, pass-through of the remainder",
                           result=v, links=[lid], basis="fixture")
            a.add_calc(key=f"net {lid}{sfx}", rule="the link's sign x (gross x (1 - hedge) x (1 - pass-through))",
                       formula="exposed = gross x (1 - hedge); recovery = exposed x pass-through; net = sign x (exposed - recovery)",
                       inputs={"gross": gross, "hedge": hedge, "pass_through": pt, "link_sign": sg},
                       result=sg * (exposed - recovered), links=[lid],
                       unit=m.attrs.get(x["target_attribute_id"], {}).get("unit"),
                       basis=f"fixture; the model states hedge '{prof.get('hedge', 'unknown')}' and pass-through "
                             f"'{prof.get('pass_through', 'unknown')}' on the link")
            a.mech(link=lid, source=x["source_attribute_id"], target=x["target_attribute_id"], sized=False,
                   mechanism=(x.get("transition") or {}).get("mechanism", ""))
            a.note("recovery applies to the exposure after hedges, not to the gross; a hedge can delay rather than remove "
                   "the exposure, and recognition follows purchasing, inventory and price implementation")

    # -- mechanisms, baselines and the record --------------------------------------------------------------------------
    def _trace(self, a: Answer, m: Model, tr: dict, fx: dict) -> None:
        hold = set(fx.get("hold") or [])
        for r in tr.get("routes") or []:
            for s in r.get("steps") or []:
                lid = s.get("relationship_id")
                x = m.links.get(lid) or {}
                sized = s.get("calibration") == "calibrated"
                if lid not in a.states:
                    if s.get("target_attribute_id") in hold:
                        a.states[lid] = "held constant"
                    elif sized:
                        a.states[lid] = "measured zero" if (x.get("profile") or {}).get("native_slope") == 0 else "sized"
                    else:
                        a.states[lid] = UNKNOWN
                if a.states[lid] in ("held constant", UNKNOWN):
                    a.unsized(link=lid, source=s.get("source_attribute_id"), target=s.get("target_attribute_id"),
                              why="held constant by the fixture" if a.states[lid] == "held constant" else "uncalibrated: sign only",
                              state=a.states[lid])
                a.mech(link=lid, source=s.get("source_attribute_id"), target=s.get("target_attribute_id"), sized=sized,
                       mechanism=(x.get("transition") or {}).get("mechanism", ""), via="trace")

    def _baseline(self, a: Answer, m: Model) -> None:
        """No fixture: each total's dated observations apart from the model's state; each view checked per period."""
        def when(o: dict) -> str:
            """The period the value is of: when the fact occurred (a reported figure's period end), else its valid time."""
            return str(o.get("occurred_at") or o.get("valid_at") or o.get("observed_at") or "")[:10]

        totals = sorted({c["total_attribute_id"] for c in m.comps if c.get("additive")})
        for t in totals:
            cs = [c for c in m.comps if c["total_attribute_id"] == t]
            at = self.r.attribute(t) or {}
            obs = at.get("observations") or []
            state = (at.get("level") or {}).get("mean")
            a.add_calc(key=f"state {t}", rule="model state (posterior mean)", result=state, unit=at.get("unit"), basis="model state")
            by_period = {when(o): _num(o.get("value")) for o in obs if _num(o.get("value")) is not None}
            for w, val in sorted(by_period.items()):
                a.add_calc(key=f"observed {t} @{w}", rule="dated observation", result=val, unit=at.get("unit"),
                           basis=f"observation dated {w}")
                if state is not None and abs(state - val) > 1e-9:
                    a.note(f"{t}: the model state ({state:.6g}) is not the dated actual ({val:.6g} at {w}); the actual is "
                           "reported as observed and the state as model state")
            if not obs:
                a.note(f"{t}: no dated observation is loaded; the model state is not an actual")
            for c in cs:
                parts = comp_parts(c)
                obs_p = {p: {when(o): _num(o.get("value")) for o in (self.r.attribute(p) or {}).get("observations") or []}
                         for p in parts}
                signs = {p: Model.sign(next((x for x in m.incoming.get(t, []) if x["source_attribute_id"] == p), {}))
                         for p in parts}
                periods = set.intersection(*[set(v) for v in obs_p.values()]) if parts and all(obs_p.values()) else set()
                for w in sorted(periods):
                    vals = {p: obs_p[p][w] for p in parts}
                    if any(v is None for v in vals.values()):
                        continue
                    s = sum(signs[p] * v for p, v in vals.items())
                    a.add_calc(key=f"view {c['id']} @{w}", rule=f"composition {c['id']} ({c.get('role')})",
                               formula="sum of parts, each signed by its accounting link", inputs=vals, result=s,
                               difference_to_total=(by_period[w] - s) if by_period.get(w) is not None else None,
                               basis=f"dated observations at {w}")
                if not periods:
                    a.note(f"{c['id']}: no period with every part observed; the view is not checked")
                a.mech(link=c["id"], source="parts", target=t, sized=True,
                       mechanism=f"{c.get('role')} view of {t}: {c.get('basis', '')}")
                if c["id"] not in a.retrieved_ids:
                    a.retrieved_ids.append(c["id"])
            if t not in a.retrieved_ids:
                a.retrieved_ids.append(t)
            if len(cs) > 1:
                a.note(f"{t}: one driving view feeds the total; reconciling views are checked against it, never added to it")

    def _finish(self, a: Answer, m: Model, fx: dict) -> None:
        used = {mm["link"] for mm in a.mechanisms} | {lid for c in a.calculations for lid in c.get("links") or [] if lid}
        for p in m.con.get("paths") or []:
            if any(s.get("relationship_id") in used for s in p.get("steps") or []) and p["id"] not in a.retrieved_ids:
                a.retrieved_ids.append(p["id"])
        for lid in sorted(x for x in used if x in m.links):
            tr = m.links[lid].get("transition") or {}
            for s in (tr.get("evidence") or {}).get("sources") or []:
                if s not in a.sources:
                    a.sources.append(s)
            if tr.get("timing"):
                a.timing.append({"link": lid, **tr["timing"]})
            for v in (lid, m.links[lid]["source_attribute_id"], m.links[lid]["target_attribute_id"]):
                if v not in a.retrieved_ids:
                    a.retrieved_ids.append(v)
        # the views a used link reconciles into: the composition is evidence too
        edges = {(m.links[lid]["source_attribute_id"], m.links[lid]["target_attribute_id"]) for lid in used if lid in m.links}
        for c in m.comps:
            if any((p, c["total_attribute_id"]) in edges for p in comp_parts(c)) and c["id"] not in a.retrieved_ids:
                a.retrieved_ids.append(c["id"])
        for h in fx.get("hold") or []:
            a.states.setdefault(h, "held constant")
        for lid, x in m.links.items():
            if x["source_attribute_id"] in (fx.get("shock") or {}) and lid not in a.states:
                a.states[lid] = "not applicable"
        if a.unsized_steps:
            a.note("unsized steps are listed with their state; none is counted as zero")


# -- the grader -----------------------------------------------------------------------------------------------------------
def _outcome(hit: int, need: int) -> str:
    if need == 0:
        return "Not tested"
    return "Pass" if hit == need else ("Partial" if hit > 0 else "Fail")


def grade(answer: Answer, grading: dict) -> dict:
    """Four outcomes from the hidden spec, with reasons; every critical failure is listed apart."""
    out: dict[str, Any] = {"case_id": answer.case_id, "reasons": {}, "critical": []}
    # evidence: model object ids (source locations in a client's workbook are not world-model objects: listed apart)
    ev = grading.get("evidence") or {}
    ids = ev.get("ids") or []
    got = [i for i in ids if i in answer.retrieved_ids]
    out["evidence"] = _outcome(len(got), len(ids))
    out["reasons"]["evidence"] = {"required": ids, "missing": [i for i in ids if i not in got],
                                  "source_locations": ev.get("locations", []),
                                  "source_locations_status": ("Not tested: workbook cells are bound in the local provenance "
                                                              "records, not world-model objects") if ev.get("locations") else ""}
    # mechanism: required links or objects, required states; forbidden moves fail it and are critical
    mech = grading.get("mechanism") or {}
    seen = {mm["link"] for mm in answer.mechanisms} | set(answer.retrieved_ids)
    req = list(mech.get("required", []))
    hit = [r for r in req if r in seen]
    st_req = mech.get("states") or {}
    st_hit = [k for k, v in st_req.items() if answer.states.get(k) == v]
    out["mechanism"] = _outcome(len(hit) + len(st_hit), len(req) + len(st_req))
    bad = []
    for f in mech.get("forbidden", []):
        kind = f.get("kind")
        c = answer.calc(f["key"]) if f.get("key") else None
        if kind == "sized_link" and any(mm["link"] == f["link"] and mm.get("sized") for mm in answer.mechanisms):
            bad.append(f)
        elif kind == "zero_for_unsized" and any(s.get("state") == "measured zero" for s in answer.unsized_steps):
            bad.append(f)
        elif kind == "calculation_key" and c is not None and c.get("result") is not None:
            bad.append(f)
        elif kind == "numeric_zero" and c is not None and c.get("result") == 0:
            bad.append(f)
    if bad:
        out["mechanism"] = "Fail"
        out["critical"] += [{"dimension": "mechanism", **b} for b in bad]
    out["reasons"]["mechanism"] = {"required": req, "missing": [r for r in req if r not in hit], "states_required": st_req,
                                   "states_wrong": {k: answer.states.get(k) for k in st_req if k not in st_hit},
                                   "forbidden_hit": bad}
    # calculation: each expected key within its tolerance, or its expected state
    calcs = grading.get("calculation") or []
    ok, why = 0, []
    for c in calcs:
        mine = answer.calc(c["key"])
        if "expected_state" in c:
            good = mine is not None and mine.get("result") is None and mine.get("state") == c["expected_state"]
            ok += good
            why.append({"key": c["key"], "status": "ok" if good else "wrong",
                        "got": None if mine is None else [mine.get("state"), mine.get("result")], "expected": c["expected_state"]})
            if not good and mine is not None and mine.get("result") == 0:
                out["critical"].append({"dimension": "calculation", "key": c["key"], "kind": "a numeric zero for an unknown"})
            continue
        if mine is None or mine.get("result") is None:
            why.append({"key": c["key"], "status": "missing", "expected": c["expected"]})
            continue
        got_v, exp = float(mine["result"]), float(c["expected"])
        if abs(got_v - exp) <= float(c.get("tolerance", 1e-6)):
            ok += 1
            why.append({"key": c["key"], "status": "ok", "got": got_v, "expected": exp})
        else:
            why.append({"key": c["key"], "status": "wrong", "got": got_v, "expected": exp})
            if got_v * exp < 0:
                out["critical"].append({"dimension": "calculation", "key": c["key"], "kind": "wrong sign"})
            elif c.get("critical"):
                out["critical"].append({"dimension": "calculation", "key": c["key"], "kind": c["critical"]})
    out["calculation"] = _outcome(ok, len(calcs))
    out["reasons"]["calculation"] = why
    # timing and communication
    tc = grading.get("timing") or {}
    checks = []
    if tc.get("fixture_label"):
        checks.append(("the fixture is labelled as stipulated, not a disclosure",
                       any("controlled fixture" in x for x in answer.labels)))
    if tc.get("timing_entries"):
        checks.append(("onset and recognition of the links used", bool(answer.timing)))
    if tc.get("unsized_listed"):
        checks.append(("unsized steps listed, each with a state", bool(answer.unsized_steps)
                       and all(s.get("state") in STATES for s in answer.unsized_steps)))
    for n in tc.get("notes_contain", []):
        checks.append((f"states: {n}", any(n.lower() in x.lower() for x in answer.notes)))
    out["timing"] = _outcome(sum(1 for _c, v in checks if v), len(checks))
    out["reasons"]["timing"] = [{"check": c, "ok": v} for c, v in checks]
    return out


def run(cases: list[Case], reader: Reader) -> list[dict]:
    resp = Responder(reader)
    out = []
    for case in cases:
        if hasattr(reader, "calls"):
            reader.calls.clear()
        ans = resp.answer(case.public())
        out.append({"case": case.id, "category": case.category, "question": case.question, "answer": ans.as_dict(),
                    "grade": grade(ans, case.grading)})
    return out


def summary_line(r: dict) -> str:
    g = r["grade"]
    crit = f"; CRITICAL {len(g['critical'])}" if g["critical"] else ""
    return (f"{r['case']}: evidence {g['evidence']}, mechanism {g['mechanism']}, calculation {g['calculation']}, "
            f"timing {g['timing']}{crit}")


def dump(results: list[dict], path: Path) -> None:
    Path(path).write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str))
