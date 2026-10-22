"""The inner-loop suite's grader (Oct 22): the runner's results against the answer key, as the suite's scorecard.

This is the only code that is handed the answer key, and it takes its path as an explicit argument (`grade(results,
key_path, ...)`); the runner (inner_loop.py) never names it and cannot read it.

What it produces. A status for every case, each with a reason: `pass`, `fail`, `blocked` or `not_run`.

- executed pass rate = pass / (pass + fail); execution coverage = (pass + fail) / main cases (98);
- blocked and not-run cases are counted apart, with their reasons, and are never a pass;
- the two review gates (the cases the key puts in the `review_gate` group) have their own section;
- a high pass rate does not resolve a material blocked or failed requirement, and the scorecard says so.

How a case is graded. Three kinds of check, kept apart; a case passes only when every applicable one does, so a
correct endpoint reached through a wrong bridge fails.

- values: each expected value of the numeric oracle is matched to our field of the same meaning, at the *displayed
  precision* of the expected value (a value written with four decimals is compared at four). A tolerance is used only
  where the clarifications allow one: a one-million-yen rounding residual, and 0.005 percentage point for the
  automotive margin; anything else is exact.
- assertions: each `name=value` of the acceptance check that is not an oracle value (a date, a flag, a refusal, a
  classification) must be returned under a field of the same meaning. They fall into three facets by what they say:
  mechanism, accounting destination, and proof limits; the rest are plain assertions.
- unknowns: an expected unknown must be returned as an unresolved input, not as a number.

Detail. For a development case the scorecard keeps expected and actual beside each failed check, for diagnosis. For a
validation candidate it keeps the status only: the builder sees pass and fail counts, never an expected answer.
"""

from __future__ import annotations

import inspect
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from axelrod_wm.evaluation import inner_loop, inner_loop_packets, inner_loop_tools

STATUSES = ("pass", "fail", "blocked", "not_run")
MAIN_CASES = 98
FACETS = {"mechanism": re.compile(r"mechanism|bridge|path|route|driver", re.I),
          "accounting_destination": re.compile(r"destination|account|recogni|presentation|classif|location", re.I),
          "proof_limits": re.compile(r"proof|limit|unknown|undetermined|status|determin|established", re.I)}
ONE_MILLION_YEN = Decimal(1)
ALLOWED_PP = Decimal("0.005")

NOTE = ("A high executed pass rate does not resolve a material blocked or failed requirement: blocked and not-run "
        "cases are not passes and stay open until the check can be run.")


# -- matching our fields to the key's labels -------------------------------------------------------------------------------
GENERIC = {"delta", "change", "effect", "total"}                    # words that do not say which quantity it is
STOP = {"the", "and", "for", "with", "that", "this", "from", "per", "all", "its", "are", "was", "but", "any", "only",
        "when", "then", "than", "into", "such", "each", "both", "must", "require", "assert", "reject", "flag", "check",
        "store", "keep", "explicit", "explicitly", "before", "after", "mandatory", "assertions", "assertion", "two",
        "one", "not", "has", "have", "can", "may", "also", "more", "same", "use", "yes", "set", "mark"}
DIRECTIVE = re.compile(r"(assert|require|reject|flag|preserve|no)\b", re.I)
NEGATIVE_START = ("no ", "not ", "without ", "never ", "do not ")
NEGATIVE_VALUES = {"false", "none", "null", "no", "unknown", "undetermined", "missing", "uncalibrated"}
SCALES = (("trillion", Decimal(10) ** 12), ("billion", Decimal(10) ** 9), ("million", Decimal(10) ** 6),
          ("thousand", Decimal(10) ** 3))


def norm(s: str) -> str:
    return re.sub(r"[\W_]", "", str(s).lower())


def tokens(s: str) -> set[str]:
    """The words of a name, without the generic ones (delta, change, ...) unless nothing else is left."""
    words = {t for t in re.split(r"[^a-z0-9]+", str(s).lower()) if t}
    return (words - GENERIC) or words


def stems(s: str) -> set[str]:
    spaced = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", str(s).lower())
    return {t[:5] for t in re.split(r"[^a-z0-9]+", spaced) if len(t) >= 3 and t not in STOP}


def flatten(x: Any, prefix: str = "") -> dict[str, Any]:
    """Our actual_result as leaf fields; a leaf is reachable by its own name and by its dotted path."""
    out: dict[str, Any] = {}
    if isinstance(x, dict):
        for k, v in x.items():
            out |= flatten(v, f"{prefix}{k}.")
    else:
        out[prefix[:-1]] = x
    return out


