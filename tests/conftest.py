"""Shared fixtures."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from axelrod_wm.engine.config import load_config
from axelrod_wm.engine.engine import Engine
from axelrod_wm.engine.initialize import ConstructionSpec, Initializer, SeedFile, load_vocabulary
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.trace import NullTracer

START_DATE = date(2023, 1, 2)                     # day 0 of the constructed engine
START = datetime(2023, 1, 2, tzinfo=timezone.utc)
SEEDS = "data/scenarios/oil_shock_demo/superentity_seeds.yaml"
VOCAB = load_vocabulary("data/taxonomy")


def pytest_addoption(parser):
    parser.addoption("--runslow", action="store_true", default=False,
                     help="also run tests marked slow (full scenario runs)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        return
    skip = pytest.mark.skip(reason="slow: pass --runslow to run the full scenario")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True, scope="session")
def _session_lake(tmp_path_factory):
    """Module- and session-scoped apps are built before any function fixture runs: give them a lakehouse of their own
    too, so no test ever reads or writes the repo's var/lake."""
    mp = pytest.MonkeyPatch()
    mp.setenv("WORLD_MODEL_LAKE_DIR", str(tmp_path_factory.mktemp("session") / "lake"))
    mp.setenv("WORLD_MODEL_EMBEDDER", "hashing")
    mp.delenv("WORLD_MODEL_LLM_PROVIDER", raising=False)
    mp.delenv("WORLD_MODEL_API_KEYS", raising=False)
    yield
    mp.undo()


