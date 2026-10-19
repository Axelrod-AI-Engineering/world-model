"""The daily distillation at its edges: an edge with no weight today implies no effect (neither in the
episode nor in the analogs' responses), and a value missing from the graph has no entity-memory summary."""

from __future__ import annotations

from tests.conftest import close_day, observe_event, predict_day


def test_weightless_edges_and_missing_values_are_left_out(warm_engine):
    eng = warm_engine
    dev = eng.wm.deviations
    every = max(1, int(eng.config.entity_memory.entry_every_days))
    d = eng.wm.last_processed_day + 1
    while (d + 1) % every:
        d += 1
    day_date = dev.date_of(d)
    predict_day(eng, d)
    ev = observe_event("GUE-OBS", {"inflation.headline_cpi": 9.0}, day_date, event_type="supply_shock")
    eng.learning.run(ev, ev.recorded_at, d)
    sids = list(eng.wm.graph.entities["inflation"].subentity_ids)
    with eng.mutator.begin("edits", at=eng.wm.clock) as txn:
        txn.put("wm.fold_accumulators", "e01", (0.0, 0.0))
        txn.put("wm.fold_accumulators", "e02", (0.4, 2.0))
        txn.update("wm.graph.entities", "inflation", subentity_ids=sids + ["inflation.ghost"])
    assert eng.wm.episode_buffer and not eng.wm.episode_buffer[-1].routine
    _moves, report = close_day(eng, d)
    ep = eng.ltm.prior_states.episodes[report.episode_id]
    assert "e01" not in ep.edge_effects and ep.edge_effects["e02"] == (0.2, 2.0)
    assert "e01" not in ep.response_effects and ep.response_effects["e02"] == (0.2, 2.0)
    entry = eng.ltm.entity_memories["inflation"].entries[-1]
    assert set(entry.subentity_summaries) == set(sids) and "inflation.ghost" not in entry.z
