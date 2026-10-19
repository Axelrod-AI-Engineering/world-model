"""Business construction (Oct 17): what turns a company from "a macro driver moves its profit" into the mechanisms
that decide the outcome, so a reader (or an agent) can follow a change through the exposed business, the actor's
response, the operating outcome, and the accounts, and see where the model stops.

Three kinds of object, all versioned in the causal graph:

- **Transition** (on an interaction): what the link means as a business step. The mechanism and who acts; the
  condition it needs and the observable that proves it; the observable's definition, units, frequency, and proof
  limits; onset, build-up, persistence, and when the accounts recognize it; evidence for existence, direction,
  magnitude, and timing, kept apart because their support differs; the breaker that stops, caps, delays, or reverses
  it; the next state; and what is still unresolved. Unknowns stay "unknown", never a guess.
- **NamedPath**: a readable, connected path of interactions from a starting change to a named financial endpoint.
  Steps run in order; steps that share a `branch` are parallel responses to the same state (a shared driver's effects
  are branches, not a false sequence).
- **Composition**: one view of a business split into parts (reporting segments, regions, customer versus production
  location, products, investment assets, ...), on one accounting basis and unit, reconciled to its total with a
  residual and eliminations. Views of the same business overlap: they are never added to each other.

Two properties of an interaction say how it computes:

- `calibration`: "calibrated" (its effect size is estimated and it propagates) or "uncalibrated" (the mechanism, its
  direction, and its conditions are represented, but its size is not known: it carries no numbers, so it adds nothing
  to a simulation and a forecast that depends on it says so). Missing calibration does not delete a mechanism and does
  not mean zero.
- `edge_type` "accounting": an accounting relationship (a part adds to its total), with a fixed weight that learning
  never refits, so statistics cannot flip the sign of an identity.

Oct 18, identities that are not sums (the bank build's limits, docs/construction/jpmorgan.md):

- **Identity**: a product (NII = balance x rate), a ratio (CET1 ratio = CET1 / RWA), or a difference (NII ex Markets =
  NII - Markets NII). Its links (`edge_type` "identity") carry weights derived from the values' levels and scales
  (`identity_weights`), fixed like accounting links.
- **StockFlow**: a stock accumulating flows per period (capital += net income - distributions). Its links (`edge_type`
  "stock_flow") have derived weights and an accumulating kernel (model/temporal.py), so the stock integrates the flow.
- **Matrix**: two additive views of one total (segments x lines) as one structure; only the driving view links to the
  total, the cells link to both views' parts, and the passive view reconciles without driving.
- **ResponseState** (`state:` on a link): different sizes for rises and falls, a threshold that stops the response, a
  sign that flips with a value's level; compiled to piecewise moderators.

`validate_construction` checks the structure: every path step resolves to an interaction, consecutive steps meet,
branches share their source, compositions name real values with the right links, and no value is a part of two
views that would be added together; identities, stock-flows and matrices have their links. `reconcile` checks the
numbers (Oct 18): each additive composition's parts add to its total within 0.5% at the model's levels, or at given
levels (a baseline bundle's observes, `bundle_levels`); `reconcile_identities` the identities, `reconcile_matrices` the
cells, `reconcile_stock_flows` each roll-forward between dated baseline levels (`bundle_series`).
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

Support = Literal["documented", "public_not_supplied", "guidance", "broker", "peer", "model", "assumption", "inferred",
                  "unknown"]
# documented: the company's own disclosure, in the supplied material; public_not_supplied (Oct 18): the company
# discloses it publicly, but not in the supplied material (so it cannot be cited from it); guidance: management's forward statement; broker: an attributed research
# interpretation; peer (Oct 18): transferred from a named comparable company's disclosure; model: a workbook formula or dependency that was inspected; assumption: the builder's, stated;
# inferred: follows from other represented facts; unknown: not established


class Observable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    definition: str = ""
    units: str = ""
    frequency: str = ""                  # e.g. "monthly", "quarterly results", "event"
    proof_limits: str = ""               # what the observable cannot show


class Timing(BaseModel):
    """When the link acts. Each part is a phrase ("1-2 quarters", "at renewal") or "unknown"."""

    model_config = ConfigDict(extra="forbid")

    onset: str = "unknown"
    build: str = "unknown"
    persistence: str = "unknown"
    recognition: str = "unknown"         # when the accounts show it
    # Oct 18: a calendar or administered date the link acts on ("mortgage rates reset on 1 January", "at the annual
    # renewal"). Recorded and exported; the engine's kernel counts days from the change, so it does not schedule it
    calendar: str = ""


class EvidenceBasis(BaseModel):
    """What supports each claim of the link, separately: that it exists, its sign, its size, and its timing."""

    model_config = ConfigDict(extra="forbid")

    existence: Support = "unknown"
    direction: Support = "unknown"
    magnitude: Support = "unknown"
    timing: Support = "unknown"
    sources: list[str] = []              # source ids; the bindings (file, page, cell) stay with the client's data


InputStatus = Literal["found_connected", "found_not_connected", "found_proxy", "not_yet_reviewed",
                      "disclosed_not_supplied", "not_disclosed_in_reviewed_sources"]
# found_connected: the input is in the supplied material and bound to the model (a value, an observation, a citation);
# found_not_connected: it is in the material but not yet bound; found_proxy (Oct 18): only a sector or peer figure was
# found (its source in found_in, what it stands in for in the note), not the company's own; disclosed_not_supplied
# (Oct 18): the supplied material was searched and lacks it, but the company discloses it publicly (say where in the
# note); not_yet_reviewed: the material that would hold it has
# not been searched; not_disclosed_in_reviewed_sources: the supplied material was searched and does not disclose it


class InputNeed(BaseModel):
    """An input a transition needs, and what is known about it: whether the supplied material was searched for it, and
    where it was found. "Missing" is never declared before the search."""

    model_config = ConfigDict(extra="forbid")

    input: str
    status: InputStatus = "not_yet_reviewed"
    searched: list[str] = []             # what was searched: source ids, or "corpus: <query>"
    found_in: list[str] = []             # source ids where it was found
    note: str = ""

    @model_validator(mode="after")
    def _evidence_for_status(self) -> InputNeed:
        if self.status in ("not_disclosed_in_reviewed_sources", "disclosed_not_supplied") and not self.searched:
            raise ValueError(f"{self.input!r}: '{self.status}' needs the sources that were searched")
        if self.status.startswith("found") and not self.found_in:
            raise ValueError(f"{self.input!r}: '{self.status}' needs the sources it was found in")
        return self


class Transition(BaseModel):
    """One link as a business step (the seven parts of "show each transition inside its path")."""

    model_config = ConfigDict(extra="forbid")

    mechanism: str                       # 1. what happens, and its direction in words
    sign: Literal["+", "-"] | None = None    # the direction, needed when the link is uncalibrated
    actor: str = ""                      # 1. who decides or responds
    business_unit: str = ""              # 1. the exposed unit
    geography: str = ""
    currency: str = ""
    condition: str = ""                  # 2. what must hold for the link to act
    condition_observable: str = ""       # 2. the observable that proves the condition
    observable: Observable | None = None # 3. the observable of the link's own outcome
    timing: Timing = Timing()            # 4.
    evidence: EvidenceBasis = EvidenceBasis()   # 5.
    breaker: str = ""                    # 6. what stops, caps, delays, or reverses it
    breaker_threshold: str = ""          # 6. only when supported
    next_state: str = ""                 # 7. the next operating state or financial output
    unresolved: list[InputNeed] = []     # 7. inputs still missing, each with its search status
    # Oct 18 (retrieval fields): what offsets the exposure before it reaches the accounts; "" = not stated (unknown)
    hedge: str = ""                      # hedging that delays or removes part of the effect
    pass_through: str = ""               # the share passed on to customers or suppliers, when stated

    @field_validator("unresolved", mode="before")
    @classmethod
    def _plain_names(cls, v: Any) -> Any:
        """A bare name is an input not yet reviewed."""
        return [{"input": x} if isinstance(x, str) else x for x in v]


class Asymmetry(BaseModel):
    """Different sizes when a value stands above or below a level (Oct 18): a deposit beta in hikes versus cuts. Each size
    is an effect {mu, sigma} in sd/sd; `value` defaults to the link's source and `at` (native units) to the value's
    construction level, so "rises" and "falls" are moves of the source from where it was built."""

    model_config = ConfigDict(extra="forbid")

    rises: dict[str, float]              # the effect while the value is above `at`
    falls: dict[str, float]              # the effect while it is below
    value: str | None = None
    at: float | None = None


class Threshold(BaseModel):
    """A response that acts only while a value is above (or below) a level, native units (Oct 18): buybacks above a
    capital requirement."""

    model_config = ConfigDict(extra="forbid")

    value: str
    above: float | None = None
    below: float | None = None

    @model_validator(mode="after")
    def _one_side(self) -> Threshold:
        if (self.above is None) == (self.below is None):
            raise ValueError(f"threshold on {self.value}: give exactly one of `above` and `below`")
        return self


class SignFlip(BaseModel):
    """A response whose sign follows which side of a level a value is on, native units (Oct 18): reinvestment adds to
    income while new yields are above book yields and subtracts below. The effect's own sign applies on `positive`."""

    model_config = ConfigDict(extra="forbid")

    value: str
    at: float
    positive: Literal["above", "below"] = "above"