@pytest.fixture(autouse=True, scope="module")
def _module_lake(tmp_path_factory):
    """A module-scoped app gets a lakehouse of its module's own, so no module sees documents another one uploaded
    (autouse, so it is set before the module's own fixtures build their apps)."""
    mp = pytest.MonkeyPatch()
    mp.setenv("WORLD_MODEL_LAKE_DIR", str(tmp_path_factory.mktemp("module") / "lake"))
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def _isolated_lake(tmp_path, monkeypatch):
    """Every test gets its own lakehouse and the hashing embedder (exact, and no model download), and no LLM step."""
    monkeypatch.setenv("WORLD_MODEL_LAKE_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("WORLD_MODEL_EMBEDDER", "hashing")
    monkeypatch.delenv("WORLD_MODEL_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("WORLD_MODEL_API_KEYS", raising=False)


def make_config(**updates):
    base = {"storage": {"backend": "memory", "path": "var/test"}}
    base.update(updates)
    return load_config(overrides=[base])


def constructed_engine(build: bool = False, config=None) -> Engine:
    """An engine holding the M1 graph: construction plus seed patterns (no history)."""
    cfg = config or make_config()
    if build:
        from axelrod_wm.engine.engine import build_engine

        eng = build_engine(cfg, MemoryBackend(), NullTracer(), vocab=VOCAB)
    else:
        eng = Engine(cfg, MemoryBackend(), NullTracer(), vocab=VOCAB)
    init = Initializer(eng)
    init.construct(ConstructionSpec.load("data/worlds/economy"), "data/taxonomy", start=START_DATE, vocab=VOCAB)
    init.load_seeds(SeedFile.load(SEEDS), now=eng.wm.clock)
    return eng


@pytest.fixture
def m1_engine() -> Engine:
    return constructed_engine()


def warm_taxonomies(eng, rounds: int = 6, now=None) -> None:
    """Push every entity and interaction through its classification path `rounds` times, as the
    history replay would, so supports exceed the recall threshold."""
    from axelrod_wm.engine.interfaces import Classification
    from axelrod_wm.model.taxonomy import TaxonomyKind

    now = now or eng.wm.clock
    ltm = eng.ltm
    otax, itax = ltm.object_generalizations.taxonomy, ltm.interaction_generalizations.taxonomy
    updater = eng.components["generalization_updater"]
    for _ in range(rounds):
        cls = []
        for eid, ent in sorted(eng.wm.graph.entities.items()):
            if ent.generalization_id:
                path = otax.path_from_root(ent.generalization_id)
                cls.append(Classification(item_id=eid, taxonomy=TaxonomyKind.OBJECT, path=path, prior_source_id=path[0]))
        for iid, inter in sorted(eng.wm.graph.interactions.items()):
            if inter.generalization_id:
                path = itax.path_from_root(inter.generalization_id)
                cls.append(Classification(item_id=iid, taxonomy=TaxonomyKind.INTERACTION, path=path,
                                          prior_source_id=path[0]))
        ctx = eng.context(learn=True, now=now)
        with eng.mutator.begin("warm", at=now) as txn:
            updater.update(cls, ltm, ctx, txn)


def real_event(ops, eid="GUE-T", at=None, produced_by="human", **kw):
    from axelrod_wm.events.graph_update import GraphUpdateEvent

    at = at or datetime(2026, 2, 16, 5, 30, tzinfo=timezone.utc)
    return GraphUpdateEvent.model_validate({"id": eid, "kind": "real", "occurred_at": at, "recorded_at": at,
                                            "produced_by": produced_by, "ops": ops, **kw})


@pytest.fixture
def warm_engine():
    eng = constructed_engine(build=True)
    warm_taxonomies(eng)
    return eng


T01_TARGETS = ["inflation.headline_cpi", "interest_rates.us_policy_rate", "credit_availability.credit_growth",
               "business_investment.capex_growth", "asset_prices.equity_index", "confidence.consumer_confidence",
               "productivity_tech.tfp_growth"]


def oil_thesis(now, thesis_id="T-01", delta=1.0, days_ahead=86, horizon_days=270, targets=None, extra_ops=()):
    from datetime import timedelta

    from axelrod_wm.events.thesis import Thesis

    at = now + timedelta(days=days_ahead)
    ops = [{"op": "change_value", "target": {"kind": "concrete", "subentity_id": "resources_energy.oil_price"},
            "delta": delta, "mode": "relative", "persistence": "step", "at": at.isoformat()}] if delta else []
    ops += list(extra_ops)
    return Thesis.model_validate({
        "id": thesis_id, "question": "What if oil prices doubled next quarter?", "mode": "scaffolded",
        "horizon_days": horizon_days, "posed_by": "test", "posed_at": now.isoformat(),
        "targets": T01_TARGETS if targets is None else targets,
        "event": {"id": f"GUE-{thesis_id}", "kind": "hypothetical", "event_type": "supply_shock",
                  "occurred_at": at.isoformat(), "recorded_at": now.isoformat(), "produced_by": "human", "ops": ops}})


SCENARIO_DIR = "data/scenarios/oil_shock_demo"


def make_controller(engine=None, policy: str | None = None):
    from axelrod_wm.control.controller import WorldModelController

    eng = engine or constructed_engine(build=True)
    c = WorldModelController(eng, scenario_dir=SCENARIO_DIR)
    if policy:
        c.set_review_policy(policy)
    return c


def market_event(me_id: str):
    import json

    from axelrod_wm.intake.sources import parse_market_event

    for line in open(f"{SCENARIO_DIR}/market_events.jsonl"):
        if line.strip():
            d = json.loads(line)
            if d["id"] == me_id:
                return parse_market_event(d)[0]
    raise KeyError(me_id)


# ---------------------------------------------------------------------------------------------
# The daily loop without an update run: predict, fold, record, consolidate (§7.8 step 4)
# ---------------------------------------------------------------------------------------------

def predict_day(eng, d: int) -> None:
    """Working memory opens the day (its prediction)."""
    eng.learning.open_day(d)


def close_day(eng, d: int):
    """The day's end, as the update run does it: record (working), distill (long-term), close (working)."""
    dev = eng.wm.deviations
    ctx = eng.context(learn=True, now=dev.day_end(d), processing_day=d)
    moves = eng.learning.working.record_day(d, ctx)
    report = eng.learning.long_term.distill(d, ctx)
    eng.learning.working.close_day(d, ctx, report)
    report.version = eng.version
    return moves, report


def run_days(eng, n: int, events=None, at_hour: int = 21):
    """Process the next n days. `events(day) -> list[GraphUpdateEvent]` supplies real events to fold
    on a day. Returns the consolidation reports."""
    from datetime import time as _time

    reports = []
    for _ in range(n):
        d = eng.wm.last_processed_day + 1
        predict_day(eng, d)
        dev = eng.wm.deviations
        for ev in (events(d) if events else []):
            now = datetime.combine(dev.date_of(d), _time(at_hour), tzinfo=timezone.utc)
            eng.learning.run(ev, now, d)
        reports.append(close_day(eng, d)[1])
    return reports


def observe_event(eid: str, values: dict, day_date, event_type: str = "data_release", **kw):
    """A data-release style real event observing native values on a date."""
    at = datetime.combine(day_date, datetime.min.time(), tzinfo=timezone.utc).replace(hour=21)
    ops = [{"op": "observe_value", "target": {"kind": "concrete", "subentity_id": sid}, "value": float(v),
            "observed_at": at.isoformat()} for sid, v in values.items()]
    return real_event(ops, eid=eid, at=at, produced_by="data_feed", event_type=event_type, **kw)
