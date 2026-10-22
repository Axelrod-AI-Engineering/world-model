"""Judge packets for the inner-loop suite (Oct 22): the part of grading that needs a reader.

The numeric layer of the grader settles what a number can settle (inner_loop_grade.numeric_layer). What it cannot settle is
left for a judge to decide on meaning: the key's assertions (wording, mechanism, accounting destination, proof limits) and a
number that two different figures of the answer could each match. `prepare` writes one packet per answered case that has
such facets:

    <judge>/<test_id>/judge.md              a generic rubric and the question
                       facets.json          the key's facets for this case only, with stable ids, and the key's reference answer
                       answer.json          the answer to judge (its fields, quantities, evidence, objects, assumptions)
                       verdict.schema.json  per facet: pass or fail, and a one-line reason quoting the answer
    <judge>/judge_run.json                  the run, the graded answers' sha256 and the cases

A judge writes `<judge>/verdicts/<test_id>.json`; the grader combines them (`--verdicts`). This module reads the answer key, so
it is grader-side code: it takes the key's path as an argument, and its packets are never written inside an answerer's packets
(a folder holding a run.json of answer packets is refused).
"""

from __future__ import annotations

import json
from pathlib import Path

from axelrod_wm.evaluation import inner_loop
from axelrod_wm.evaluation import inner_loop_grade as g

RUBRIC = """# Judge case {test_id}

You judge one answer against the facets a reviewer wrote for this case. You decide each facet **on meaning, not wording**.

## Question

{question}

## What to read

- `facets.json`: the facets to decide, each with an id, a kind and a text, and the reviewer's reference answer for context.
- `answer.json`: the answer under judgement: its result fields, the quantities it states, its evidence, objects and assumptions.
- Read only this folder.

## How to decide

- A facet passes when the answer states it, in any words or fields. Synonyms count; a different field name does not matter.
- A facet marked `NOT:` passes when the answer does not make that claim, or states the opposite.
- A correct final number reached through a wrong bridge fails: when a facet asks for a mechanism, an accounting destination, a
  treatment or a limit, the answer must state it correctly, not only land on the figure.
- An unsupported claim fails: a statement that nothing in the answer's evidence, quantities or reasoning supports.
- Where a facet says a quantity has no determined value, a correctly identified unknown passes, and a stated number fails.
- A `quantity` facet asks whether the answer states that quantity, under any label, with that value in that unit and scale.
- Do not use what you know of the subject to fill a gap in the answer. If the answer does not say it, the facet fails.

## How to write the verdicts

Write `{verdict_path}` so that it validates against `verdict.schema.json`: for each facet id, `pass` or `fail` and a one-line
reason that quotes the answer (or says it is silent).
"""


def prepare_judge(results: dict, key_path: Path, out: Path, run: str, only: tuple[str, ...] = ()) -> dict:
    """Write the judge packets for the answered cases of `results`. Deterministic."""
    out = Path(out).resolve()
    for folder in (out, *out.parents):
        marker = folder / "run.json"
        if marker.exists() and "answers" in json.loads(marker.read_text(encoding="utf-8")):
            raise ValueError(f"{folder} holds answer packets: judge packets live apart from them")
    key = json.loads(Path(key_path).read_text(encoding="utf-8"))
    by_id = {r["test_id"]: r for r in results["results"]}
    cases = []
    (out / "verdicts").mkdir(parents=True, exist_ok=True)
    for case in key["cases"]:
        tid = case["test_id"]
        result = by_id.get(tid)
        if (only and tid not in only) or result is None or result["status"] != inner_loop.ANSWERED:
            continue
        facets = g.judge_facets(case, result)
        if not facets:
            continue
        packet = out / tid
        packet.mkdir(parents=True, exist_ok=True)
        view = {k: result.get(k) for k in ("actual_result", "scope_period_units_when_applicable", "quantities",
                                           "evidence_and_object_bindings_when_applicable", "calculation_trace_when_applicable",
                                           "assumptions_and_unresolved_inputs")}
        (packet / "judge.md").write_text(RUBRIC.format(test_id=tid, question=case["question"],
                                                       verdict_path=out / "verdicts" / f"{tid}.json"), encoding="utf-8")
        (packet / "facets.json").write_text(inner_loop.dumps({"test_id": tid, "facets": facets,
                                                              "reference_answer": case.get("precise_answer")}), encoding="utf-8")
        (packet / "answer.json").write_text(inner_loop.dumps(view), encoding="utf-8")
        (packet / "verdict.schema.json").write_text(inner_loop.dumps(g.verdict_schema()), encoding="utf-8")
        cases.append({"test_id": tid, "facets": len(facets)})
    meta = {"run": run, "suite_id": key["suite_id"], "graded_answers": results.get("answers"), "verdicts": str(out / "verdicts"),
            "cases": cases}
    (out / "judge_run.json").write_text(inner_loop.dumps(meta), encoding="utf-8")
    return meta
