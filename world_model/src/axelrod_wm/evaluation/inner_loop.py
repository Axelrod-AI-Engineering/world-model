"""The inner-loop accuracy suite's runner (Oct 22): answer a questions-only bank from the world model, return the
suite's contract, and never see an answer.

The suite is a bank of cases (a question, its family, the frozen page excerpts it is bound to) plus the stipulated
inputs of the cases that need them (`fixture_inputs`) and an index of the frozen excerpts (source, version, hashes,
availability date, page). The runner answers each case from a *recipe*: a small, declarative plan kept beside the
client's data, never tracked, that says where each input comes from and how the answer is built. A recipe holds no
answers. Its inputs are read, by locator, from the question text, the fixture, a frozen excerpt, or the world model
(through the `Reader` the golden-bank harness already uses: the v1 construction), and its results are computed by a
deterministic, free-standing calculator (Decimal arithmetic, a restricted expression language, no clock, no random).

    inputs     name -> locator: {question: regex} | {fixture: path} | {excerpt: id, after: regex, index: n}
                                | {excerpt: id, pattern: regex} | {source_of: id, field: f} | {const: v}
    compute    name -> expression over the inputs and earlier names (+ - * / ** min max abs round sum, if/else,
               comparisons, dates)
    facts      field -> a stated qualitative result (a refusal, a classification, a scope) the case asks for
    unknowns   what the case's inputs leave undetermined, named; they are returned, never counted as zero

Operations (`op`): `calc` (the above), `reconcile` (a composition's parts against its total: the parts come from the
world model's composition, the figures from the source), `identity` (one of the model's identities against the source's
figures, with the golden bank's arithmetic), `ledger` (update and undo of a stipulated input and its
dependent output, with the audit history), `review_mapping` and `review_golden` (the two review gates: artifacts in,
a classification out), and `blocked` (a requirement the system cannot run, with its reason). A missing recipe, a missing
source or an unresolvable input is `blocked` with a reason, never a guess.

Separation (the evidence for the suite's golden-provenance review). The runner reads files only through `Access`,
which refuses any path outside the roots it was given (the suite folder, the recipes), and logs every file it read with
its hash. The answer key lives outside those roots; this module never names it, and the grader (inner_loop_grade.py)
is the only code that is handed its path. A test asserts the module's text.

The contract. The suite's output fields (`required_output_fields`) are semantic targets, not a schema: `FIELD_MAP` maps
our own fields (`answer`, `scope`, `objects`, ...) onto them, and a field a case does not exercise says so with a reason
instead of an invented baseline. Our schema is not renamed: the result keeps it under `internal`.
"""

from __future__ import annotations

import ast
import hashlib
import json
import operator
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, DivisionByZero, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

import yaml

from axelrod_wm.evaluation.golden import eval_identity

CONTRACT_FIELDS = (
    "test_id", "actual_result", "status", "scope_period_units_when_applicable",
    "evidence_and_object_bindings_when_applicable", "calculation_trace_when_applicable",
    "selected_baseline_scenario_version_when_applicable", "assumptions_and_unresolved_inputs",
)

# Our fields -> the suite's field labels. The labels are semantic targets (the suite's adapter_field_policy), so the
# mapping preserves values, definitions, evidence and state; it does not rename ours.
FIELD_MAP = {
    "actual_result": "answer",
    "scope_period_units_when_applicable": "scope",
    "evidence_and_object_bindings_when_applicable": "evidence_and_objects",
    "calculation_trace_when_applicable": "calculations",
    "selected_baseline_scenario_version_when_applicable": "baseline",
    "assumptions_and_unresolved_inputs": "assumptions_and_missing",
}

ANSWERED, BLOCKED, NOT_RUN = "answered", "blocked", "not_run"


class Blocked(Exception):
    """The case cannot be run or judged as specified; the message is its reason."""


class AccessDenied(PermissionError):
    """A read outside the roots the runner was given."""


class Reader(Protocol):
    def construction(self, entity_id: str) -> dict: ...


class Service(Protocol):
    """A clean world to operate on: the intake side of the v1 API, as a runner needs it."""

    def upload(self, name: str, data: bytes) -> dict: ...
    def documents(self) -> list[dict]: ...
    def bundles(self) -> list[dict]: ...


class RecordStore(Protocol):
    """A clean store of dated records for one metric, for the ingestion-order case. `can_state_supersession` says
    whether a record can say that it corrects another; `current` is the record selected at an information cutoff."""

    can_state_supersession: bool

    def ingest(self, record: dict) -> None: ...
    def current(self, as_of: date) -> dict | None: ...
    def history(self) -> list[dict]: ...


