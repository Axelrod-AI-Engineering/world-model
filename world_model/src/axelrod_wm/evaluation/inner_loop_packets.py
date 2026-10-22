"""The inner-loop suite as a file protocol (Oct 22): task packets out, answer files back.

The system under test is an agent that reads our export the way an analyst's agent does. It is a person-like reader with a
folder, not code in this repository, so the runner does two things and answers nothing itself:

    prepare   one packet per case under <packets>/<test_id>/, and the shared, read-only export beside them
    collect   read <packets>/answers/<test_id>.json, check it against the schema, and return the suite's contract

A packet holds `task.md` (the question, the return contract and field policy, generic instructions: no case-specific hint),
`fixture_inputs.json` when the case has stipulated inputs, `excerpts/` (copies of the frozen pages bound to that case, the
admissible source evidence) with `excerpt_index.json`, and `answer.schema.json`. An invalid or missing answer is `blocked`
with the reason; an answer's own `blocked` is kept with its stated reason; a case is never given a guess.

Separation. Packets are built only from the suite folder (through the runner's guard and read log); the answer key is never
an input, and this module never names it. `collect` records which answers were graded (the folder and a sha256 over every
file) and the agents' transcripts (path and hash), so the grader can report from evidence what the agents opened. The same
answers give byte-identical results: nothing here reads a clock or a random source.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from axelrod_wm.evaluation import inner_loop as il

STATUSES = ("answered", "blocked")


def answer_schema() -> dict:
    """What an answer file holds. Field names inside `answer` are the quantity's own meaning; units are stated, not implied."""
    text = {"type": "string"}
    strings = {"type": "array", "items": text}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema", "title": "One case's answer", "type": "object",
        "required": ["test_id", "status"], "additionalProperties": False,
        "properties": {
            "test_id": text,
            "status": {"type": "string", "enum": list(STATUSES),
                       "description": "answered: the check was run (an undetermined result is a valid answer). blocked: it cannot be run."},
            "reason": {**text, "description": "required when blocked: the missing source, input or operation"},
            "answer": {"type": "object", "description": "the result: one field per quantity or assertion, named by its meaning"},
            "unit": {**text, "description": "the unit of the numbers in `answer` unless `units` says otherwise"},
            "units": {"type": "object", "description": "field name to unit, where a field differs from `unit`"},
            "period": text,
            "scope": {"type": "object", "description": "entity, perimeter, currency, basis, geography as they matter"},
            "baseline": {"type": "object", "description": "selected baseline, scenario and version, when the case exercises one"},
            "evidence": {"type": "array", "items": {
                "type": "object", "required": ["excerpt_id", "location", "passage"], "additionalProperties": False,
                "properties": {"excerpt_id": text, "location": text, "passage": {**text, "description": "quoted from the page"}}}},
            "objects": {**strings, "description": "ids of the model objects the answer rests on"},
            "assumptions": strings,
            "missing_inputs": {**strings, "description": "what the case leaves undetermined"},
            "calculations": {"type": "array", "items": {
                "type": "object", "required": ["expression", "value"], "additionalProperties": False,
                "properties": {"expression": text, "inputs": {"type": "object"}, "value": {}}}},
        }}


def validate(x: Any, schema: dict, where: str = "$") -> list[str]:
    """The schema's problems with `x`: the subset of JSON Schema `answer_schema` uses (type, enum, required, properties,
    additionalProperties, items)."""
    kinds = {"object": dict, "array": list, "string": str}
    t = schema.get("type")
    if t and not isinstance(x, kinds[t]):
        return [f"{where}: expected {t}"]
    if "enum" in schema and x not in schema["enum"]:
        return [f"{where}: {x!r} is not one of {schema['enum']}"]
    out: list[str] = []
    if t == "object":
        props = schema.get("properties", {})
        out += [f"{where}: missing {k}" for k in schema.get("required", []) if k not in x]
        if schema.get("additionalProperties") is False:
            out += [f"{where}: unexpected field {k}" for k in sorted(set(x) - set(props))]
        for k in sorted(set(x) & set(props)):
            out += validate(x[k], props[k], f"{where}.{k}")
    if t == "array":
        for i, v in enumerate(x):
            out += validate(v, schema["items"], f"{where}[{i}]")
    return out


