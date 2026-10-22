"""A built construction, end to end: its links in the v4.1.4 pack (transitions in the canonical properties,
uncalibrated links without numbers, accounting identities, the business paths), and accounting weights that
neither process noise nor folding moves (dynamics/daily.py, learning/fold.py)."""

from __future__ import annotations

from datetime import date

from axelrod_wm.context.v4 import domain_pack, pack_config
from axelrod_wm.engine.engine import Engine, build_engine
from axelrod_wm.engine.initialize import ConstructionSpec, Initializer, load_vocabulary
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.trace import NullTracer
from tests.conftest import make_config, observe_event, real_event, run_days
from tests.unit.engine.test_cov_initialize import _taxonomy
from tests.unit.model.test_business_construction import ATTRS, acme_construction, world


def engine(tmp_path, build=Engine):
    c = acme_construction()
    for i in c["interactions"]:
        if i.get("edge_type") == "accounting":       # as a construction file writes them: no reporting lag
            i["kernel"] = {"delay_days": 0, "lag_days": 1, "duration_days": None}
    tax = _taxonomy(tmp_path, attrs=ATTRS, objects={"root": "gen:obj:root", "nodes": [
        {"id": "gen:obj:root", "name": "Object", "parent": None}]})
    eng = build(make_config(), MemoryBackend(), NullTracer(), vocab=load_vocabulary(tax))
    Initializer(eng).construct(ConstructionSpec.load(world(tmp_path, c), tax), tax,
                               start=date(2024, 1, 1), vocab=load_vocabulary(tax))
    return eng


def test_the_pack_carries_transitions_identities_and_business_paths(tmp_path):
    from axelrod_wm.model.construction import NamedPath, PathStep, Transition

    eng = engine(tmp_path)
    g = eng.wm.graph
    g.interactions["t3"] = g.interactions["t3"].model_copy(          # a bare transition: no breaker, timing unknown
        update={"transition": Transition(mechanism="landed cost squeezes segment profit", sign="-")})
    g.paths["P0"] = NamedPath(id="P0", name="Gone", entity_id="acme", trigger="t", endpoint="acme.profit",
                              steps=[PathStep(interaction_id="ghost")])         # nothing of it is exported
    pack = domain_pack(eng.wm, eng.ltm, pc=pack_config("acme_demo", "Acme"), book=["acme"], version=1, state_hash=None)
    text = str(pack)
    assert "represented_uncalibrated" in text and "unknown (uncalibrated)" in text
    assert "accounting_identity" in text and "a tariff raises the landed cost of imported vehicles" in text
    assert "local sourcing" in text and "onset at customs entry" in text
    assert "Tariffs and sourcing".lower().replace(" ", "_") in text.lower() and "landed cost squeezes segment" in text
    assert "_gone" not in text.lower()
    # Oct 18: each additive view carries its reconciliation at the model's levels (auto 10 + finance 10 - 1 vs 10)
    bridge = {b["composition_id"]: b for b in pack["domain_specific_support_objects"]["financial_bridge"]}
    rec = bridge["C1"]["reconciliation"]
    assert rec["status"] == "flag" and abs(rec["difference"] + 9.0) < 1e-6 and rec["total"] == "acme.profit"
    g.compositions["C2"] = g.compositions["C2"].model_copy(update={"additive": False})
    pack = domain_pack(eng.wm, eng.ltm, pc=pack_config("acme_demo", "Acme"), book=["acme"], version=1, state_hash=None)
    bridge = {b["composition_id"]: b for b in pack["domain_specific_support_objects"]["financial_bridge"]}
    assert bridge["C2"]["reconciliation"] is None


def test_accounting_weights_stay_as_built_while_days_pass_and_observations_fold(tmp_path):
    eng = engine(tmp_path, build_engine)
    g = eng.wm.graph
    built = {i: g.interactions[i].forward.effect.model_dump() for i in ("a0", "a1", "a2", "a3", "a4")}
    start = g.interactions["t2"].forward.effect.model_dump()
    dev = eng.wm.deviations

    def events(d):
        when = dev.date_of(d)
        return [observe_event(f"o{d}", {"acme.auto": 12.0 + d % 3, "acme.na": 11.0 - d % 2,
                                        "acme.landed_cost": 9.0 + d % 4, "acme.profit": 14.0 + d % 5}, when)]

    run_days(eng, 6, events)
    g = eng.wm.graph
    assert {i: g.interactions[i].forward.effect.model_dump() for i in built} == built
    twice = observe_event("twice", {"acme.profit": 15.0}, dev.date_of(eng.wm.last_processed_day + 1))
    ops = [op.model_dump(mode="json", exclude_none=True) for op in twice.ops] * 2     # one value read twice
    run_days(eng, 1, lambda d: [real_event(ops, eid="twice", at=twice.occurred_at, produced_by="data_feed",
                                           event_type="data_release")])
    assert {i: eng.wm.graph.interactions[i].forward.effect.model_dump() for i in built} == built
    assert g.interactions["t2"].forward.effect.model_dump() != start      # a calibrated link does learn
