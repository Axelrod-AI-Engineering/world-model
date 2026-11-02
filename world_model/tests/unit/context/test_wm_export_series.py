"""Update mechanics as exports (context/wm_export_series.py, Oct 31), on the synthetic acme client: the series records
what happened at each step, including what an evaluator should fail (two orders, two different models)."""

from __future__ import annotations

from axelrod_wm.context.wm_export_series import attempt, update_series
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.unit.sim.test_import_persistence import bundle, good, runner


def strip(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "manifest"}


def series(first, second):
    return update_series(lambda: runner(MemoryBackend()), first, second, world_model_id="acme", label="Acme",
                         generated_at="2026-10-31T00:00:00Z", series_id="acme-updates", subjects=("Acme",))


def test_each_step_is_an_export_that_names_its_operation_and_what_to_compare_it_with():
    first = bundle(good("A", "2026-08-04T09:00:00Z", 0.5), good("B", "2026-08-06T09:00:00Z", 0.75), title="first")
    second = bundle(good("C", "2026-08-05T09:00:00Z", 1.25), title="second")
    docs = series(first, second)
    sc = [d["manifest"]["scenario"] for d in docs]
    assert [s["operation"] for s in sc] == ["build", "ingest", "export_again", "reingest", "ingest", "ingest", "as_of",
                                            "restore"]
    assert [s["step"] for s in sc] == list(range(8)) and {s["series_id"] for s in sc} == {"acme-updates"}
    m = [d["manifest"] for d in docs]
    assert strip(docs[2]) == strip(docs[1]) and m[2]["state_hash"] == m[1]["state_hash"]     # exported twice: the same
    assert sc[3]["note"] == "nothing new to import" and m[3]["state_hash"] == m[1]["state_hash"]   # idempotent
    assert m[7]["state_hash"] == m[1]["state_hash"] and m[7]["version"] == m[1]["version"]    # restored exactly
    assert int(m[6]["version"]) <= int(m[1]["version"]) and sc[6]["as_of_requested"]
    assert (sc[4]["order"], sc[5]["order"], sc[5]["target_step"]) == ("first,second", "second,first", 4)
    assert m[4]["state_hash"] != m[5]["state_hash"]           # the order changes the state today; the evaluator says so
    assert docs[1]["history"]["versions"][-1]["version"] == int(m[1]["version"])
    assert docs[6]["history"]["proposals"] == [] and len(docs[4]["history"]["versions"]) > len(docs[1]["history"]["versions"])


def test_an_import_answer_is_its_state_or_its_refusal():
    assert attempt(lambda b: {"state": "regated"}, {}) == "regated"