# -- the task --------------------------------------------------------------------------------------------------------------
def task_text(case: dict, fixture: dict | None, index: list[dict], paths: dict[str, str], policy: str, tools: str) -> str:
    """The packet's task.md. Everything below the question is the same for every case."""
    inputs = [f"- `{paths['packet']}/fixture_inputs.json`: stipulated inputs for this case. Treat them as given, and as the only "
              "figures the question supplies." if fixture is not None else "- No fixture inputs: the question states everything it stipulates."]
    inputs.append("- `excerpts/`: copies of the frozen source pages bound to this case, with `excerpt_index.json` (source, version, "
                  "availability date, pages). They are the only admissible source evidence; a figure from anywhere else is not evidence."
                  if index else "- No source pages are bound to this case: it is answered from the question, the fixture, the export and the model.")
    return f"""# Case {case['test_id']}

You are answering one case of an accuracy suite for a company's world model. Answer from this packet, the shared export and the
read-only tools below. Read only files inside this packet and the shared export. Do not read any file that could hold expected
answers, and do not try to find one.

## Question

{case['question']}

## Inputs

{chr(10).join(inputs)}
- The shared export (read-only): `{paths['export']}`. Its `reading/` shards, domain pack, evidence packs and source catalogue are what
  an analyst's agent would open: use `export-search` first, then `export-read`.

## Tools (run from the repository root; all read-only)

```
{tools} calc --expr "a * b / 100" --input a=1,234 --input b=5 --log {paths['packet']}/calc_log.jsonl
{tools} export-list --export {paths['export']} [--prefix reading/]
{tools} export-search --export {paths['export']} "operating income" [--limit 20]
{tools} export-read --export {paths['export']} reading/00_START_HERE.md [--start 0 --length 20000]
{tools} model-get --memo {paths['memo']} /search --param q=toyota --param mode=graph
{tools} model-get --memo {paths['memo']} /entities/<entity>/attributes/<key>/observations --param as_of=<ISO time>
{tools} model-get --memo {paths['memo']} /evidence/<id>
{tools} model-construction --memo {paths['memo']} <entity> <compositions|identities|attributes|paths|stock_flows|links> [--match <word>]
{tools} op-ingest-orders --payload <json file>
{tools} op-update-undo --payload <json file>
```

- `calc` is a Decimal calculator: do every calculation with it, never in your head. Numbers may be written as printed
  (`1,234`, `(285,617)`); dates as `YYYY-MM-DD`. `--log` records the calculation for the collector.
- `model-get` reads the world under test (an uncached read starts the world in process and takes about half a minute; ask in one
  batch where you can). `as_of` selects the model's state at a time; observations carry `available_at`.
- `op-*` run the two operations a state case needs on clean temporary worlds. If the system cannot run one, the tool says
  `supported: false` and why. Report that; never simulate the operation yourself.

## How to answer

1. Find what the case needs in the order: the question and fixture, the bound pages, the export, the model. Quote the passage you
   rely on (page id, where on the page, the words).
2. Name each field of `answer` by the meaning of the quantity (`snake_case`), give numbers as JSON numbers, and state the unit in
   `unit` or `units` (a number in million yen is not a number in yen). Keep the precision the source displays.
3. Keep apart what the case asks apart: the value, its definition and scope, the mechanism by which an effect arises, the account
   it lands in and when, and what the evidence cannot prove. Put each in its own field when the question touches it.
4. Respect time: a source is usable at a date only if it was available by then; use `as_of` and `available_at`.
5. Never invent an input. If something needed is missing, list it in `missing_inputs`. A result that is genuinely undetermined by
   the stipulated inputs is a valid answer: give the field as `null` or `"undetermined"`, say why, and name what is missing. If you
   cannot run the specified check at all (no source, no operation), set `status` to `blocked` and state the reason.
6. List your assumptions, and the ids of the model objects (values, compositions, identities) your answer rests on.

## Return contract

Write one JSON file, `{paths['answer']}`, that validates against `{paths['packet']}/answer.schema.json`. The suite maps it to its
own labels: `answer` is the actual result; `unit`, `units`, `period`, `scope` are the scope, period and units; `evidence` and
`objects` are the evidence and object bindings; `calculations` is the calculation trace; `baseline` is the selected baseline, scenario
and version (omit it for isolated arithmetic: do not invent a baseline id); `assumptions` and `missing_inputs` are the assumptions and
unresolved inputs.

Field policy of the suite: {policy}
"""