class ResponseState(BaseModel):
    """State-dependent responses of one link, written in construction YAML (`state:` on an interaction). Each compiles
    to a piecewise moderator of the interaction model (model/interaction.ParameterBinding, form "piecewise": the full
    effect on one side of the moderator's level, gamma x the effect on the other): an asymmetry's gamma is falls / rises,
    a threshold's is 0, a sign flip's is -1. Levels are native and convert to the moderator's standard units at its
    construction level."""

    model_config = ConfigDict(extra="forbid")

    asymmetry: Asymmetry | None = None
    threshold: Threshold | None = None
    sign_flip: SignFlip | None = None


class PathStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: str
    branch: str | None = None            # parallel steps share a branch label and a source


class NamedPath(BaseModel):
    """A connected path from a starting change to a named financial endpoint."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    entity_id: str                       # the company the path explains
    trigger: str                         # the starting state or change, in words
    steps: list[PathStep]
    endpoint: str                        # the financial endpoint (a subentity id)
    description: str = ""
    active_when: str = ""                # Oct 18: a dormant or conditional path's condition ("once the stake is zero")


class Composition(BaseModel):
    """One view of a business split into parts that add (by accounting links) to a total, on one basis."""

    model_config = ConfigDict(extra="forbid")

    id: str
    entity_id: str
    view: str                            # reporting_segments | regions | customer_location | production_location | ...
    basis: str                           # the accounting basis and definition, e.g. "segment operating income (IFRS)"
    unit: str
    period: str = ""                     # e.g. "fiscal year ending March"
    total: str                           # subentity id of the total
    members: list[str]                   # subentity ids of the parts
    residual: str | None = None          # what the parts leave out (other businesses, corporate)
    eliminations: str | None = None      # intersegment eliminations
    additive: bool = True                # False for a view whose parts overlap (e.g. product lines of one segment)
    # Oct 18: True for the one view that carries changes into the total (its parts' accounting links); False for a
    # reconciling view, observed and reconciled against the total but never propagating into it (no quantified links)
    drives: bool = True
    note: str = ""


IdentityForm = Literal["product", "ratio", "difference", "weighted_average"]


def _dupes(xs: list[str]) -> list[str]:
    return sorted({x for x in xs if xs.count(x) > 1})


class Identity(BaseModel):
    """An exact relationship that is not "a part adds to its total" (Oct 18): a product (NII = balance x rate, revenue =
    units x price), a ratio (CET1 ratio = CET1 / RWA, NIM = NII / earning assets), or a difference (NII ex Markets = NII
    - Markets NII). Each term reaches the target by an `identity` link whose weight is derived from the values' levels
    and scales, never guessed (`identity_weights`)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    entity_id: str
    target: str                          # the value the identity defines
    form: IdentityForm
    factors: list[str] = []              # product: target = coefficient x factor_1 x factor_2 ...
    numerator: list[str] = []            # ratio: target = coefficient x (numerator product) / (denominator product)
    denominator: list[str] = []
    of: str | None = None                # difference: target = of - minus_1 - minus_2 ...
    minus: list[str] = []
    weights: dict[str, float] = {}       # weighted_average: target = sum w_i x term_i, stated weights summing to 1
    coefficient: float = 1.0             # product and ratio: a unit conversion (0.01 for a rate in %, 4 to annualize)
    unit_check: str = ""                 # the unit algebra in words: "USD bn = USD bn x % x 0.01"
    basis: str = ""
    period: str = ""
    note: str = ""

    @model_validator(mode="after")
    def _form_fields(self) -> Identity:
        used = {"product": {"factors"}, "ratio": {"numerator", "denominator"}, "difference": {"of", "minus"},
                "weighted_average": {"weights"}}[self.form]
        stray = [f for f in ("factors", "numerator", "denominator", "of", "minus", "weights")
                 if f not in used and getattr(self, f)]
        if stray:
            raise ValueError(f"identity {self.id}: a {self.form} has no {', '.join(stray)}")
        if self.form == "product" and len(self.factors) < 2:
            raise ValueError(f"identity {self.id}: a product needs at least two factors")
        if self.form == "ratio" and not (self.numerator and self.denominator):
            raise ValueError(f"identity {self.id}: a ratio needs a numerator and a denominator")
        if self.form == "difference" and not (self.of and self.minus):
            raise ValueError(f"identity {self.id}: a difference needs `of` and at least one `minus`")
        if self.form in ("difference", "weighted_average") and self.coefficient != 1.0:
            raise ValueError(f"identity {self.id}: a {self.form} has no coefficient")
        if self.form == "weighted_average" and (len(self.weights) < 2 or abs(sum(self.weights.values()) - 1) > 1e-6):
            raise ValueError(f"identity {self.id}: a weighted average needs two or more weights that sum to 1")
        if self.coefficient == 0:
            raise ValueError(f"identity {self.id}: a zero coefficient defines nothing")
        terms = [v for v, _ in self.terms()]
        if _dupes(terms):
            raise ValueError(f"identity {self.id}: {', '.join(_dupes(terms))} appears twice")
        if self.target in terms:
            raise ValueError(f"identity {self.id}: the target is also a term")
        return self

    def terms(self) -> list[tuple[str, int]]:
        """(value, exponent) for a product or ratio (+1 a factor or numerator, -1 a denominator); (value, sign) for a
        difference (+1 the total, -1 a part taken out)."""
        if self.form == "product":
            return [(v, 1) for v in self.factors]
        if self.form == "ratio":
            return [(v, 1) for v in self.numerator] + [(v, -1) for v in self.denominator]
        if self.form == "weighted_average":
            return [(v, 1) for v in self.weights]
        return [(str(self.of), 1)] + [(v, -1) for v in self.minus]

    def linear(self) -> bool:
        """A difference or weighted average holds in native units; a product or ratio in log space."""
        return self.form in ("difference", "weighted_average")

    def coefficients(self) -> dict[str, float]:
        """Each term's native coefficient in a linear identity (its sign, or its weight)."""
        return {v: (self.weights[v] if self.form == "weighted_average" else float(e)) for v, e in self.terms()}

    def role(self, value: str) -> str:
        if self.form == "product":
            return "factor"
        if self.form == "ratio":
            return "numerator" if value in self.numerator else "denominator"
        if self.form == "weighted_average":
            return f"weight {self.weights[value]:g}"
        return "total" if value == self.of else "deduction"

    def formula(self, names: dict[str, str] | None = None) -> str:
        """The identity in words: "NII = 0.01 x earning assets x NIM", "CET1 ratio = 100 x CET1 / RWA"."""
        n = names or {}

        def nm(v: str) -> str:
            return n.get(v, v)

        coef = "" if self.coefficient == 1.0 else f"{self.coefficient:g} x "
        if self.form == "product":
            rhs = coef + " x ".join(nm(v) for v in self.factors)
        elif self.form == "ratio":
            num = " x ".join(nm(v) for v in self.numerator)
            den = " x ".join(nm(v) for v in self.denominator)
            rhs = f"{coef}{num} / {den if len(self.denominator) == 1 else '(' + den + ')'}"
        elif self.form == "weighted_average":
            rhs = " + ".join(f"{w:g} x {nm(v)}" for v, w in self.weights.items())
        else:
            rhs = " - ".join([nm(str(self.of)), *(nm(v) for v in self.minus)])
        return f"{nm(self.target)} = {rhs}"


