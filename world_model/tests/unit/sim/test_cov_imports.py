"""The import runner (sim/imports.py): a seeded model brought up to date by import bundles, each item reviewed in
date order; bundles from a server-side folder; items older than the model folded in late."""

from __future__ import annotations

import json

import pytest

from axelrod_ingest.contract.bundle import ImportBundle
from axelrod_wm.clients import load_scenario_yaml
from axelrod_wm.control.controller import ControllerError
from axelrod_wm.control.updates import UpdateState
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.sim.imports import ImportRunner, load_bundle_file
from axelrod_wm.sim.scenario import ScenarioScript
from axelrod_wm.trace import RecordingTracer
from tests.where import ACME_SCENARIO

ACME = str(ACME_SCENARIO)


def item(iid: str, at: str, rate: float) -> dict:
    return {"id": iid, "published_at": at, "source": "Synthetic newswire", "source_type": "central_bank",
            "headline": f"The central bank sets its policy rate at {rate}%", "entities": ["central_bank"],
            "signals": [{"type": "observe", "value_of": "central_bank.policy_rate", "value": rate, "quote": f"{rate}%"}]}


def bundle(*items: dict, title: str = "Test bundle") -> dict:
    return {"title": title, "collected_by": "a test", "synthetic": True, "items": list(items)}


def script(imports_dir: str | None, seeds: bool = True) -> ScenarioScript:
    raw = load_scenario_yaml(ACME)
    raw["imports_dir"] = imports_dir
    if not seeds:
        raw["initialization"]["seeds"] = None
    return ScenarioScript.model_validate(raw)


def runner(imports_dir: str | None = None, seeds: bool = True) -> ImportRunner:
    r = ImportRunner(None, None, script(imports_dir, seeds), True, storage=MemoryBackend(),
                     tracer=RecordingTracer(run_id="imp"))
    r.load()
    return r


def review_all(r: ImportRunner, update_id: str) -> None:
    ctl = r.controller
    run = ctl.get_update(update_id)
    while run.state == UpdateState.AWAITING_REVIEW:
        ctl.approve(run.waiting_on, "eve")        # approving the awaited item resumes the run


@pytest.fixture(scope="module")
def imported(tmp_path_factory):
    folder = tmp_path_factory.mktemp("imports")
    r = runner(str(folder))
    return r, folder


def test_a_model_without_seeds_loads_with_no_superentities():
    r = runner(seeds=False)
    ctl = r.controller
    assert r.loaded and not ctl.engine.wm.graph.instances
    assert r.status().imports and r.status().canvas == "seeded"


def test_parse_accepts_a_bundle_and_names_the_first_problem(tmp_path):
    b = ImportBundle.model_validate(bundle(item("A", "2026-08-04T09:00:00Z", 0.5)))
    assert ImportRunner.parse(b) is b
    with pytest.raises(ControllerError, match=r"not an import bundle: items\.0\.published_at"):
        ImportRunner.parse({"items": [{"id": "A", "source": "s", "headline": "h"}]})
    p = tmp_path / "b.json"
    p.write_text(json.dumps(bundle(item("A", "2026-08-04T09:00:00Z", 0.5))))
    assert [i.id for i in load_bundle_file(p).items] == ["A"]


def test_local_bundles_list_the_folder_and_skip_what_is_not_a_bundle(imported, tmp_path):
    r, folder = imported
    (folder / "b_good.json").write_text(json.dumps(bundle(item("A", "2026-08-04T09:00:00Z", 0.5), title="Good")))
    (folder / "a_not_json.json").write_text("{nope")
    (folder / "c_not_bundle.json").write_text(json.dumps({"items": "no"}))
    (folder / "notes.txt").write_text("ignored")
    assert r.local_bundles() == [{"name": "b_good.json", "title": "Good", "items": 1, "collected_by": "a test"}]
    assert r.local_bundle("../b_good.json")["title"] == "Good"           # only the file name counts
    with pytest.raises(ControllerError, match="no bundle 'missing.json' here"):
        r.local_bundle("missing.json")
    # no folder configured, or one that does not exist on this server
    no_dir = ImportRunner(None, None, script(None), True)
    assert no_dir.local_bundles() == []
    assert not no_dir.status().loaded and no_dir.status().total_steps == 0     # not loaded yet
    with pytest.raises(ControllerError, match="no bundle"):
        no_dir.local_bundle("b_good.json")
    absent = ImportRunner(None, None, script(str(tmp_path / "absent")), True)
    assert absent.local_bundles() == []


def test_import_reviews_in_date_order_then_says_it_is_done(imported):
    r, _ = imported
    ctl = r.controller
    b = bundle(item("B", "2026-08-05T09:00:00Z", 0.75), item("A", "2026-08-04T09:00:00Z", 0.5))
    pv = r.preview(b)
    assert [x["id"] for x in pv["items"]] == ["A", "B"] and {x["status"] for x in pv["items"]} == {"new"}
    out = r.import_items(b)
    assert out["imported"] == ["A", "B"] and out["state"] == "awaiting_review"
    assert ctl.proposals[out["waiting_on"]].market_event_id == "IM-A"
    assert r.status().state == "awaiting_review"
    with pytest.raises(ControllerError, match="still running"):
        r.import_items(bundle(item("C", "2026-08-06T09:00:00Z", 1.0)))
    review_all(r, out["update_id"])
    st = r.status()
    assert st.state == "idle" and st.caption.startswith("Up to date through Aug 5: “Test bundle” is in (2 approved")
    assert r.import_log[-1]["closed"] is True
    r.caption = "something else"
    assert r.status().caption == "something else"        # said once
    assert [x["status"] for x in r.preview(b)["items"]] == ["imported", "imported"]
    with pytest.raises(ControllerError, match="nothing new to import"):
        r.import_items(b)


def test_items_older_than_the_model_fold_in_late_on_the_next_day(imported):
    r, _ = imported
    ctl = r.controller
    wm = ctl.engine.wm
    last = int(wm.last_processed_day)
    old = bundle(item("OLD", "2026-08-03T09:00:00Z", 0.4), title="Old news")
    assert r.preview(old)["items"][0]["status"] == "late"
    out = r.import_items(old)
    run = ctl.get_update(out["update_id"])
    # the run goes through the day after the last processed one, and the item queues onto that day
    assert run.first_day == run.last_day == last + 1
    assert run.late_from == {"IM-OLD": wm.deviations.day_of(r.imported["IM-OLD"].published_at)}
    assert run.queue == {last + 1: ["IM-OLD"]}
    review_all(r, out["update_id"])
    assert run.state == UpdateState.DONE and run.report.late_collected == 1 and run.report.approved == 1
    assert int(wm.last_processed_day) == last + 1