# -- prepare ---------------------------------------------------------------------------------------------------------------
def prepare_packets(suite: il.Suite, out: Path, run: str, *, tools_command: str, export_dir: Path, memo_dir: Path,
                    only: list[str] | None = None) -> dict:
    """Write the run's packets beside an export that already exists at `export_dir`. Deterministic."""
    out = Path(out).resolve()
    export_dir = Path(export_dir).resolve()
    if not export_dir.is_dir():
        raise FileNotFoundError(f"the export {export_dir} has not been produced")
    (out / "answers").mkdir(parents=True, exist_ok=True)
    policy = suite.meta.get("adapter_field_policy") or ""
    cases = []
    for case in suite.cases:
        tid = case["test_id"]
        if only and tid not in only:
            continue
        packet = out / tid
        (packet / "excerpts").mkdir(parents=True, exist_ok=True)
        fixture = suite.fixtures.get(tid)
        index = []
        for eid in case.get("frozen_excerpt_ids", []):
            e = suite.excerpt(eid)
            text = suite.excerpt_text(eid)                      # also checks the page against the hash the index froze
            (packet / "excerpts" / f"{eid}.txt").write_text(text, encoding="utf-8")
            pdf = suite.root / "excerpts" / Path(e["pdf_file"]).name
            if pdf.exists():
                (packet / "excerpts" / f"{eid}.pdf").write_bytes(suite.access.read_bytes(pdf))
            src = suite.index["sources"][e["source_id"]]
            index.append({"excerpt_id": eid, "source_id": e["source_id"], "title": src.get("title"),
                          "source_version": e["source_version"], "availability_date": src["availability_date"],
                          "pdf_pages": e["pdf_pages"], "printed_page": e["printed_page"], "text_file": f"excerpts/{eid}.txt",
                          "original_pdf_sha256": e["original_pdf_sha256"], "text_sha256": e["text_sha256"]})
        if index:
            (packet / "excerpt_index.json").write_text(il.dumps(index), encoding="utf-8")
        if fixture is not None:
            (packet / "fixture_inputs.json").write_text(il.dumps(fixture["fixture_inputs"]), encoding="utf-8")
        (packet / "answer.schema.json").write_text(il.dumps(answer_schema()), encoding="utf-8")
        paths = {"packet": str(packet), "export": str(export_dir), "memo": str(Path(memo_dir).resolve()),
                 "answer": str(out / "answers" / f"{tid}.json")}
        (packet / "task.md").write_text(task_text(case, fixture, index, paths, policy, tools_command), encoding="utf-8")
        cases.append({"test_id": tid, "excerpts": [i["excerpt_id"] for i in index], "fixture": fixture is not None})
    meta = {"run": run, "suite_id": suite.meta.get("suite_id"), "suite_version": suite.meta.get("version"),
            "export": str(export_dir), "export_files": len([p for p in export_dir.rglob("*") if p.is_file()]),
            "memo": str(Path(memo_dir).resolve()), "answers": str(out / "answers"), "cases": cases}
    (out / "run.json").write_text(il.dumps(meta), encoding="utf-8")
    return meta


