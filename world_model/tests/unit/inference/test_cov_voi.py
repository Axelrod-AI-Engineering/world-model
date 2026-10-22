"""Value of information (voi.py, §8.11): context buckets, a stored thesis's shocks, the probability and the
references of each kind of hypothesis, and which hypotheses a touched entity re-scores."""

from __future__ import annotations

from datetime import timedelta

import pytest

from axelrod_wm.inference.voi import ForecastSensitivityVOI, HypothesisScorer, current_bucket, thesis_shocks
from axelrod_wm.memory.working import ForecastStateView
from axelrod_wm.model.hypothesis import Hypothesis, HypothesisKind, HypothesisStatus
from tests.conftest import START, constructed_engine, oil_thesis

NOW = START + timedelta(days=30)
OIL = "resources_energy.oil_price"
CPI = "inflation.headline_cpi"
FED = "federal_reserve.policy_stance"


def _hyp(hid="H-x", kind=HypothesisKind.INTERACTION_PRESENT, p=0.5, **kw):
    return Hypothesis(id=hid, kind=kind, statement=hid, probability=p, scored_at=NOW, origin="human", **kw)


def _cv(sid, delta=1.0, **kw):
    return {"op": "change_value", "target": {"kind": "concrete", "subentity_id": sid}, "delta": delta,
            "mode": "standardized", "at": (NOW + timedelta(days=10)).isoformat(), **kw}


def _pose(eng, thesis, pinned=False):
    """Put a thesis into the forecast layer as a posed one (only its JSON is read for references)."""
    layer = eng.wm.forecast_layer
    layer.by_thesis[thesis.id] = ForecastStateView.model_construct(thesis_id=thesis.id,
                                                                   thesis=thesis.model_dump(mode="json"))
    layer.order = [*layer.order, thesis.id]
    if pinned:
        layer.pinned = {*layer.pinned, thesis.id}


@pytest.fixture
def eng():
    return constructed_engine(build=True)


@pytest.fixture
def ctx(eng):
    return eng.context(learn=False, now=NOW)


def test_a_decision_with_no_observed_inputs_is_in_the_neutral_bucket(eng, ctx):
    assert all(eng.wm.deviations.z_at(s, ctx.today) is None for _k, _i, s, _t, _d in eng.wm.graph.in_channel_items(FED))
    assert current_bucket(FED, eng.wm, ctx) == "neutral"


def test_the_abstract_rescore_touched_has_no_default(eng, ctx):
    assert HypothesisScorer.rescore_touched(ForecastSensitivityVOI(), {"x"}, eng.wm, eng.ltm, ctx, None) is None


def test_thesis_shocks_keep_concrete_value_changes_of_known_subentities(eng, ctx):
    abstract = {"op": "change_value", "target": {"kind": "abstract", "entity_id": "delta"}, "delta": 1.0,
                "mode": "standardized", "at": (NOW + timedelta(days=10)).isoformat()}
    observe = {"op": "observe_value", "target": {"kind": "concrete", "subentity_id": CPI}, "value": 3.0,
               "observed_at": NOW.isoformat()}
    th = oil_thesis(NOW, delta=0, extra_ops=[_cv(OIL, 2.0, delta_sd=0.5), _cv("ghost.value"), abstract, observe,
                                             _cv(CPI, 1.0, intervention=True, window_days=20)])
    shocks = thesis_shocks(th.model_dump(mode="json"), eng.wm, ctx)
    assert [s.subentity_id for s in shocks] == [OIL, CPI]
    oil, cpi = shocks
    assert oil.size == pytest.approx(2.0) and oil.size_sd == pytest.approx(0.5)
    assert not oil.intervention and oil.hold_days is None
    assert cpi.intervention and cpi.hold_days == 20
    assert oil.start_day == cpi.start_day >= 1


def test_probability_falls_back_to_the_stored_value(eng, ctx):
    s = ForecastSensitivityVOI(eng.config)
    # a decision on an unknown value, and a decision with no value at all
    ghost = _hyp(kind=HypothesisKind.ENTITY_DECISION, p=0.37, decision_subentity_id="ghost.value", decision_change=1.0)
    bare = _hyp(kind=HypothesisKind.ENTITY_DECISION, p=0.21)
    assert s.probability(ghost, eng.wm, eng.ltm, ctx) == 0.37
    assert s.probability(bare, eng.wm, eng.ltm, ctx) == 0.21
    # an edge that is neither in the graph nor between two named ends
    lost = _hyp(p=0.42, interaction_id="no_such_edge")
    assert s.probability(lost, eng.wm, eng.ltm, ctx) == 0.42


