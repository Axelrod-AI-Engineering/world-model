"""The inner-loop accuracy suite's shared parts (Oct 22): the suite, the read guard, the calculator, and the contract.

The suite is a bank of cases (a question, its family, the frozen page excerpts it is bound to) plus the stipulated
inputs of the cases that need them (`fixture_inputs`) and an index of the frozen excerpts (source, version, hashes,
availability date, page). Answering is done by an agent that reads a task packet (inner_loop_packets.py), not by code here;
this module holds what the packets, the tools and the grader share:

- `Access`: every file the runner side reads goes through it, refused outside the roots it was given (the suite folder, the
  packets) and logged with its hash. The answer key lives outside those roots; no module on the runner side names it, a test
  asserts their text, and the grader (inner_loop_grade.py) is the only code handed its path.
- `Suite`, `load_suite`: the questions-only bank, its fixtures and source index, with each frozen page checked against the hash
  the index froze.
- The calculator: Decimal arithmetic in a restricted expression language (+ - * / ** min max abs round sum, if/else,
  comparisons, dates), deterministic, with no clock and no random source.
- The contract: the suite's output fields (`required_output_fields`) are semantic targets, not a schema. `FIELD_MAP` maps our own
  fields (`answer`, `scope`, `objects`, ...) onto them, and a field a case does not exercise says so with a reason instead of an
  invented baseline. Our schema is not renamed: the result keeps it under `internal`.
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
from typing import Any

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


NUMBER = re.compile(r"\(?[-−]?\d[\d,]*(?:\.\d+)?\)?")


def parse_number(token: str) -> Decimal:
    """'1,234,567' -> 1234567; '(12,345)' -> -12345; a unicode minus is a minus."""
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
    """A constant as the calculator's value: numbers are Decimals."""
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


def na(reason: str) -> dict:
    return {"applicable": False, "reason": reason}


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


def dumps(run: dict) -> str:
    """Byte-stable JSON: sorted keys, fixed indent, no timestamps."""
    return json.dumps(run, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