# -- collect ---------------------------------------------------------------------------------------------------------------
def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def squeeze(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def read_answer(suite: il.Suite, packets: Path, tid: str) -> tuple[dict | None, str, str]:
    """(the answer, its sha256 or '', the reason it cannot be used or '')."""
    f = packets / "answers" / f"{tid}.json"
    if not f.exists():
        return None, "", "no answer file was written"
    raw = suite.access.read_bytes(f)
    try:
        ans = json.loads(raw)
    except ValueError as e:
        return None, sha(raw), f"invalid answer: not JSON ({e})"
    problems = validate(ans, answer_schema())
    if not problems and ans["test_id"] != tid:
        problems = [f"$.test_id: {ans['test_id']!r} is not {tid!r}"]
    if not problems and ans["status"] == "blocked" and not ans.get("reason", "").strip():
        problems = ["$.reason: a blocked answer states its reason"]
    if not problems and ans["status"] == "answered" and not ans.get("answer"):
        problems = ["$.answer: an answered case returns its result"]
    return (None, sha(raw), "invalid answer: " + "; ".join(problems[:4])) if problems else (ans, sha(raw), "")


def internal_of(suite: il.Suite, packets: Path, case: dict, ans: dict) -> dict:
    """Our own fields for an answer: its evidence checked against the case's frozen pages, its calculations against the log."""
    evidence = []
    for ev in ans.get("evidence", []):
        bound = ev["excerpt_id"] in case.get("frozen_excerpt_ids", [])
        found = bound and squeeze(ev["passage"]).lower() in squeeze(suite.excerpt_text(ev["excerpt_id"])).lower()
        evidence.append({**ev, "bound_to_case": bound, "passage_found_on_page": found})
    log = packets / case["test_id"] / "calc_log.jsonl"
    logged = [{**json.loads(line), "verified_by_tool": True} for line in suite.access.read_text(log).splitlines()] if log.exists() else []
    seen = {(c["expression"], json.dumps(c["value"])) for c in logged}
    declared = [{**c, "verified_by_tool": False} for c in ans.get("calculations", [])
                if (c["expression"], json.dumps(c["value"])) not in seen]
    answer = {**ans.get("answer", {}), **({"unresolved": ans["missing_inputs"]} if ans.get("missing_inputs") else {})}
    scope = {k: ans[k] for k in ("period", "unit", "units", "scope") if k in ans}
    objects = [{"id": o} for o in ans.get("objects", [])]
    return {
        "answer": answer,
        "scope": scope or il.na("the answer states no period, unit or scope"),
        "evidence_and_objects": {"evidence": evidence, "objects": objects} if evidence or objects
        else il.na("the answer cites no source page or model object"),
        "calculations": logged + declared,
        "baseline": ans.get("baseline") or il.na("isolated arithmetic or no baseline stated: none is invented"),
        "assumptions_and_missing": {"assumptions": ans.get("assumptions", []), "unresolved": ans.get("missing_inputs", [])},
        "grounding": {"operation": "agent", "model_objects": [o["id"] for o in objects],
                      "source_excerpts": sorted({e["excerpt_id"] for e in evidence}), "computed": [], "stated": sorted(answer)},
    }


def collect(suite: il.Suite, packets: Path, transcripts: list[Path] | None = None, only: list[str] | None = None) -> dict:
    """The suite's results from the answers in `<packets>/answers`, in the shape the grader reads."""
    packets = Path(packets).resolve()
    results, hashes = [], {}
    for case in suite.cases:
        tid = case["test_id"]
        if only and tid not in only:
            continue
        required = tuple(suite.fixtures.get(tid, {}).get("required_output_fields") or il.CONTRACT_FIELDS)
        ans, digest, why = read_answer(suite, packets, tid)
        if digest:
            hashes[tid] = digest
        if ans is None or ans["status"] == "blocked":
            reason = why or ans["reason"].strip()
            results.append(il.to_contract(case, il.BLOCKED, None, reason, required))
            continue
        results.append(il.to_contract(case, il.ANSWERED, internal_of(suite, packets, case, ans), "", required))
    overall = sha("".join(f"{t} {h}\n" for t, h in sorted(hashes.items())).encode())
    return {"suite_id": suite.meta.get("suite_id"), "suite_version": suite.meta.get("version"),
            "adapter_field_policy": suite.meta.get("adapter_field_policy"), "field_map": il.FIELD_MAP,
            "run": json.loads(suite.access.read_text(packets / "run.json")),
            "answers": {"dir": str(packets / "answers"), "files": len(hashes), "sha256": overall, "by_case": hashes},
            "transcripts": [{"path": str(Path(t)), "bytes": Path(t).stat().st_size, "sha256": sha(Path(t).read_bytes())}
                            for t in sorted(transcripts or [], key=str)],
            "results": results, "access": suite.access.report()}