def test_an_unknown_edge_id_is_found_by_its_ends(eng, ctx):
    s = ForecastSensitivityVOI(eng.config)
    present = _hyp(p=0.01, interaction_id="no_such_edge", source_id=CPI, target_id=FED)
    absent = present.model_copy(update={"kind": HypothesisKind.INTERACTION_ABSENT})
    p = eng.wm.graph.interactions["e43"].existence.mean()
    assert s.probability(present, eng.wm, eng.ltm, ctx) == pytest.approx(p)
    assert s.probability(absent, eng.wm, eng.ltm, ctx) == pytest.approx(1.0 - p)


def test_references_are_the_posed_theses_pinned_first_and_at_most_three(eng, ctx):
    s = ForecastSensitivityVOI(eng.config)
    h = _hyp(interaction_id="e43")
    for k, sid in enumerate(["asset_prices.equity_index", CPI, "interest_rates.us_policy_rate", OIL], start=1):
        _pose(eng, oil_thesis(NOW, thesis_id=f"T-{k}", delta=0, extra_ops=[_cv(sid)]), pinned=(k == 1))
    # a view stored without its thesis is skipped
    eng.wm.forecast_layer.by_thesis["T-bare"] = ForecastStateView.model_construct(thesis_id="T-bare", thesis=None)
    eng.wm.forecast_layer.order = [*eng.wm.forecast_layer.order, "T-bare"]
    # a posed thesis that only intervenes adds no reference
    _pose(eng, oil_thesis(NOW, thesis_id="T-do", delta=0, extra_ops=[_cv(CPI, intervention=True, window_days=5)]))
    refs = s._references(h, eng.wm, ctx)
    # T-1 is pinned, then the most recent ones (T-do and T-bare yield nothing), three theses read in all
    assert [[x.subentity_id for x in r] for r in refs] == [["asset_prices.equity_index"]]


def test_without_posed_theses_the_reference_is_a_unit_shock_at_the_source(eng, ctx):
    s = ForecastSensitivityVOI(eng.config)
    by_edge = s._references(_hyp(interaction_id="e43"), eng.wm, ctx)            # no ends named: the edge's source
    assert [[(x.subentity_id, x.size) for x in r] for r in by_edge] == [[(CPI, 1.0)]]
    assert s._references(_hyp(interaction_id="no_such_edge"), eng.wm, ctx) == []
    ghost = _hyp(kind=HypothesisKind.ENTITY_DECISION, decision_subentity_id="ghost.value")
    assert s._references(ghost, eng.wm, ctx) == []


def test_sensitivity_is_zero_when_nothing_can_be_simulated(eng, ctx):
    s = ForecastSensitivityVOI(eng.config, eng.components["propagator"])
    # no reference at all
    assert s.sensitivity(_hyp(interaction_id="no_such_edge"), eng.wm, eng.ltm, ctx) == 0.0
    # with a posed thesis as the reference: a decision on an unknown value, and an edge with no ends
    _pose(eng, oil_thesis(NOW, thesis_id="T-ref"))
    ghost = _hyp(kind=HypothesisKind.ENTITY_DECISION, decision_subentity_id="ghost.value", decision_change=1.0)
    assert s.sensitivity(ghost, eng.wm, eng.ltm, ctx) == 0.0
    assert s._hyp_channel(_hyp(interaction_id="no_such_edge"), eng.wm, eng.ltm, ctx) is None
    assert s.sensitivity(_hyp(interaction_id="no_such_edge"), eng.wm, eng.ltm, ctx) == 0.0


def test_rescore_touched_finds_subjects_through_the_edge(eng, ctx):
    scorer = eng.components["hypothesis_scorer"]
    hs = [_hyp("H-edge", interaction_id="e43"),                          # no ends named: inflation and the Fed
          _hyp("H-lost", interaction_id="no_such_edge"),                 # no subjects at all
          _hyp("H-closed", interaction_id="e43", status=HypothesisStatus.REFUTED)]
    assert all(not h.subject_entity_ids for h in hs)
    with eng.mutator.begin("h", at=NOW) as txn:
        for h in hs:
            txn.add("wm.hypotheses", h)
    with eng.mutator.begin("rescore", at=NOW) as txn:
        out = scorer.rescore_touched({"federal_reserve"}, eng.wm, eng.ltm, ctx, txn)
    assert out == ["H-edge"]
    assert eng.wm.hypotheses["H-edge"].sensitivity_at == NOW
    assert eng.wm.hypotheses["H-lost"].sensitivity_at is None
    assert scorer._history is None                                      # the frozen history is released