class StockFlow(BaseModel):
    """A stock that accumulates flows (Oct 18): closing = opening + inflows - outflows, each flow measured per
    `period_days` (CET1 capital += net income - distributions; allowance += provision - charge-offs; AUM += net flows +
    market). Each flow reaches the stock by a `stock_flow` link whose weight is derived and whose kernel accumulates."""

    model_config = ConfigDict(extra="forbid")

    id: str
    entity_id: str
    stock: str
    period_days: float                   # the period each flow is measured over (91 for a quarter)
    inflows: list[str] = []
    outflows: list[str] = []             # held as positive levels that subtract (a flow held negative is an inflow)
    # Oct 18: what the stock value measures: its level at the period's end, or its average over the period (average
    # subscribers); an average lags the end level by about half a period
    measure: Literal["period_end", "period_average"] = "period_end"
    basis: str = ""
    note: str = ""

    @model_validator(mode="after")
    def _flows(self) -> StockFlow:
        if self.period_days <= 0:
            raise ValueError(f"stock-flow {self.id}: the period must be positive")
        flows = [*self.inflows, *self.outflows]
        if not flows:
            raise ValueError(f"stock-flow {self.id}: no flows")
        if _dupes(flows):
            raise ValueError(f"stock-flow {self.id}: {', '.join(_dupes(flows))} appears twice")
        if self.stock in flows:
            raise ValueError(f"stock-flow {self.id}: the stock is also a flow")
        return self

    def terms(self) -> list[tuple[str, int]]:
        return [(v, 1) for v in self.inflows] + [(v, -1) for v in self.outflows]

    def formula(self, names: dict[str, str] | None = None) -> str:
        n = names or {}
        flows = "".join(f" {'+' if k > 0 else '-'} {n.get(v, v)}" for v, k in self.terms())
        st = n.get(self.stock, self.stock)
        avg = "; the stock is a period average" if self.measure == "period_average" else ""
        return f"{st} (closing) = {st} (opening){flows}, per {self.period_days:g} days{avg}"