def find_field(label: str, fields: dict[str, Any]) -> tuple[str, Any] | None:
    """The field of ours that means `label`: the same name, else the only one whose words contain, or are contained in,
    the label's. Ambiguity is no match."""
    for path, v in fields.items():
        if norm(path) == norm(label) or norm(path.rsplit(".", 1)[-1]) == norm(label):
            return path, v
    want = tokens(label)
    near = [(p, v) for p, v in fields.items()
            if want and (t := tokens(p.rsplit(".", 1)[-1])) and (want <= t or t <= want)]
    return near[0] if len(near) == 1 else None


def decimals_of(x: Any) -> int:
    d = Decimal(repr(x)) if isinstance(x, float) else Decimal(x)
    return max(0, -d.as_tuple().exponent)


def to_decimal(x: Any) -> Decimal | None:
    if isinstance(x, bool) or x is None:
        return None
    try:
        return Decimal(str(x).replace(",", "").rstrip("%"))
    except ArithmeticError:
        return None


def mixed_scales(unit: Any) -> bool:
    """A key unit that names more than one scale ("billion/trillion JPY"): each of our fields carries its own."""
    return sum(word in str(unit or "").lower() for word, _ in SCALES) > 1


def unit_scale(unit: Any) -> Decimal:
    """The scale a unit string states first (million, billion, ...); none is 1."""
    text = str(unit or "").lower()
    found = sorted((text.find(word), s) for word, s in SCALES if word in text)
    return found[0][1] if found else Decimal(1)


def values_match(expected: Any, actual: Any, tol: Decimal = Decimal(0), factor: Decimal = Decimal(1)) -> bool:
    """At the expected value's displayed precision; booleans and words by their normalized text. `factor` converts our
    number into the key's unit (million yen into yen)."""
    if expected is None:
        return actual is None
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            values_match(e, a, tol, factor) for e, a in zip(expected, actual, strict=True))
    e, a = to_decimal(expected), to_decimal(actual)
    if e is not None and a is not None:
        places = Decimal(1).scaleb(-decimals_of(expected))
        return abs((a * factor).quantize(places) - e.quantize(places)) <= tol
    if isinstance(expected, bool) or isinstance(actual, bool):
        return norm(expected) == norm(actual)
    return bool(norm(expected)) and norm(expected) in norm(actual)


def tolerance(case: dict, oracle: dict) -> Decimal:
    """The key's absolute tolerance, kept only where the clarifications name one."""
    tol = to_decimal(oracle.get("absolute_tolerance")) or Decimal(0)
    million_yen = "million" in str(oracle.get("unit", "")).lower() and "jpy" in str(oracle.get("unit", "")).lower()
    if case["test_id"].endswith("02-08"):
        return min(tol, ALLOWED_PP)
    return min(tol, ONE_MILLION_YEN) if million_yen else Decimal(0)


def facet_of(name: str) -> str:
    return next((f for f, rx in FACETS.items() if rx.search(name)), "assertions")


# -- the key's assertions --------------------------------------------------------------------------------------------------
def last_segment(raw: str) -> str:
    """The end of a chain `a*b=c` (the value the chain comes to); an `=` inside brackets does not split it."""
    depth, cut = 0, 0
    for k, ch in enumerate(raw):
        depth += {"(": 1, ")": -1, "[": 1, "]": -1}.get(ch, 0)
        if ch == "=" and depth == 0:
            cut = k + 1
    return raw[cut:]


def scan_pairs(text: str) -> tuple[list[tuple[str, str]], str]:
    """`name=value` assertions (a value may be an expression or a chain `a*b=c`), and the text without them."""
    pairs, rest, i = [], [], 0
    for m in re.finditer(r"(?<![\w=])([A-Za-z_][\w.]*)=", text):
        if m.start() < i:
            continue
        j, depth = m.end(), 0
        while j < len(text) and (depth > 0 or text[j] not in " ,;"):
            depth += {"(": 1, ")": -1, "[": 1, "]": -1}.get(text[j], 0)
            j += 1
        raw = text[m.end():j].rstrip(".")
        pairs.append((m.group(1), last_segment(raw)))
        rest.append(text[i:m.start()])
        i = j
    return pairs, " ".join([*rest, text[i:]])


