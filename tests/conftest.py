"""Shared fixtures."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from axelrod_wm.engine.config import load_config
from axelrod_wm.engine.engine import Engine
from axelrod_wm.engine.initialize import ConstructionSpec, Initializer, SeedFile
from axelrod_wm.memory.snapshots import MemoryBackend
from axelrod_wm.trace import NullTracer

START = datetime(2023, 1, 2, tzinfo=timezone.utc)
SEEDS = "data/scenarios/oil_shock_demo/superentity_seeds.yaml"


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


def make_config(**updates):
    base = {"storage": {"backend": "memory", "path": "var/test"}}
    base.update(updates)
    return load_config(overrides=[base])


def constructed_engine(build: bool = False, config=None) -> Engine:
    """An engine holding the M1 graph: construction plus seed patterns (no history)."""
    cfg = config or make_config()
    if build:
        from axelrod_wm.engine.engine import build_engine

        eng = build_engine(cfg, MemoryBackend(), NullTracer())
    else:
        eng = Engine(cfg, MemoryBackend(), NullTracer())
    init = Initializer(eng)
    init.construct(ConstructionSpec.load("data/construction"), "data/taxonomy", start=START)
    init.load_seeds(SeedFile.load(SEEDS), now=START)
    return eng


@pytest.fixture
def m1_engine() -> Engine:
    return constructed_engine()


def warm_taxonomies(eng, rounds: int = 6, now=None) -> None:
    """Push every entity and interaction through its classification path `rounds` times, as the
    history replay would, so supports exceed the recall threshold."""
    from axelrod_wm.core.taxonomy import TaxonomyKind
    from axelrod_wm.engine.interfaces import Classification

    now = now or START
    ltm = eng.ltm
    updater = eng.components["generalization_updater"]
    for _ in range(rounds):
        cls = []
        for eid, ent in sorted(eng.wm.graph.entities.items()):
            if ent.generalization_id:
                path = ltm.object_taxonomy.path_from_root(ent.generalization_id)
                cls.append(Classification(item_id=eid, taxonomy=TaxonomyKind.OBJECT, path=path, prior_source_id=path[0]))
        for iid, inter in sorted(eng.wm.graph.interactions.items()):
            if inter.generalization_id:
                path = ltm.interaction_taxonomy.path_from_root(inter.generalization_id)
                cls.append(Classification(item_id=iid, taxonomy=TaxonomyKind.INTERACTION, path=path,
                                          prior_source_id=path[0]))
        ctx = eng.context(learn=True, now=now)
        with eng.mutator.begin("warm", now=now) as txn:
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

    from axelrod_wm.ingest.sources import parse_market_event

    for line in open(f"{SCENARIO_DIR}/market_events.jsonl"):
        if line.strip():
            d = json.loads(line)
            if d["id"] == me_id:
                return parse_market_event(d)[0]
    raise KeyError(me_id)