class Matrix(BaseModel):
    """Two additive views of one total declared as one cross-classified structure (Oct 18): rows x columns (segments x
    lines), each cell optional. Only the driving view's parts link to the total; the other view's parts are reached from
    the cells (each cell links to its row part and its column part) and reconcile to the total without driving it, so
    nothing is counted twice and both views can be observed together."""

    model_config = ConfigDict(extra="forbid")

    id: str
    entity_id: str
    rows: str                            # a composition id
    columns: str                         # a composition id with the same total
    drives: Literal["rows", "columns"] = "rows"
    cells: dict[str, dict[str, str]] = {}    # row part -> column part -> the cell's value id
    note: str = ""

    @property
    def driving(self) -> str:
        return self.rows if self.drives == "rows" else self.columns

    @property
    def passive(self) -> str:
        return self.columns if self.drives == "rows" else self.rows

    def cell_list(self) -> list[tuple[str, str, str]]:
        """(row part, column part, cell value)."""
        return [(r, c, v) for r, cols in sorted(self.cells.items()) for c, v in sorted(cols.items())]


def reconciling_views(graph: Any) -> dict[str, str]:
    """Composition id -> why it reconciles to its total without driving it: `drives: false` on the composition, or
    the matrix that holds it as its passive view."""
    out = {cid: "drives: false" for cid, c in sorted(graph.compositions.items()) if c.additive and not c.drives}
    out.update({m.passive: f"matrix {mid}" for mid, m in sorted(graph.matrices.items())})
    return out


def composition_role(graph: Any, cid: str) -> str:
    """"driving" (its parts' accounting links carry changes into the total), "reconciling" (observed and reconciled
    against the total, never propagating into it), or "non_additive" (its parts overlap)."""
    if not graph.compositions[cid].additive:
        return "non_additive"
    return "reconciling" if cid in reconciling_views(graph) else "driving"


def _parts(c: Composition) -> list[str]:
    return [*c.members, *([c.residual] if c.residual else []), *([c.eliminations] if c.eliminations else [])]


# -- derived weights (Oct 18) -------------------------------------------------------------------------------------------
def native_per_sd(level: float, scale: float, link: str) -> float:
    """d(value) / d(z) at `level`: a standard unit's size in native units (scale x d value / d link)."""
    if link == "log":
        return scale * level
    if link == "logit":
        return scale * level * (1.0 - level)
    return scale


def log_per_sd(level: float, scale: float, link: str, what: str) -> float:
    """d ln(value) / d(z) at `level` (a relative change per standard unit); a Gaussian value is linearized at its level,
    which must not be zero."""
    if link == "log":
        return scale
    if level == 0:
        raise ValueError(f"{what}: a level of zero cannot be linearized in a product or ratio")
    return native_per_sd(level, scale, link) / level


def identity_weights(identity: Identity, values: dict[str, tuple[float, float, str]]) -> dict[str, float]:
    """Each term's weight on the target, in target sd per term sd, at the construction levels. `values`: value id ->
    (native level, link-space scale, link). A product or ratio holds in log space, d ln y = sum_i e_i d ln x_i (e = +1
    a factor or numerator, -1 a denominator), so w_i = e_i x (d ln x_i / dz_i) / (d ln y / dz_y); a difference holds in
    native units, dy = dx_of - sum dx_minus, so w_i = sign_i x (dx_i / dz_i) / (dy / dz_y)."""
    ly, sy, ky = values[identity.target]
    out = {}
    for v, e in identity.terms():
        lx, sx, kx = values[v]
        if identity.linear():
            out[v] = identity.coefficients()[v] * native_per_sd(lx, sx, kx) / native_per_sd(ly, sy, ky)
        else:
            out[v] = e * log_per_sd(lx, sx, kx, v) / log_per_sd(ly, sy, ky, identity.target)
    return out