class V1Service:
    """The v1 API's documents and bundles, on a fresh app (any client with `get` and `post`)."""

    def __init__(self, client: Any, world_model_id: str) -> None:
        self.c, self.base, self.n = client, f"/v1/world-models/{world_model_id}", 0

    def upload(self, name: str, data: bytes) -> dict:
        self.n += 1
        r = self.c.post(self.base + "/documents", files={"files": (name, data, "text/plain")},
                        data={"source": "fixture", "source_type": "other"},
                        headers={"Idempotency-Key": f"inner-loop-{self.n}"})
        return r.json()["data"]["result"]["detail"]["results"][0]

    def documents(self) -> list[dict]:
        return self.c.get(self.base + "/documents").json()["data"]

    def bundles(self) -> list[dict]:
        return self.c.get(self.base + "/bundles").json()["data"]


class Cached:
    """A reader that fetches each entity's construction once per run."""

    def __init__(self, reader: Reader) -> None:
        self.reader = reader
        self.memo: dict[str, dict] = {}

    def construction(self, entity_id: str) -> dict:
        if entity_id not in self.memo:
            self.memo[entity_id] = self.reader.construction(entity_id)
        return self.memo[entity_id]


# -- reading, with a guard and a log ---------------------------------------------------------------------------------------
class Access:
    """Every file the runner reads goes through here: refused outside `roots`, logged with its hash."""

    def __init__(self, roots: list[Path]) -> None:
        self.roots = [Path(r).resolve() for r in roots]
        self.reads: dict[str, str] = {}

    def allowed(self, path: Path) -> bool:
        return any(path.resolve().is_relative_to(r) for r in self.roots)

    def read_bytes(self, path: Path) -> bytes:
        p = Path(path).resolve()
        if not self.allowed(p):
            raise AccessDenied(f"{p.name}: outside the folders this run may read")
        raw = p.read_bytes()
        self.reads[str(p)] = hashlib.sha256(raw).hexdigest()
        return raw

    def read_text(self, path: Path) -> str:
        return self.read_bytes(path).decode("utf-8")

    def report(self) -> dict:
        return {"roots": [str(r) for r in self.roots], "files_read": [{"path": p, "sha256": h}
                                                                      for p, h in sorted(self.reads.items())]}


# -- the suite -------------------------------------------------------------------------------------------------------------
@dataclass
class Suite:
    root: Path
    access: Access
    meta: dict
    cases: list[dict]
    fixtures: dict[str, dict]
    index: dict
    _text: dict[str, str] = field(default_factory=dict)

    def excerpt(self, excerpt_id: str) -> dict | None:
        return next((e for e in self.index.get("excerpts", []) if e["excerpt_id"] == excerpt_id), None)

    def excerpt_text(self, excerpt_id: str) -> str:
        """The frozen page's text, checked against the index's hash (a changed page is a blocked case)."""
        if excerpt_id not in self._text:
            e = self.excerpt(excerpt_id)
            if e is None:
                raise Blocked(f"excerpt {excerpt_id} is not in the source index")
            path = self.root / "excerpts" / Path(e["text_file"]).name
            if not path.exists():
                raise Blocked(f"excerpt {excerpt_id}: the frozen page is not in the suite folder")
            raw = self.access.read_bytes(path)
            if hashlib.sha256(raw).hexdigest() != e["text_sha256"]:
                raise Blocked(f"excerpt {excerpt_id} differs from the hash the index froze")
            self._text[excerpt_id] = raw.decode("utf-8")
        return self._text[excerpt_id]


def load_suite(root: Path, access: Access | None = None) -> Suite:
    """The questions-only bank, its fixture inputs and its source index, from one folder."""
    root = Path(root)
    access = access or Access([root])
    q = json.loads(access.read_text(root / "questions.json"))
    fixtures = json.loads(access.read_text(root / "fixture_inputs.json"))
    index = json.loads(access.read_text(root / q["source_index"]))
    meta = {k: v for k, v in q.items() if k != "cases"}
    return Suite(root, access, meta, q["cases"], fixtures, index)


def load_recipes(path: Path, access: Access) -> dict[str, dict]:
    return yaml.safe_load(access.read_text(Path(path))) or {}


# -- numbers, text, dates --------------------------------------------------------------------------------------------------
NUMBER = re.compile(r"\(?[-−]?\d[\d,]*(?:\.\d+)?\)?")