def expected_of(raw: str) -> Any:
    """An assertion's value: a number (an expression is evaluated), a flag, or a word."""
    try:
        return inner_loop.evaluate(raw, {})
    except inner_loop.Blocked:
        return {"true": True, "false": False, "null": None}.get(raw.lower(), raw)


def clauses(text: str) -> list[tuple[set[str], bool]]:
    """What the prose of an acceptance check requires, as (content stems, negative). A sentence's leading verb (Reject
    makes it negative) is dropped; a clause is a part split at ' and ' and commas."""
    out = []
    for sentence in re.split(r"[.;:]\s+|[.;:]$", text):
        body = sentence.strip()
        if not DIRECTIVE.match(body):
            continue                  # narrative and the assertions already checked as values
        reject = bool(re.match(r"(reject|no)\b", body, re.I))
        body = re.sub(r"^(assert|require|reject|flag|preserve)\b\s*", "", body, flags=re.I)
        for part in re.split(r",\s+|\s+and\s+|\s+before\s+", body):
            asked = re.match(r"(require|assert|flag|check)\b", part, re.I)
            st = stems(part)
            if st:
                out.append((st, (reject and not asked) or part.lower().startswith(NEGATIVE_START)))
    return out


def haystack(result: dict, fields: dict[str, Any]) -> list[tuple[set[str], Any]]:
    """Every statement our result makes, as (stems of its name and its words, value): fields, assumptions, trace inputs."""
    def words(v: Any) -> set[str]:
        return stems(v) if isinstance(v, (str, int, float)) and not isinstance(v, bool) else set()

    hay = [(stems(p.replace(".", " ").replace("_", " ")) | words(v), v) for p, v in fields.items()]
    scope = result.get("scope_period_units_when_applicable") or {}
    hay += [(stems(k.replace("_", " ")) | words(v), v) for k, v in flatten(scope).items()]
    for step in result.get("calculation_trace_when_applicable") or []:
        # an answer's calculation is {expression, inputs, value}; a recipe run's also has a name
        label = step.get("name") or step.get("expression", "")
        named = {s for k, v in (step.get("inputs") or {}).items() for s in stems(k.replace("_", " ")) | words(v)}
        hay.append((stems(label.replace("_", " ")) | words(step.get("value")) | named, step.get("value")))
    return hay


def negative(value: Any) -> bool:
    return value is None or value is False or value == 0 or str(value).lower().split(" ")[0] in NEGATIVE_VALUES