def stock_flow_weights(sf: StockFlow, values: dict[str, tuple[float, float, str]]) -> dict[str, float]:
    """Each flow's weight on its stock: stock sd added per period by a flow held one sd above its level,
    w = +-(d flow / dz_flow) / (d stock / dz_stock), at the construction levels."""
    ls, ss, ks = values[sf.stock]
    return {v: e * native_per_sd(*values[v]) / native_per_sd(ls, ss, ks) for v, e in sf.terms()}


def validate_construction(graph: Any) -> list[str]:
    """Structural problems with the graph's paths and compositions (empty when the construction holds)."""
    problems: list[str] = []
    inter = graph.interactions
    for pid, p in sorted(graph.paths.items()):
        if p.entity_id not in graph.entities:
            problems.append(f"path {pid}: unknown entity {p.entity_id!r}")
        if p.endpoint not in graph.subentities:
            problems.append(f"path {pid}: unknown endpoint {p.endpoint!r}")
        if not p.steps:
            problems.append(f"path {pid}: no steps")
            continue
        missing = [s.interaction_id for s in p.steps if s.interaction_id not in inter]
        if missing:
            problems.append(f"path {pid}: unknown interactions {missing}")
            continue
        reached: set[str] = set()
        for k, s in enumerate(p.steps):
            i = inter[s.interaction_id]
            if i.retired_at is not None:
                problems.append(f"path {pid}: step {k} ({i.id}) is retired")
            if k and i.source_id not in reached:
                problems.append(f"path {pid}: step {k} ({i.id}) starts at {i.source_id}, which no earlier step reaches")
            if s.branch is not None:
                sibs = [inter[t.interaction_id].source_id for t in p.steps if t.branch == s.branch]
                if len(set(sibs)) > 1:
                    problems.append(f"path {pid}: branch {s.branch!r} steps start at different values {sorted(set(sibs))}")
            reached |= {i.source_id, i.target_id}
        if p.endpoint not in reached:
            problems.append(f"path {pid}: no step reaches its endpoint {p.endpoint}")
    member_of: dict[str, list[str]] = {}
    passive = reconciling_views(graph)
    accounting = [i for i in inter.values() if i.retired_at is None and str(i.edge_type) == "accounting"]
    links = {(i.source_id, i.target_id) for i in accounting}
    quantified = {(i.source_id, i.target_id) for i in accounting if i.quantified}
    driving: dict[str, list[str]] = {}
    for cid, c in sorted(graph.compositions.items()):
        if c.additive and cid not in passive:
            driving.setdefault(c.total, []).append(cid)
    for total, cids in sorted(driving.items()):
        if len(cids) > 1:
            problems.append(f"{total} has {len(cids)} driving views ({', '.join(cids)}); one view drives a total: mark "
                            f"the others `drives: false` (reconciling) or declare them as a matrix")
    for mid, m in sorted(graph.matrices.items()):
        if m.driving in graph.compositions and not graph.compositions[m.driving].drives:
            problems.append(f"matrix {mid}: its driving view {m.driving} is marked `drives: false`")
    for cid, c in sorted(graph.compositions.items()):
        if c.entity_id not in graph.entities:
            problems.append(f"composition {cid}: unknown entity {c.entity_id!r}")
        for sid in [c.total, *_parts(c)]:
            if sid not in graph.subentities:
                problems.append(f"composition {cid}: unknown value {sid!r}")
        if c.total in _parts(c):
            problems.append(f"composition {cid}: the total is also a part")
        if not c.additive:
            continue
        for sid in _parts(c):
            if cid in passive:
                # a reconciling view is observed and reconciled against the total but never drives it: a quantified
                # link would count the change a second time (an uncalibrated one carries no numbers and may stay)
                if (sid, c.total) in quantified:
                    problems.append(f"composition {cid}: {sid} drives {c.total}, but {cid} is a reconciling view "
                                    f"({passive[cid]}); only the driving view links to the total")
                continue
            if sid in graph.subentities and (sid, c.total) not in links:
                problems.append(f"composition {cid}: {sid} has no accounting link to its total {c.total}")
            member_of.setdefault(f"{sid}|{c.total}", []).append(cid)
    # a part may sit in bridges of different totals (a segment's revenue in group revenue and in its own segment
    # profit bridge: a tree); only two additive views of the same total overlap
    for key, cids in sorted(member_of.items()):
        if len(cids) > 1:
            problems.append(f"{key.split('|')[0]} is a part of more than one additive view ({', '.join(cids)}); views "
                            f"overlap and must not be added to each other")
    problems += _identity_problems(graph) + _matrix_problems(graph, links)
    for iid, i in sorted(inter.items()):
        if i.retired_at is None and str(getattr(i, "calibration", "calibrated")) == "uncalibrated" \
                and (i.transition is None or i.transition.sign is None):
            problems.append(f"interaction {iid}: uncalibrated, so it needs a transition with a sign")
    return problems


