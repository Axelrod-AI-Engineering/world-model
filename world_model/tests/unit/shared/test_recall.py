"""Recall (§8.4.3), attention, and pattern binding (§8.8 bind)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from axelrod_wm.memory.long_term import Episode
from axelrod_wm.shared.recall import SoftmaxTopK
from axelrod_wm.shared.recognize import BfsRoleFillingBinder
from tests.conftest import make_config, real_event

AT = datetime(2026, 3, 9, 21, tzinfo=timezone.utc)


def test_softmax_top_k_attention():
    pol = SoftmaxTopK(make_config())
    att = pol.select({"a": 1.0, "b": 0.9, "c": 0.2, "d": -3.0}, top_k=3)
    assert list(att) == ["a", "b", "c"]
    assert sum(att.values()) == pytest.approx(1.0)
    assert att["a"] > att["b"] > att["c"]
    att2 = SoftmaxTopK(make_config(), min_attention=0.2).select({"a": 1.0, "b": 0.9, "c": -1.0}, top_k=3)
    assert "c" not in att2 and sum(att2.values()) == pytest.approx(1.0)


def _episode(eid, end, tags, etypes, key_sig, patterns=(), routine=False):
    return Episode(id=eid, day=end.date(), trigger_event_ids=[f"GUE-{eid}"], event_types=list(etypes), routine=routine,
                   signature=set(key_sig), key_signature=set(key_sig), deltas={}, active_interaction_ids=[],
                   edge_effects={}, active_pattern_ids=list(patterns), tags=list(tags))


def test_fed_event_recalls_s1_or_s8(warm_engine):
    eng = warm_engine
    ev = real_event([{"op": "observe_value", "target": {"kind": "concrete", "subentity_id": "federal_reserve.policy_stance"},
                      "value": 4.75, "observed_at": "2026-01-28T19:00:00Z"}], "GUE-ME01", AT, produced_by="data_feed",
                    event_type="data_release")
    res = eng.learning.run(ev, AT, 0)
    top3 = [s.pattern_id for s in sorted(res.shared.recall.superentities, key=lambda s: -s.attention)[:3]]
    assert "S1" in top3 or "S8" in top3


def test_bank_stress_recalls_bank_run_analogs_and_binds_a_history_pattern(warm_engine):
    eng = warm_engine
    with eng.mutator.begin("episodes", at=AT) as txn:
        sig = {"gen:obj:root", "gen:obj:market_stress", "gen:int:root", "gen:int:financial_contagion"}
        txn.add("ltm.prior_states.episodes", _episode("EP-a", AT - timedelta(days=270), ["bank-run-like", "2008-like"],
                                                      ["financial_stress"], sig))
        txn.add("ltm.prior_states.episodes", _episode("EP-b", AT - timedelta(days=30), [], ["data_release"],
                                                      {"gen:obj:root"}, routine=True))
        txn.add("ltm.prior_states.episodes", _episode("EP-c", AT - timedelta(days=900), ["energy-shock-like"],
                                                      ["supply_shock"], {"gen:obj:supply_factor"}))
    ops = [{"op": "change_value", "target": {"kind": "concrete", "subentity_id": "financial_crises.banking_stress"},
            "delta": 2.0, "mode": "standardized", "at": AT.isoformat()},
           {"op": "change_value", "target": {"kind": "concrete", "subentity_id": "asset_prices.equity_index"},
            "delta": -0.04, "mode": "relative", "at": AT.isoformat()}]
    res = eng.learning.run(real_event(ops, "GUE-ME06", AT, produced_by="hand_drawn", event_type="financial_stress",
                                      tags=["bank-run-like"]), AT, 0)
    analogs = [a.episode_id for a in res.shared.recall.analogs]
    assert analogs[0] == "EP-a"
    assert "EP-b" not in analogs                      # routine episodes are not analogs
    bound = {eng.wm.graph.instances[i].pattern_id for i in res.shared.induction.bound_instance_ids}
    assert bound & {"HP1", "HP2"}


def test_recency_baseline_prefers_recent_episodes():
    from axelrod_wm.shared.recall import RecencyRecaller
    from tests.conftest import constructed_engine

    eng = constructed_engine(build=True)
    with eng.mutator.begin("episodes", at=AT) as txn:
        txn.add("ltm.prior_states.episodes", _episode("EP-old", AT - timedelta(days=700), ["bank-run-like"],
                                                      ["financial_stress"], {"x"}))
        txn.add("ltm.prior_states.episodes", _episode("EP-new", AT - timedelta(days=7), [], ["regulatory_action"], {"y"}))
    from axelrod_wm.shared.process import ParsedEvent

    parsed = ParsedEvent(event_id="E", kind="real", event_type="financial_stress", day=0, processing_day=0, shocks=[],
                         observations=[],
                         touched_subentity_ids=[], touched_entity_ids=[], new_entity_ids=[], new_interaction_ids=[],
                         touched_interaction_ids=[], tags=["bank-run-like"])
    ctx = eng.context(learn=True, now=AT)
    res = RecencyRecaller(eng.config, SoftmaxTopK(eng.config)).recall(parsed, eng.wm, eng.ltm, ctx)
    assert res.analogs[0].episode_id == "EP-new"


def test_binder_binds_hp2_and_marks_absent_relations(warm_engine):
    eng = warm_engine
    binder = BfsRoleFillingBinder(eng.config, eng)
    patterns = eng.ltm.object_generalizations.patterns
    b = binder.bind(patterns["HP2"], ["financial_crises", "asset_prices"], eng.wm.graph, eng.ltm)
    assert b is not None and b.coverage == 1.0
    assert b.bindings == {"asset_prices": "asset_prices", "financial_crises": "financial_crises"}
    assert sorted(b.interaction_ids) == ["e07", "e28"]
    s9 = binder.bind(patterns["S9"], ["federal_reserve"], eng.wm.graph, eng.ltm)
    assert s9 is not None and s9.absent_interaction_ids == ["e43"] and s9.interaction_ids == ["e41"]
    assert binder.bind(patterns["HP2"], ["climate_change"], eng.wm.graph, eng.ltm) is None


def test_routine_data_never_binds(warm_engine):
    eng = warm_engine
    ev = real_event([{"op": "observe_value", "target": {"kind": "concrete", "subentity_id": "financial_crises.banking_stress"},
                      "value": 0.1, "observed_at": AT.isoformat()}], "GUE-RT", AT, produced_by="data_feed",
                    event_type="data_release")
    res = eng.learning.run(ev, AT, 0)
    assert res.shared.parsed.is_routine()
    assert res.shared.induction.bound_instance_ids == []