def clause_ok(st: set[str], neg: bool, hay: list[tuple[set[str], Any]]) -> bool:
    """Most of the clause's stems appear among our statements (all of them when it has two or fewer); a negative clause
    also needs the statement that carries them to say no."""
    have = set().union(*(h for h, _ in hay)) if hay else set()
    need = len(st) if len(st) <= 2 else -(-len(st) * 6 // 10)
    if len(st & have) < need:
        return False
    return not neg or any(negative(v) for h, v in hay if h & st)


# -- one case --------------------------------------------------------------------------------------------------------------
def check_case(case: dict, result: dict) -> tuple[bool, dict[str, dict], list[dict]]:
    """(passes, per-facet status, failed checks with expected and actual)."""
    actual = result.get("actual_result") or {}
    fields = flatten(actual)
    oracle = case.get("numeric_oracle") or {}
    tol = tolerance(case, oracle)
    scope = result.get("scope_period_units_when_applicable") or {}
    scope = scope if oracle.get("unit") else {}

    def factor_for(path: str) -> Decimal:
        """Our number in the key's unit: the scale of our unit for this field (the recipe's `units`, else its `unit`)."""
        ours = (scope.get("units") or {}).get(path.rsplit(".", 1)[-1], scope.get("unit"))
        if mixed_scales(oracle.get("unit")):
            return Decimal(1)                                      # the key's fields are in their own scales: ours are too
        return unit_scale(ours) / unit_scale(oracle.get("unit"))   # no unit in the key: the numbers are compared as given

    expected_values = oracle.get("expected_values") or {}
    facets: dict[str, dict] = {}
    failed: list[dict] = []

    def record(facet: str, label: str, expected: Any, got: Any, ok: bool) -> None:
        f = facets.setdefault(facet, {"checked": 0, "failed": 0})
        f["checked"] += 1
        if not ok:
            f["failed"] += 1
            failed.append({"facet": facet, "label": label, "expected": expected, "actual": got})

    for label, expected in expected_values.items():
        hit = find_field(label, fields)
        record("values", label, expected, None if hit is None else hit[1],
               hit is not None and values_match(expected, hit[1], tol, factor_for(hit[0])))
    covered = {to_decimal(v) for v in expected_values.values()} - {None}
    pairs, prose = scan_pairs(case.get("acceptance_check", ""))
    for name, raw in pairs:
        value = expected_of(raw)
        d = to_decimal(value)
        if d is not None and d in covered:
            continue
        if isinstance(value, str) and re.search(r"[-+*/]", value):          # a formula: the prose's way of saying a bridge
            prose += f". Assert {name} {value}"
            continue
        hit = find_field(name, fields)
        record(facet_of(name), name, plain_text(value), None if hit is None else hit[1],
               hit is not None and values_match(value, hit[1], Decimal(0), factor_for(hit[0]) if d is not None else Decimal(1)))
    for expected in oracle.get("expected_unknowns") or []:
        hit = find_field(expected, fields)
        record("proof_limits", f"unknown: {expected}", "no determined value, with the missing inputs named",
               None if hit is None else hit[1],
               hit is not None and to_decimal(hit[1]) is None and bool(fields.get("unresolved")))
    hay = haystack(result, fields)
    for st, neg in clauses(prose):
        record(facet_of(" ".join(st)), ("not " if neg else "") + " ".join(sorted(st)), "stated", None,
               clause_ok(st, neg, hay))
    ok = bool(facets) and all(f["failed"] == 0 for f in facets.values())
    return ok, facets, failed


def plain_text(value: Any) -> Any:
    return inner_loop.plain(value)


def grade_case(case: dict, result: dict | None, validation: bool) -> dict:
    """One case's scorecard row. A case the runner did not report is not run."""
    row: dict[str, Any] = {"test_id": case["test_id"], "family": case["failure_family"],
                           "family_id": case["family_id"], "group": case["scorecard_group"],
                           "split": case["development_split"]}
    if result is None or result["status"] == inner_loop.NOT_RUN:
        return row | {"status": "not_run", "reason": (result or {}).get("reason") or "the runner did not report it"}
    if result["status"] == inner_loop.BLOCKED:
        return row | {"status": "blocked", "reason": result["reason"]}
    ok, facets, failed = check_case(case, result)
    g = result.get("internal", {}).get("grounding", {})
    row |= {"status": "pass" if ok else "fail", "facets": facets,
            "grounding": {"operation": g.get("operation"), "model_objects": len(g.get("model_objects", [])),
                          "source_excerpts": len(g.get("source_excerpts", [])), "stated_facts": len(g.get("stated", []))}}
    if validation:
        return row | {"reason": "validation candidate: detail withheld"}
    reason = "every applicable check passed" if ok else "; ".join(
        f"{f['facet']}: {f['label']}" for f in failed) or "no check could be made"
    return row | {"reason": reason, "detail": failed, "key_text": {"precise_answer": case.get("precise_answer"),
                                                                   "acceptance_check": case.get("acceptance_check")}}


# -- the scorecard ---------------------------------------------------------------------------------------------------------
def rates(rows: list[dict]) -> dict:
    n = {s: sum(r["status"] == s for r in rows) for s in STATUSES}
    ran = n["pass"] + n["fail"]
    return n | {"executed": ran, "executed_pass_rate": None if not ran else round(n["pass"] / ran, 4),
                "execution_coverage": round(ran / MAIN_CASES, 4)}


def transcript_scan(key_path: Path, results: dict, forbid: tuple[str, ...] = ()) -> dict:
    """What the agents' transcripts show: for each marker (the key's path and file name, and any the caller adds, such as
    the folder name of held-out data), how many transcripts mention it. A transcript that cannot be read is counted."""
    markers = [m for m in (str(Path(key_path)), Path(key_path).name, *forbid) if m]
    texts, unreadable = [], 0
    for t in results.get("transcripts", []):
        try:
            texts.append(Path(t["path"]).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            unreadable += 1
    return {"transcripts_scanned": len(texts), "transcripts_unreadable": unreadable,
            "mentions": {m: sum(m in t for t in texts) for m in markers}}


def separation_evidence(key_path: Path, results: dict, forbid: tuple[str, ...] = ()) -> dict:
    """The evidence for answer-key separation, taken outside the runner: the files it reports reading, against the key's
    own folder, the source of the runner's modules against the key's path and names, and what the agents' transcripts say."""
    key_dir = Path(key_path).resolve().parent
    read = [Path(f["path"]).resolve() for f in results["access"]["files_read"]]
    source = "".join(inspect.getsource(m) for m in (inner_loop, inner_loop_packets, inner_loop_tools))
    names = [p for p in (key_dir.name, Path(key_path).name) if p]
    scan = transcript_scan(key_path, results, forbid)
    return {"runner_read_files": len(read),
            "runner_read_anything_under_key_folder": any(p.is_relative_to(key_dir) for p in read),
            "runner_roots_exclude_key_folder": not any(key_dir.is_relative_to(Path(r)) or Path(r).is_relative_to(key_dir)
                                                       for r in results["access"]["roots"]),
            "runner_source_names_key_location": any(n in source for n in names),
            "grader_takes_key_path_as_argument": "key_path" in inspect.signature(grade).parameters,
            "transcripts": scan, "no_transcript_mentions_the_key": not any(scan["mentions"].values())}


def grade(results: dict, key_path: Path, run: str = "run", forbid: tuple[str, ...] = (),
          only: tuple[str, ...] = ()) -> dict:
    """The scorecard for `results` (the runner's output) against the key at `key_path`."""
    key = json.loads(Path(key_path).read_text(encoding="utf-8"))
    by_id = {r["test_id"]: r for r in results["results"]}
    rows = [grade_case(c, by_id.get(c["test_id"]), c["development_split"] != "development") for c in key["cases"]
            if not only or c["test_id"] in only]
    main = [r for r in rows if r["group"] != "review_gate"]
    gates = [r for r in rows if r["group"] == "review_gate"]
    families: dict[str, dict] = {}
    for r in main:
        families.setdefault(f"{r['family_id']:02d} {r['family']}", []).append(r)
    review = {"cases": gates, "counts": rates(gates) | {"note": "own section; not in the main rates"}}
    for g in gates:
        if g["test_id"].endswith("10"):
            review["answer_key_separation"] = separation_evidence(key_path, results, forbid)
    return {"run": run, "suite_id": key["suite_id"], "version": key["version"],
            "main": rates(main) | {"cases": len(main)},
            "by_family": {k: rates(v) | {"cases": len(v)} for k, v in sorted(families.items())},
            "blocked": sorted({(r["test_id"], r["reason"]) for r in main if r["status"] == "blocked"}),
            "not_run": sorted({(r["test_id"], r["reason"]) for r in main if r["status"] == "not_run"}),
            "review_gates": review, "cases": main, "note": NOTE, "graded_inputs": results.get("answers"),
            "only": list(only) or None,
            "tolerances": "exact at displayed precision; one million yen for rounding residuals; 0.005 percentage "
                          "point for the automotive margin"}


def markdown(card: dict) -> str:
    m = card["main"]
    pct = lambda x: "n/a" if x is None else f"{100 * x:.1f}%"      # noqa: E731
    answers = card.get("graded_inputs")
    lines = [f"# Inner-loop accuracy scorecard: {card['suite_id']} v{card['version']} ({card['run']})", "",
             *([f"Graded answers: `{answers['dir']}` ({answers['files']} files, sha256 `{answers['sha256']}`)", ""] if answers else []),
             "## Main scorecard", "",
             "| pass | fail | blocked | not run | executed pass rate | execution coverage |", "|---|---|---|---|---|---|",
             f"| {m['pass']} | {m['fail']} | {m['blocked']} | {m['not_run']} | {pct(m['executed_pass_rate'])} "
             f"({m['pass']}/{m['executed']}) | {pct(m['execution_coverage'])} ({m['executed']}/{MAIN_CASES}) |", "",
             card["note"], "", "## By family", "",
             "| family | pass | fail | blocked | not run |", "|---|---|---|---|---|"]
    lines += [f"| {k} | {v['pass']} | {v['fail']} | {v['blocked']} | {v['not_run']} |" for k, v in card["by_family"].items()]
    lines += ["", "## Cases", "", "| case | status | reason |", "|---|---|---|"]
    lines += [f"| {r['test_id']} | {r['status']} | {r['reason'].replace('|', '/')} |" for r in card["cases"]]
    g = card["review_gates"]
    lines += ["", "## Review checks (10-09 and 10-10), scored separately", "",
              "| case | status | reason |", "|---|---|---|"]
    lines += [f"| {r['test_id']} | {r['status']} | {r['reason'].replace('|', '/')} |" for r in g["cases"]]
    if "answer_key_separation" in g:
        lines += ["", "Answer-key separation, by evidence:", ""]
        lines += [f"- {k}: {v}" for k, v in g["answer_key_separation"].items()]
    return "\n".join(lines) + "\n"