def _identity_problems(graph: Any) -> list[str]:
    """Identities and stock-flows: their entity and values exist, each term reaches the target by exactly the link of
    its kind that names the object, no such link names anything else, and a stock-flow link accumulates over the
    period."""
    problems: list[str] = []
    live = [i for i in graph.interactions.values() if i.retired_at is None]
    objs: list[tuple[str, Any, str, str]] = [("identity", x, x.target, "identity")
                                             for _, x in sorted(graph.identities.items())]
    objs += [("stock-flow", x, x.stock, "stock_flow") for _, x in sorted(graph.stock_flows.items())]
    for kind, x, target, edge in objs:
        if x.entity_id not in graph.entities:
            problems.append(f"{kind} {x.id}: unknown entity {x.entity_id!r}")
        for sid in [target, *(v for v, _ in x.terms())]:
            if sid not in graph.subentities:
                problems.append(f"{kind} {x.id}: unknown value {sid!r}")
        for v, _ in x.terms():
            ls = [i for i in live if i.source_id == v and i.target_id == target and str(i.edge_type) == edge
                  and i.identity == x.id]
            if len(ls) != 1:
                problems.append(f"{kind} {x.id}: {v} needs one {edge} link to {target} naming it (found {len(ls)})")
            for i in ls:
                k = i.forward.kernel
                if edge == "stock_flow" and (not k.accumulates or abs(k.lag.mean() - x.period_days) > 0.5):
                    problems.append(f"{kind} {x.id}: link {i.id} must accumulate over {x.period_days:g} days")
    known = {(x.id, edge): {(v, t) for v, _ in x.terms()} for _k, x, t, edge in objs}
    for i in sorted(live, key=lambda i: i.id):
        edge = str(i.edge_type)
        if edge not in ("identity", "stock_flow"):
            continue
        pairs = known.get((i.identity or "", edge))
        if pairs is None:
            problems.append(f"interaction {i.id}: an {edge} link names no {edge.replace('_', '-')} ({i.identity!r})")
        elif (i.source_id, i.target_id) not in pairs:
            problems.append(f"interaction {i.id}: {i.source_id} -> {i.target_id} is not a term of {i.identity}")
    return problems


def _matrix_problems(graph: Any, links: set[tuple[str, str]]) -> list[str]:
    """Matrices: two additive views of one total and entity, and each cell linked to its row part and column part."""
    problems: list[str] = []
    comps = graph.compositions
    for mid, m in sorted(graph.matrices.items()):
        if m.entity_id not in graph.entities:
            problems.append(f"matrix {mid}: unknown entity {m.entity_id!r}")
        missing = [c for c in (m.rows, m.columns) if c not in comps]
        if missing or m.rows == m.columns:
            problems.append(f"matrix {mid}: rows and columns must be two compositions "
                            f"({'unknown ' + ', '.join(missing) if missing else 'the same one twice'})")
            continue
        r, c = comps[m.rows], comps[m.columns]
        if r.total != c.total or r.entity_id != c.entity_id or not (r.additive and c.additive):
            problems.append(f"matrix {mid}: {m.rows} and {m.columns} must be additive views of one total of one entity")
        for row, col, cell in m.cell_list():
            if row not in _parts(r) or col not in _parts(c):
                problems.append(f"matrix {mid}: cell {cell} sits at ({row}, {col}), which is not a row part and a "
                                f"column part")
                continue
            if cell not in graph.subentities:
                problems.append(f"matrix {mid}: unknown cell value {cell!r}")
                continue
            for part in (row, col):
                if (cell, part) not in links:
                    problems.append(f"matrix {mid}: cell {cell} has no accounting link to {part}")
    return problems


TOLERANCE = 0.005    # a composition reconciles when its parts add to the total within 0.5% of the total


def model_levels(graph: Any, statistic: Literal["mean", "median"] = "mean") -> dict[str, float]:
    """Each value's level: its posterior mean (or median) in native units (a value whose family has neither is left
    out). The means of lognormal parts need not add up when their medians do (the mean carries exp(sigma^2 / 2)), so a
    view built from round construction levels reconciles at the medians first."""
    out = {}
    for sid, s in graph.subentities.items():
        try:
            out[sid] = float(s.posterior.mean() if statistic == "mean" else s.posterior.quantile(0.5))
        except Exception:  # noqa: BLE001 - a family without a mean has no level to reconcile
            continue
    return out


def bundle_levels(bundle: dict) -> dict[str, float]:
    """The levels an axelrod.import/v1 bundle observes: per value, its latest observe (by the item's publication
    time; on a tie, the later in the file). Only `observe` signals carry a level."""
    seen: dict[str, tuple[str, int, float]] = {}
    k = 0
    for item in bundle.get("items") or []:
        at = str(item.get("published_at") or "")
        for sig in item.get("signals") or []:
            if sig.get("type") != "observe" or sig.get("value_of") is None or sig.get("value") is None:
                continue
            k += 1
            prev = seen.get(sig["value_of"])
            if prev is None or (at, k) > prev[:2]:
                seen[sig["value_of"]] = (at, k, float(sig["value"]))
    return {sid: v for sid, (_at, _k, v) in sorted(seen.items())}


def reconcile(graph: Any, levels: dict[str, float] | None = None, tolerance: float = TOLERANCE) -> list[dict]:
    """For each additive composition: does the total equal its members + residual + eliminations? Each part counts
    with the sign of its accounting link to the total: a deduction held as a positive level (funding cost, other
    expenses) has a negative link and subtracts; an elimination is either held negative with a positive link or held
    positive with a negative one. Levels are the model's (`model_levels`) unless `levels` ({value id: level}, e.g.
    `bundle_levels` of the local baselines) is given.

    Each row: the total's level and the signed sum of the parts' levels; their difference (total minus sum) and
    relative difference (over |total|); the parts that subtract; parts whose unit differs from the total's; values
    without a level; the residual level that would close the gap (the residual's level plus the difference, through
    its sign; the difference when the view has no residual); and `ok` (all levels present, one unit, within
    `tolerance`) or `flag`."""
    lv = model_levels(graph) if levels is None else levels
    subs = graph.subentities
    sign = {(i.source_id, i.target_id): i.polarity() for i in graph.interactions.values()
            if i.retired_at is None and str(i.edge_type) == "accounting"}
    rows = []
    for cid, c in sorted(graph.compositions.items()):
        if not c.additive:
            continue
        parts = _parts(c)
        sg = {s: sign.get((s, c.total), 1) for s in parts}
        unit = subs[c.total].unit if c.total in subs else c.unit
        mismatch = [s for s in parts if s in subs and subs[s].unit != unit]
        missing = [s for s in [c.total, *parts] if s not in lv]
        total = lv.get(c.total)
        got = [sg[s] * lv[s] for s in parts if s in lv]
        total_sum = sum(got) if got else None
        diff = rel = close = None
        if total is not None and total_sum is not None:
            diff = total - total_sum
            rel = diff / abs(total) if total else (0.0 if diff == 0 else None)
            close = lv.get(c.residual, 0.0) + sg[c.residual] * diff if c.residual else diff
        rows.append({"composition_id": cid, "entity_id": c.entity_id, "view": c.view,
                     "role": composition_role(graph, cid), "unit": unit,
                     "total": c.total, "total_level": total, "parts": parts,
                     "subtracted": [s for s in parts if sg[s] < 0], "sum": total_sum, "difference": diff,
                     "relative_difference": rel, "unit_mismatches": mismatch, "missing_levels": missing,
                     "residual": c.residual, "residual_to_close": close, "tolerance": tolerance,
                     "status": verdict(missing, mismatch, rel, tolerance), "blocked_by": missing})
    return rows