def parse_number(token: str) -> Decimal:
    """'1,063,473' -> 1063473; '(285,617)' -> -285617; a unicode minus is a minus."""
    neg = token.startswith("(") or token.lstrip("(").startswith(("-", "−"))
    digits = re.sub(r"[^\d.]", "", token)
    return -Decimal(digits) if neg else Decimal(digits)


def parse_date(text: str) -> date:
    for fmt in ("%Y-%m-%d", "%B %d, %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    raise Blocked(f"not a date: {text!r}")


def plain(x: Any) -> Any:
    """A JSON-ready value: a Decimal is an int when whole, else a float; containers are walked."""
    if isinstance(x, Decimal):
        return int(x) if x == x.to_integral_value() else float(x)
    if isinstance(x, date):
        return x.isoformat()
    if isinstance(x, dict):
        return {k: plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    return x


def as_value(x: Any) -> Any:
    """A recipe constant as the calculator's value: numbers are Decimals."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return x
    return Decimal(str(x))


# -- the expression language -----------------------------------------------------------------------------------------------
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
_CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Eq: operator.eq,
        ast.NotEq: operator.ne}


def _round(x: Decimal, n: Decimal = Decimal(0)) -> Decimal:
    return x.quantize(Decimal(1).scaleb(-int(n)))


_FUNCS = {"min": min, "max": max, "abs": abs, "round": _round, "sum": lambda *a: sum(a, Decimal(0))}


def evaluate(expr: str, env: dict[str, Any]) -> Any:
    """A restricted expression over `env`; anything else, and any arithmetic that cannot be done, is blocked."""
    try:
        return _eval(ast.parse(str(expr), mode="eval").body, env)
    except (DivisionByZero, InvalidOperation, ZeroDivisionError) as e:
        raise Blocked(f"cannot calculate {expr!r}: {type(e).__name__}") from e
    except SyntaxError as e:
        raise Blocked(f"cannot read the expression {expr!r}") from e


def _eval(n: ast.AST, env: dict[str, Any]) -> Any:
    if isinstance(n, ast.Constant):
        return as_value(n.value)
    if isinstance(n, ast.Name):
        if n.id not in env:
            raise Blocked(f"the expression uses {n.id}, which is not an input or an earlier result")
        return env[n.id]
    if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
        return _BIN[type(n.op)](_eval(n.left, env), _eval(n.right, env))
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd, ast.Not)):
        v = _eval(n.operand, env)
        return {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Not: operator.not_}[type(n.op)](v)
    if isinstance(n, ast.Compare) and all(type(o) in _CMP for o in n.ops):
        left = _eval(n.left, env)
        for op, right in zip(n.ops, n.comparators, strict=True):
            r = _eval(right, env)
            if not _CMP[type(op)](left, r):
                return False
            left = r
        return True
    if isinstance(n, ast.BoolOp):
        vals = [_eval(v, env) for v in n.values]
        return all(vals) if isinstance(n.op, ast.And) else any(vals)
    if isinstance(n, (ast.List, ast.Tuple)):
        return [_eval(e, env) for e in n.elts]
    if isinstance(n, ast.IfExp):
        return _eval(n.body if _eval(n.test, env) else n.orelse, env)
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
        return _FUNCS[n.func.id](*[_eval(a, env) for a in n.args])
    raise Blocked(f"the expression uses something the calculator does not allow ({type(n).__name__})")


# -- locators --------------------------------------------------------------------------------------------------------------
@dataclass
class Run:
    """What one case has used so far: its evidence bindings, objects and the model reads it made."""

    suite: Suite
    case: dict
    reader: Reader | None
    services: Any = None            # a factory of clean `Service`s, for the cases that operate on a world
    stores: Any = None              # a factory of clean `RecordStore`s, for the ingestion-order case
    evidence: dict[str, dict] = field(default_factory=dict)
    objects: list[dict] = field(default_factory=list)
    baseline: dict | None = None

    def bind(self, excerpt_id: str, location: str, passage: str) -> None:
        e = self.suite.excerpt(excerpt_id)
        if e is None or excerpt_id not in self.case.get("frozen_excerpt_ids", []):
            raise Blocked(f"excerpt {excerpt_id} is not one of this case's frozen excerpts")
        src = self.suite.index["sources"][e["source_id"]]
        rec = self.evidence.setdefault(excerpt_id, {
            "excerpt_id": excerpt_id, "source_id": e["source_id"], "source_version": e["source_version"],
            "availability_date": src["availability_date"], "pdf_pages": e["pdf_pages"],
            "printed_page": e["printed_page"], "original_pdf_sha256": e["original_pdf_sha256"],
            "text_sha256": e["text_sha256"], "locations": []})
        rec["locations"].append({"location": location, "passage": passage})


def _pick(matches: list, loc: dict, what: str) -> Any:
    nth = int(loc.get("nth", 0))
    if nth >= len(matches):
        raise Blocked(f"{what}: match {nth} not found (found {len(matches)})")
    return matches[nth]


def _typed(m: re.Match, loc: dict) -> Any:
    """The match's group (1 by default) as the locator's kind: a number, a date, or text."""
    try:
        raw = m.group(int(loc.get("group", 1)))
    except IndexError as e:
        raise Blocked(f"the pattern {m.re.pattern!r} has no group {loc.get('group', 1)}") from e
    return {"number": parse_number, "date": parse_date}.get(loc.get("kind", "number"), str)(raw)


def _line_of(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start:end if end >= 0 else len(text)].strip()[:200]


def locate(loc: dict, run: Run) -> Any:
    """One input's value from its locator (see the module's docstring)."""
    kind = loc.get("kind", "number")
    if "const" in loc:
        return as_value(loc["const"])
    if "neg" in loc:
        return -locate(loc["neg"], run)
    if "sum" in loc:
        return sum((locate(x, run) for x in loc["sum"]), Decimal(0))
    if "fixture" in loc:
        node: Any = run.suite.fixtures.get(run.case["test_id"], {})
        for part in str(loc["fixture"]).split("."):
            if not isinstance(node, dict) or part not in node:
                raise Blocked(f"the fixture has no {loc['fixture']}")
            node = node[part]
        return as_value(node)
    if "question" in loc:
        m = _pick(list(re.finditer(loc["question"], run.case["question"])), loc, "question")
        return _typed(m, loc)
    if "source_of" in loc:
        e = run.suite.excerpt(loc["source_of"])
        if e is None:
            raise Blocked(f"excerpt {loc['source_of']} is not in the source index")
        raw = run.suite.index["sources"][e["source_id"]][loc["field"]]
        run.bind(loc["source_of"], f"source {e['source_id']}: {loc['field']}", str(raw))
        return {"number": parse_number, "date": parse_date}.get(kind, str)(str(raw))
    if "excerpt" in loc:
        eid = loc["excerpt"]
        text = run.suite.excerpt_text(eid)
        if "pattern" in loc:
            m = _pick(list(re.finditer(loc["pattern"], text, re.S)), loc, f"{eid} pattern")
            run.bind(eid, f"pattern {loc['pattern']!r} #{loc.get('nth', 0)}", _line_of(text, m.start()))
            return _typed(m, loc)
        anchor = _pick(list(re.finditer(loc["after"], text)), loc, f"{eid} anchor")
        numbers = list(NUMBER.finditer(text, anchor.start() if loc.get("inclusive") else anchor.end()))
        n = _pick(numbers, {"nth": loc.get("index", 0)}, f"{eid} number after the anchor")
        run.bind(eid, f"after {loc['after']!r} #{loc.get('nth', 0)}, number {loc.get('index', 0)}",
                 _line_of(text, anchor.start()) + " | " + _line_of(text, n.start()))
        return parse_number(n.group(0))
    raise Blocked(f"unknown locator {sorted(loc)}")


def gather(recipe: dict, run: Run) -> dict[str, Any]:
    return {name: locate(loc, run) for name, loc in (recipe.get("inputs") or {}).items()}


def calculate(recipe: dict, env: dict[str, Any]) -> tuple[dict[str, Any], list[dict]]:
    """The recipe's `compute`, in order, each result added to the environment; the trace records every step."""
    trace = []
    out: dict[str, Any] = {}
    for name, expr in (recipe.get("compute") or {}).items():
        out[name] = env[name] = evaluate(expr, env)
        used = sorted(k for k in env if k != name and re.search(rf"\b{re.escape(k)}\b", str(expr)))
        trace.append({"name": name, "expression": str(expr), "inputs": {k: plain(env[k]) for k in used},
                      "value": plain(out[name])})
    return out, trace


# -- the model --------------------------------------------------------------------------------------------------------------
def bind_objects(recipe: dict, run: Run) -> None:
    """Each object id the recipe names must exist in the world model's construction of its entity; one that does not is
    a gap in the model, and the case is blocked with it named."""
    ids = recipe.get("objects") or []
    if not ids:
        return
    if run.reader is None:
        raise Blocked("the recipe binds model objects but no world model was supplied")
    entity = recipe.get("entity", "")
    con = run.reader.construction(entity)
    known = {a["id"]: "attribute" for a in con.get("attributes", [])}
    known |= {x["id"]: "composition" for x in con.get("compositions", [])}
    known |= {x["id"]: "identity" for x in con.get("identities", [])}
    known |= {x["id"]: "path" for x in con.get("paths", [])}
    missing = [i for i in ids if i not in known]
    if missing:
        raise Blocked(f"not in the world model's construction of {entity}: {', '.join(missing)}")
    run.objects += [{"id": i, "kind": known[i], "entity": entity} for i in ids]


def reconcile(recipe: dict, run: Run, env: dict[str, Any]) -> tuple[dict, list[dict]]:
    """A composition's parts against its total. The composition (its parts, residual and eliminations) comes from the
    world model; every part it names needs a figure from the source, or the case is blocked naming what is missing."""
    if run.reader is None:
        raise Blocked("a reconciliation needs the world model's composition, and none was supplied")
    entity, cid = recipe["entity"], recipe["composition"]
    comp = next((c for c in run.reader.construction(entity).get("compositions", []) if c["id"] == cid), None)
    if comp is None:
        raise Blocked(f"composition {cid} is not in the world model's construction of {entity}")
    parts = [*comp["member_attribute_ids"], *[comp[k] for k in ("residual_attribute_id", "eliminations_attribute_id")
                                               if comp.get(k)]]
    figures = recipe.get("parts") or {}
    missing = [p for p in parts if p not in figures]
    if missing:
        raise Blocked(f"{cid} has parts with no figure in the source: {', '.join(missing)}")
    extra = [p for p in figures if p not in parts]
    if extra:
        raise Blocked(f"{cid} has no part {', '.join(extra)}: the source's view differs from the model's")
    values = {p: locate(figures[p], run) for p in parts}
    total = locate(recipe["total"], run)
    row_sum = sum(values.values(), Decimal(0))
    run.objects.append({"id": cid, "kind": "composition", "entity": entity, "role": comp.get("role"),
                        "total": comp["total_attribute_id"], "parts": parts})
    answer = {"row_sum": row_sum, "reported": total, "residual": abs(total - row_sum), "difference": total - row_sum,
              "reconciles": total == row_sum, "parts": values}
    trace = [{"name": "row_sum", "expression": " + ".join(parts), "inputs": plain(values), "value": plain(row_sum)},
             {"name": "difference", "expression": "reported - row_sum", "inputs": {"reported": plain(total),
                                                                                    "row_sum": plain(row_sum)},
              "value": plain(total - row_sum)}]
    env.update({"row_sum": row_sum, "reported": total, "residual": abs(total - row_sum), "difference": total - row_sum})
    return answer, trace


def run_identity(recipe: dict, run: Run, env: dict[str, Any]) -> tuple[dict, list[dict]]:
    """An identity of the world model (a difference, a product, a ratio) checked against the source: the model supplies
    the identity and its terms' roles; the source supplies every term and the reported target. The arithmetic is the
    golden bank's `eval_identity`."""
    if run.reader is None:
        raise Blocked("an identity check needs the world model's identity, and none was supplied")
    entity, iid = recipe["entity"], recipe["identity"]
    ident = next((i for i in run.reader.construction(entity).get("identities", []) if i["id"] == iid), None)
    if ident is None:
        raise Blocked(f"identity {iid} is not in the world model's construction of {entity}")
    figures = recipe.get("terms") or {}
    missing = [t["value"] for t in ident["terms"] if t["value"] not in figures]
    if missing:
        raise Blocked(f"{iid} has terms with no figure in the source: {', '.join(missing)}")
    values = {t["value"]: locate(figures[t["value"]], run) for t in ident["terms"]}
    computed = Decimal(str(eval_identity(ident, {k: float(v) for k, v in values.items()})))
    reported = locate(recipe["target"], run)
    run.objects.append({"id": iid, "kind": "identity", "entity": entity, "target": ident["target"],
                        "terms": [{"value": t["value"], "role": t["role"]} for t in ident["terms"]]})
    env.update({"identity_target": reported, "identity_computed": computed})
    answer = {"identity": ident.get("formula") or iid, "computed_target": computed, "reported_target": reported,
              "difference": reported - computed, "holds": reported == computed, "terms": values}
    trace = [{"name": "computed_target", "expression": ident.get("formula") or iid, "inputs": plain(values),
              "value": plain(computed)}]
    return answer, trace


# -- the stipulated state: update and undo ---------------------------------------------------------------------------------
class Ledger:
    """An isolated fixture state (baseline, scenario, inputs, dependent outputs) with an append-only audit log. An undo
    restores the inputs an update changed, recomputes the outputs, and is itself an audit event linked to its update."""

    def __init__(self, baseline: str, scenario: str, inputs: dict[str, Any], formulas: dict[str, str],
                 consts: dict[str, Any]) -> None:
        self.baseline, self.scenario = baseline, scenario
        self.inputs = dict(inputs)
        self.formulas, self.consts = formulas, consts
        self.audit: list[dict] = [{"seq": 0, "event": "initialize", "baseline": baseline, "scenario": scenario}]
        self._before: dict[str, dict[str, Any]] = {}

    def state(self) -> dict[str, Any]:
        env = {**self.consts, **self.inputs}
        return {**self.inputs, **{y: evaluate(f, env) for y, f in self.formulas.items()}}

    def update(self, uid: str, changes: dict[str, Any]) -> None:
        self._before[uid] = {k: self.inputs[k] for k in changes}
        self.inputs.update(changes)
        self.audit.append({"seq": len(self.audit), "event": "update", "update": uid, "from": plain(self._before[uid]),
                           "to": plain(changes)})

    def undo(self, uid: str) -> None:
        restored = self._before.pop(uid)
        self.inputs.update(restored)
        linked = next(a["seq"] for a in self.audit if a.get("update") == uid and a["event"] == "update")
        self.audit.append({"seq": len(self.audit), "event": "undo", "update": uid, "undoes": linked,
                           "restored": plain(restored)})


def run_ledger(recipe: dict, run: Run) -> tuple[dict, list[dict]]:
    spec = recipe["ledger"]
    inputs = {k: locate(v, run) for k, v in spec["inputs"].items()}
    consts = {k: locate(v, run) for k, v in (spec.get("constants") or {}).items()}
    led = Ledger(str(locate(spec["baseline"], run)), str(locate(spec["scenario"], run)), inputs, spec["formulas"], consts)
    run.baseline = {"baseline_id": led.baseline, "scenario_id": led.scenario}
    updates = {u: {k: locate(v, run) for k, v in ch.items()} for u, ch in spec["updates"].items()}
    uid, changes = next(iter(updates.items()))
    before = led.state()
    led.update(uid, changes)
    after = led.state()
    led.undo(uid)
    restored = led.state()
    answer: dict[str, Any] = {}
    for tag, st in (("before", before), ("updated", after), ("restored", restored)):
        answer |= {f"{tag}_{k}": v for k, v in st.items()}
    answer |= {"restored_equals_before": restored == before, "audit_events": len(led.audit),
               "audit_retained": [a["event"] for a in led.audit] == ["initialize", "update", "undo"],
               "undo_linked_to_update": led.audit[-1]["undoes"] == led.audit[1]["seq"], "audit": led.audit}
    trace = [{"name": f"{y}", "expression": f, "inputs": plain({**consts, **inputs}), "value": plain(before[y])}
             for y, f in spec["formulas"].items()]
    return answer, trace


# -- operations on a clean world ------------------------------------------------------------------------------------------
def run_ingest_repeat(recipe: dict, run: Run) -> dict:
    """Import the same source twice into one clean world: a repeated import must not add documents, bundles or signals."""
    if run.services is None:
        raise Blocked("this case needs a clean world to import into, and none was supplied")
    spec = recipe["ingest_repeat"]
    data = str(locate(spec["document"], run)).encode("utf-8")
    svc = run.services()
    first = svc.upload(spec["name"], data)
    after_first = {"documents": len(svc.documents()), "bundles": len(svc.bundles())}
    second = svc.upload(spec["name"], data)
    after_second = {"documents": len(svc.documents()), "bundles": len(svc.bundles())}
    run.objects.append({"id": first["document_id"], "kind": "document", "entity": None})
    return {"documents_after_first_import": after_first["documents"], "documents_after_second_import": after_second["documents"],
            "bundles_after_first_import": after_first["bundles"], "bundles_after_second_import": after_second["bundles"],
            "same_document_id": first["document_id"] == second["document_id"],
            "signals_first": first["signals"], "signals_second": second["signals"],
            "duplicate_documents_created": after_second["documents"] - after_first["documents"],
            "duplicate_bundles_created": after_second["bundles"] - after_first["bundles"],
            "unique_economic_records": after_second == after_first,
            "computed_totals_unchanged_after_identical_reimport": after_second == after_first
            and first["signals"] == second["signals"]}


def run_ingest_order(recipe: dict, run: Run) -> dict:
    """The same records, ingested in two orders into two clean stores, then queried at one information cutoff. Both
    stores must select the same current record and keep the superseded one. A store that cannot state an explicit
    supersession cannot be given the fixture, so the case is blocked."""
    if run.stores is None:
        raise Blocked("this case needs clean stores to ingest into, and none was supplied")
    fx = run.suite.fixtures[run.case["test_id"]]["fixture_inputs"]
    records = {r["id"]: r for r in fx["source_records"]}
    out: dict[str, Any] = {}
    for name, ops in fx["operations"].items():
        store = run.stores()
        if not store.can_state_supersession:
            raise Blocked("the store cannot record that one source explicitly corrects and supersedes another "
                          "(the bundle contract has no such field), so the fixture cannot be ingested")
        as_of = date.today()
        for op in ops:
            words = op.split()
            if words[0] == "ingest":
                store.ingest(records[words[1]])
            else:
                as_of = parse_date(re.search(r"\d{4}-\d{2}-\d{2}", op)[0])
        cur = store.current(as_of)
        out[f"store_{name}_current"] = cur["value"]
        out[f"store_{name}_current_source"] = cur["id"]
        out[f"store_{name}_history"] = sorted(h["id"] for h in store.history())
    names = list(fx["operations"])
    first_name, last_name = names[0], names[-1]
    out["same_current_record"] = out[f"store_{first_name}_current_source"] == out[f"store_{last_name}_current_source"]
    out["history_retained"] = all(sorted(records) == out[f"store_{n}_history"] for n in names)
    return out


# -- the review gates ------------------------------------------------------------------------------------------------------
def review_mapping(recipe: dict, run: Run, env: dict[str, Any]) -> dict:
    """Classify candidate mapping artifacts for approval. A mapping is refused when it carries a coefficient calibrated
    for another business, or has no evidence from the business it maps; one that rests on supplied terms is approved
    for what it computes, with the unquantified downstream named."""
    fx = run.suite.fixtures[run.case["test_id"]]["fixture_inputs"]
    findings: dict[str, Any] = {}
    for name in recipe["review"]["candidates"]:
        cand = fx[name]
        issues = []
        if cand.get("coefficient_origin"):
            issues.append(f"coefficient from {cand['coefficient_origin']}")
        if "insurer_evidence" in cand and not cand["insurer_evidence"]:
            issues.append("no evidence from the business it maps")
        findings[name] = ({"decision": "reject", "reasons": issues} if issues else
                          {"decision": "approve_with_limits", "reasons": [],
                           "unquantified": list(cand.get("downstream_unsupplied") or [])})
    return {"candidates": findings}


def review_golden(recipe: dict, run: Run, env: dict[str, Any]) -> dict:
    """Which candidate golden record is eligible. A record is eligible when its expected answer has an origin outside
    the model and the independent calculation agrees. The review artifacts the fixture requires are then checked: the
    ones this run can supply (the independent arithmetic, the runner's access report) are attached; a required artifact
    it cannot supply makes the approval conditional, naming it."""
    spec = recipe["review"]
    oracle = evaluate(spec["oracle"], env)
    fx = run.suite.fixtures[run.case["test_id"]]["fixture_inputs"]
    findings: dict[str, Any] = {}
    for name in spec["candidates"]:
        cand = fx[name]
        reasons = []
        if cand.get("expected_answer_origin") == "same model output":
            reasons.append("expected answer copied from the model's own output")
        if not (cand.get("independent_verification") or cand.get("claimed_controls")):
            reasons.append("no independent verification record")
        if Decimal(str(cand.get("expected_answer"))) != oracle:
            reasons.append("expected answer differs from the independent calculation")
        findings[name] = {"eligible": not reasons, "reasons": reasons, "claimed_controls": list(cand.get("claimed_controls") or [])}
    supplied = list(spec.get("supplies") or [])
    required = list(fx.get("required_review_artifacts") or [])
    missing = [a for a in required if a not in supplied]
    for f in findings.values():
        f["decision"] = ("ineligible" if not f["eligible"] else "eligible_conditional" if missing else "eligible")
    access = run.suite.access.report()
    return {"candidates": findings, "independent_oracle": oracle,
            "artifacts": {"required": required, "supplied_by_this_run": [a for a in required if a in supplied],
                          "not_supplied": missing},
            "access_evidence": {"roots": access["roots"], "files_read": len(access["files_read"])}}


# -- one case --------------------------------------------------------------------------------------------------------------
def na(reason: str) -> dict:
    return {"applicable": False, "reason": reason}


def answer_case(suite: Suite, case: dict, recipe: dict | None, reader: Reader | None,
                services: Any = None, stores: Any = None) -> dict:
    """One case's answer in our own fields; raises Blocked when it cannot be run."""
    if recipe is None:
        raise Blocked("no recipe: the runner has no plan for this operation")
    op = recipe.get("op", "calc")
    if op == "blocked":
        raise Blocked(recipe["reason"])
    run = Run(suite, case, reader, services, stores)
    env = gather(recipe, run)
    answer: dict[str, Any] = {}
    trace: list[dict] = []
    if op == "ledger":
        answer, trace = run_ledger(recipe, run)
    elif op == "reconcile":
        answer, trace = reconcile(recipe, run, env)
    elif op == "identity":
        answer, trace = run_identity(recipe, run, env)
    elif op == "ingest_repeat":
        answer = run_ingest_repeat(recipe, run)
    elif op == "ingest_order":
        answer = run_ingest_order(recipe, run)
    elif op == "review_mapping":
        answer = review_mapping(recipe, run, env)
    elif op == "review_golden":
        answer = review_golden(recipe, run, env)
    computed, steps = calculate(recipe, env)
    answer |= computed
    trace += steps
    for name in recipe.get("hide") or []:
        answer.pop(name, None)
    for name in recipe.get("show") or []:
        answer[name] = env[name]
    answer |= {k: locate(v, run) if isinstance(v, dict) else as_value(v) for k, v in (recipe.get("facts") or {}).items()}
    bind_objects(recipe, run)
    unknowns = list(recipe.get("unknowns") or [])
    if unknowns:
        answer["unresolved"] = unknowns
    grounding = {"model_objects": [o["id"] for o in run.objects], "source_excerpts": sorted(run.evidence),
                 "computed": sorted(recipe.get("compute") or []), "stated": sorted(recipe.get("facts") or []),
                 "operation": op}
    return {
        "grounding": grounding,
        "answer": plain(answer),
        "scope": {**{k: recipe[k] for k in ("period", "unit", "units", "scope", "currency", "basis") if k in recipe},
                  **({} if any(k in recipe for k in ("period", "unit", "scope")) else na("no period, unit or scope"))},
        "evidence_and_objects": {"evidence": sorted(run.evidence.values(), key=lambda e: e["excerpt_id"]),
                                 "objects": run.objects} if run.evidence or run.objects
        else na(recipe.get("no_evidence_reason", "a stipulated fixture: no source is needed")),
        "calculations": trace,
        "baseline": run.baseline or recipe.get("baseline") or na(recipe.get("no_baseline_reason",
                                                             "isolated fixture arithmetic: no baseline is selected")),
        "assumptions_and_missing": {"assumptions": list(recipe.get("assumptions") or []), "unresolved": unknowns},
        "mechanism": recipe.get("mechanism"),
    }


def to_contract(case: dict, status: str, internal: dict | None, reason: str, required: tuple[str, ...]) -> dict:
    """Our fields mapped onto the suite's. `internal` keeps ours as they are."""
    out: dict[str, Any] = {"test_id": case["test_id"], "status": status, "reason": reason}
    for label in required:
        if label in FIELD_MAP:
            out[label] = (internal or {}).get(FIELD_MAP[label], na(reason or "not answered"))
    out["quantities"] = (internal or {}).get("quantities", [])
    out["family"] = case.get("failure_family")
    out["scorecard_group"] = case.get("scorecard_group")
    out["internal"] = internal or {}
    return out


def run_suite(suite: Suite, recipes: dict[str, dict], reader: Reader | None = None, only: list[str] | None = None,
              skip: dict[str, str] | None = None, services: Any = None, stores: Any = None) -> dict:
    """Answer every case (or `only` those named). `skip` names cases not to run, each with its reason (`not_run`)."""
    skip = skip or {}
    reader = Cached(reader) if reader is not None else None
    results = []
    for case in suite.cases:
        tid = case["test_id"]
        if only and tid not in only:
            continue
        required = tuple(suite.fixtures.get(tid, {}).get("required_output_fields") or CONTRACT_FIELDS)
        if tid in skip:
            results.append(to_contract(case, NOT_RUN, None, skip[tid], required))
            continue
        try:
            internal = answer_case(suite, case, recipes.get(tid), reader, services, stores)
            results.append(to_contract(case, ANSWERED, internal, "", required))
        except Blocked as b:
            results.append(to_contract(case, BLOCKED, None, str(b), required))
    return {"suite_id": suite.meta.get("suite_id"), "suite_version": suite.meta.get("version"),
            "adapter_field_policy": suite.meta.get("adapter_field_policy"), "field_map": FIELD_MAP,
            "results": results, "access": suite.access.report()}


def dumps(run: dict) -> str:
    """Byte-stable JSON: sorted keys, fixed indent, no timestamps."""
    return json.dumps(run, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