def verdict(missing: list[str], mismatch: list[str], rel: float | None, tolerance: float) -> str:
    """"ok" (within tolerance), "flag" (a discrepancy: a gap beyond tolerance, or a unit mismatch), or "blocked" (a
    level is missing, so there is nothing to compare: the named inputs block the check, it is not a discrepancy)."""
    if mismatch:
        return "flag"
    if missing:
        return "blocked"
    return "ok" if rel is not None and abs(rel) <= tolerance else "flag"


def _rel(total: float, implied: float) -> tuple[float, float | None]:
    diff = total - implied
    return diff, diff / abs(total) if total else (0.0 if diff == 0 else None)


def reconcile_identities(graph: Any, levels: dict[str, float] | None = None,
                         tolerance: float = TOLERANCE) -> list[dict]:
    """For each identity: does the target's level equal what its terms imply (coefficient x the product of the factors,
    or of the numerator over the denominator; or the total less the parts taken out)? This is the unit check the model
    can make: units are free text, so a product's unit algebra is stated (`unit_check`) and tested through the levels
    (a rate held in % without its 0.01 misses by 100x); a difference's terms must share the target's unit.

    Each row: the identity, its form and formula, the target's level, the implied level, their difference and
    relative difference (over |target|), values without a level, unit mismatches (difference only), and `ok` or
    `flag`. Levels are the model's (`model_levels`) unless given; lognormal products reconcile at the medians."""
    lv = model_levels(graph) if levels is None else levels
    subs = graph.subentities
    rows = []
    for iid, x in sorted(graph.identities.items()):
        terms = x.terms()
        missing = [v for v in [x.target, *(t for t, _ in terms)] if v not in lv]
        mismatch = [v for v, _ in terms if x.linear() and v in subs and x.target in subs
                    and subs[v].unit != subs[x.target].unit]
        implied = diff = rel = None
        if not missing:
            if x.linear():
                implied = sum(k * lv[v] for v, k in x.coefficients().items())
            else:
                implied = x.coefficient
                for v, e in terms:
                    implied = implied * lv[v] if e > 0 else (implied / lv[v] if lv[v] else math.inf)
            diff, rel = _rel(lv[x.target], implied) if math.isfinite(implied) else (None, None)
        rows.append({"identity_id": iid, "entity_id": x.entity_id, "form": x.form,
                     "formula": x.formula({k: s.name for k, s in subs.items()}), "target": x.target,
                     "target_level": lv.get(x.target), "implied": implied, "difference": diff, "relative_difference": rel,
                     "missing_levels": missing, "unit_mismatches": mismatch, "unit_check": x.unit_check,
                     "tolerance": tolerance, "status": verdict(missing, mismatch, rel, tolerance),
                     "blocked_by": missing})
    return rows


def reconcile_matrices(graph: Any, levels: dict[str, float] | None = None, tolerance: float = TOLERANCE) -> list[dict]:
    """For each matrix, each row part and column part whose cells are all given (one per part of the other view):
    does the part equal the sum of its cells? The views themselves reconcile to the total in `reconcile`. Parts whose
    cells are incomplete are listed under `incomplete`, not checked."""
    lv = model_levels(graph) if levels is None else levels
    rows = []
    for mid, m in sorted(graph.matrices.items()):
        if m.rows not in graph.compositions or m.columns not in graph.compositions:
            continue
        r_parts, c_parts = _parts(graph.compositions[m.rows]), _parts(graph.compositions[m.columns])
        cells = m.cell_list()
        lines: list[dict] = []
        incomplete: list[str] = []
        for axis, parts, other in (("row", r_parts, c_parts), ("column", c_parts, r_parts)):
            for p in parts:
                mine = {(c if axis == "row" else r): v for r, c, v in cells if (r if axis == "row" else c) == p}
                if set(mine) != set(other):
                    incomplete.append(p)
                    continue
                vals = list(mine.values())
                missing = [v for v in [p, *vals] if v not in lv]
                got = None if missing else sum(lv[v] for v in vals)
                diff, rel = (None, None) if got is None else _rel(lv[p], got)
                lines.append({"axis": axis, "part": p, "level": lv.get(p), "sum_of_cells": got, "cells": vals,
                              "difference": diff, "relative_difference": rel, "missing_levels": missing,
                              "status": verdict(missing, [], rel, tolerance)})
        rows.append({"matrix_id": mid, "entity_id": m.entity_id, "rows": m.rows, "columns": m.columns,
                     "drives": m.drives, "lines": lines, "incomplete": incomplete, "tolerance": tolerance,
                     "status": next((v for v in ("flag", "blocked") if any(x["status"] == v for x in lines)), "ok")})
    return rows


def bundle_series(bundle: dict) -> dict[str, list[tuple[str, float]]]:
    """Every level an axelrod.import/v1 bundle observes, per value, as (publication date, level) in date order (one
    level per value and date: the later in the file)."""
    seen: dict[str, dict[str, float]] = {}
    for item in bundle.get("items") or []:
        at = str(item.get("published_at") or "")[:10]
        for sig in item.get("signals") or []:
            if sig.get("type") == "observe" and sig.get("value_of") is not None and sig.get("value") is not None:
                seen.setdefault(sig["value_of"], {})[at] = float(sig["value"])
    return {sid: sorted(d.items()) for sid, d in sorted(seen.items())}


def reconcile_stock_flows(graph: Any, series: dict[str, list[tuple[str, float]]],
                          tolerance: float = TOLERANCE) -> list[dict]:
    """For each stock-flow and each pair of consecutive dated stock levels (`bundle_series` of the baselines): does
    closing = opening + inflows - outflows, the flows summed over the levels dated after the opening and up to the
    closing? A roll-forward needs two dated stock levels, so the model's own levels (one per value) cannot check it.

    Each row: the stock-flow, the dates, the opening and closing levels, each flow's sum, the implied closing, the
    difference and relative difference (over |closing|), flows with no level in the window, and `ok` or `flag`."""
    rows = []
    for sfid, x in sorted(graph.stock_flows.items()):
        if x.measure == "period_average":
            continue                     # an average's roll-forward needs the end levels, which it does not report
        st = series.get(x.stock, [])
        for (t0, opening), (t1, closing) in zip(st, st[1:]):
            inside = {v: [lvl for at, lvl in series.get(v, []) if t0 < at <= t1] for v, _ in x.terms()}
            missing = [v for v, _ in x.terms() if not inside[v]]
            implied = opening + sum(e * sum(inside[v]) for v, e in x.terms())
            diff, rel = _rel(closing, implied)
            rows.append({"stock_flow_id": sfid, "entity_id": x.entity_id, "stock": x.stock, "opening_at": t0,
                         "closing_at": t1, "opening": opening, "closing": closing,
                         "inflows": {v: sum(inside[v]) for v in x.inflows},
                         "outflows": {v: sum(inside[v]) for v in x.outflows}, "implied_closing": implied,
                         "difference": diff, "relative_difference": rel, "missing_flows": missing,
                         "tolerance": tolerance, "status": verdict(missing, [], rel, tolerance),
                         "blocked_by": missing})
    return rows


PROFILE_FIELDS = ("native_slope", "exposure", "unit", "date", "hedge", "pass_through", "financial_endpoint", "calculation", "source")


def transition_profile(graph: Any, i: Any) -> dict[str, Any]:
    """The retrieval fields every active link carries (Oct 18): the exposure (business unit, geography, currency), the
    unit (source -> target), the date (when the link entered the model, and when the accounts recognize it), hedge and
    pass-through ("unknown" when not stated, never zero), the financial endpoint (the endpoints of the named paths the
    link is a step of, else its target), the calculation (the identity or stock-flow formula, the calibrated size, or
    "unsized (sign only)"), and the source ids. Derived from the link and the graph, so no link can lack them."""
    tr = i.transition
    sub = graph.subentities

    def unit(sid: str) -> str:
        return getattr(sub.get(sid), "unit", "") or ""

    exposure = "; ".join(x for x in ((tr.business_unit, tr.geography, tr.currency) if tr else ()) if x) or "unknown"
    ends = sorted({p.endpoint for p in graph.paths.values() if any(s.interaction_id == i.id for s in p.steps)})
    if i.identity is not None:
        obj = graph.identities.get(i.identity) or graph.stock_flows.get(i.identity)
        calc = obj.formula() if obj is not None else f"term of {i.identity}"
    elif i.quantified:
        e = i.forward.effect
        sd = getattr(e, "sigma", None)
        calc = (f"{'accounting' if i.fixed else 'calibrated'} effect {float(e.mean()):.4g} sd/sd"
                + (f" (sigma {float(sd):.3g})" if sd is not None else "")
                + (f", magnitude {tr.evidence.magnitude}" if tr else ""))
    else:
        calc = "unsized (sign only): forecasts list it as excluded, never as zero"
    recog = tr.timing.recognition if tr else "unknown"
    return {"native_slope": native_slope(graph, i),
            "exposure": exposure,
            "unit": f"{unit(i.source_id) or '?'} -> {unit(i.target_id) or '?'}",
            "date": {"in_model_from": i.created_at.isoformat() if getattr(i, "created_at", None) else None,
                     "recognition": recog},
            "hedge": (tr.hedge if tr and tr.hedge else "unknown"),
            "pass_through": (tr.pass_through if tr and tr.pass_through else "unknown"),
            "financial_endpoint": ends or [i.target_id],
            "calculation": calc,
            "source": list(tr.evidence.sources) if tr else []}


def construction_level(sub: Any) -> tuple[float, float, str]:
    """A value's (native construction level, link-space scale, link) from its prior, as the build sizes links."""
    from axelrod_wm.model.distributions import from_link

    link = str(sub.prior.link)
    return float(from_link(sub.prior.link_moments()[0], link)), float(sub.scale), link


def native_slope(graph: Any, i: Any) -> float | None:
    """A sized link's change in the target per unit change in the source, in their native units at the construction
    levels (effect x target native sd / source native sd); None when the link carries no size."""
    if not i.quantified or i.source_id not in graph.subentities or i.target_id not in graph.subentities:
        return None
    try:
        s, t = construction_level(graph.subentities[i.source_id]), construction_level(graph.subentities[i.target_id])
        return round(float(i.forward.effect.mean()) * native_per_sd(*t) / native_per_sd(*s), 9)
    except Exception:  # noqa: BLE001 - a value without a usable prior has no native slope
        return None

