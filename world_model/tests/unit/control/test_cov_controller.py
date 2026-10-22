"""The controller façade (§7.6) beyond the update loop: sources and translators, structural edits and their
refusals, approvals with selections and confidences, frontier promotions, theses that stay unbound, hypotheses,
what a fresh controller reads back from the ledger, annotations, and decisions from record to trace."""

from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta

import pytest

from axelrod_wm.control.controller import ControllerError, WorldModelController
from axelrod_wm.control.updates import UpdateRequest, UpdateState
from axelrod_wm.events.graph_update import GraphUpdateEvent
from axelrod_wm.events.market import MarketEvent, MarketEventChannel, MarketEventKind
from axelrod_wm.events.thesis import Thesis
from axelrod_wm.inference.decisions import DecisionError
from axelrod_wm.inference.task import UnboundThesis
from axelrod_wm.memory.frontier import CoMovementStatus
from axelrod_wm.model.hypothesis import Hypothesis, HypothesisStatus
from axelrod_wm.repo.ledger import LedgerKind
from axelrod_wm.repo.review import ProposalKind, ProposalStatus
from tests.conftest import SEEDS, constructed_engine, make_controller, oil_thesis, warm_taxonomies
from tests.unit.control.test_update_loop import ListSource

CPI, OIL = "inflation.headline_cpi", "resources_energy.oil_price"
RATE, FUNDING = "interest_rates.us_policy_rate", "credit_availability.us_bank_funding_cost"


def at(day: int, hour: int = 21) -> datetime:
    return datetime(2023, 1, 2, hour, tzinfo=UTC) + timedelta(days=day)


def data(eid: str, day: int, values: dict) -> MarketEvent:
    t = at(day)
    return MarketEvent(id=eid, kind=MarketEventKind.DATA, channel=MarketEventChannel.DATA_FEED, source="feed",
                       headline=f"release {eid}", published_at=t, occurred_at=t, data=values, synthetic=True)


def news(eid: str, day: int, headline: str) -> MarketEvent:
    t = at(day, 12)
    return MarketEvent(id=eid, kind=MarketEventKind.NEWS, channel=MarketEventChannel.SCRAPER, source="wire",
                       headline=headline, published_at=t, occurred_at=t, url=f"https://x.example/{eid}",
                       synthetic=True)


def until(day: int):
    return (datetime(2023, 1, 2, tzinfo=UTC) + timedelta(days=day)).date()


def request(ctl, day: int, **kw):
    d = until(day)
    return ctl.request_update(UpdateRequest(requested_by="user", until=d,
                                            requested_at=datetime.combine(d, time(23, 59, 59), tzinfo=UTC), **kw))


def edge_event(eid: str = "GUE-E", src: str = "fed_chair.hawkishness", dst: str = "interest_rates.long_term_yields",
               **kw) -> GraphUpdateEvent:
    return GraphUpdateEvent.model_validate({
        "id": eid, "kind": "real", "occurred_at": at(0).isoformat(), "recorded_at": at(0).isoformat(),
        "produced_by": "human",
        "ops": [{"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": src},
                 "target": {"kind": "concrete", "subentity_id": dst}, "label": "moves", "polarity": 1}], **kw})


@pytest.fixture
def ctl():
    c = make_controller(constructed_engine(build=True))
    warm_taxonomies(c.engine)
    c.auto_resume = False
    return c


def hypothesis(hid: str, **kw) -> Hypothesis:
    base = {"id": hid, "kind": "interaction_present", "statement": "oil moves CPI", "source_id": OIL,
            "target_id": CPI, "probability": 0.5, "scored_at": "2023-01-01T00:00:00+00:00", "origin": "human"}
    return Hypothesis.model_validate({**base, **kw})


def feed(ctl, events: list[MarketEvent]) -> None:
    ctl.register_source("feed", ListSource(events))
    ctl.engine.config.update.sources = ["feed"]


# ---------------------------------------------------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------------------------------------------------
def test_without_a_scenario_there_is_no_world_folder_and_sources_come_from_the_registry(tmp_path):
    from axelrod_wm.intake.scrapers import MockWebScraper

    eng = constructed_engine(build=True)
    bare = WorldModelController(eng)
    assert bare.world_dir() is None and bare.watchlist() is None
    chain = bare.translator_chain("news")
    assert chain and bare.translator_for("news") is chain[0]
    src = bare.source("mock_web_scraper")
    assert isinstance(src, MockWebScraper) and src.path is None and src.name == "mock_web_scraper"
    assert bare.source("mock_web_scraper") is src                       # built once
    # a scenario folder without a scenario.yaml: no world folder, and sources read the folder
    (tmp_path / "market_events.jsonl").write_text("")
    other = WorldModelController(eng, scenario_dir=tmp_path)
    assert other.world_dir() is None and other.watchlist() is None
    assert other.source("mock_web_scraper").path == tmp_path / "market_events.jsonl"
    assert other.control_state() == {"ids": {}}


def test_listeners_hear_proposals_and_their_application(ctl):
    heard = []
    ctl.listeners.append(lambda kind, **info: heard.append((kind, info["proposal"].id)))
    ctl.set_review_policy("auto_approve_all")
    p = ctl.submit_graph_update(edge_event(), by="kim")
    assert p.status == ProposalStatus.AUTO_APPLIED
    assert heard == [("proposed", p.id), ("applied", p.id)]


# ---------------------------------------------------------------------------------------------------------------
# structural edits
# ---------------------------------------------------------------------------------------------------------------
def test_group_refusals(ctl):
    with pytest.raises(ControllerError, match="at least two members"):
        ctl.propose_group("Solo", ["interest_rates"])
    with pytest.raises(ControllerError, match="unknown or retired interactions: nope"):
        ctl.propose_group("G", ["interest_rates", "credit_availability"], interactions=["nope"])
    with pytest.raises(ControllerError, match="share no interaction"):
        ctl.propose_group("G", ["geography", "market_concentration"])
    with pytest.raises(ControllerError, match="S1 is already an admitted superentity"):
        ctl.propose_group("G", ["interest_rates", "credit_availability"], pattern_id="S1")


def test_retire_refusals(ctl):
    with pytest.raises(ControllerError, match="exactly one entity or one interaction"):
        ctl.propose_retire(reason="x")
    with pytest.raises(ControllerError, match="exactly one"):
        ctl.propose_retire(entity_id="ecb", interaction_id="e01", reason="x")
    with pytest.raises(ControllerError, match="unknown entity nope"):
        ctl.propose_retire(entity_id="nope", reason="x")


def test_approval_adds_soft_support_only_to_known_concepts(ctl):
    nodes = ctl.engine.ltm.interaction_generalizations.taxonomy.nodes
    gid = sorted(nodes)[1]
    before = nodes[gid].stats.support
    ctl.set_review_policy("auto_approve_all")
    p = ctl.propose(ProposalKind.GRAPH_UPDATE, edge_event(), soft_support={gid: 0.5, "gen:int:nope": 2.0})
    assert p.status == ProposalStatus.AUTO_APPLIED
    nodes = ctl.engine.ltm.interaction_generalizations.taxonomy.nodes
    assert nodes[gid].stats.support == pytest.approx(before + 0.5) and "gen:int:nope" not in nodes
    # effects apply once, even when asked again
    cs_before = ctl.engine.version
    with ctl.engine.mutator.begin("again", at=ctl.now) as txn:
        ctl._apply_effects(p, txn)
    assert nodes[gid].stats.support == pytest.approx(before + 0.5) and ctl.engine.version == cs_before


# ---------------------------------------------------------------------------------------------------------------
# reviews
# ---------------------------------------------------------------------------------------------------------------
def test_open_proposals_selections_and_confidences(ctl):
    with pytest.raises(ControllerError, match="unknown proposal PR-9"):
        ctl.approve("PR-9", "kim")
    ev = edge_event()
    ev = ev.model_copy(update={"ops": ev.ops + edge_event(src=RATE, dst="interest_rates.long_term_yields").ops})
    ctl.set_review_policy("review_all")
    p = ctl.submit_graph_update(ev, by="kim")
    assert p.status == ProposalStatus.PENDING
    with pytest.raises(ControllerError, match="nothing is selected"):
        ctl.approve(p.id, "kim", keep=[])
    # a confidence that changes nothing is not logged
    n = len(ctl.engine.ledger.of_kind(LedgerKind.REVIEW_DECISION))
    ctl.set_confidence(p.id)
    assert len(ctl.engine.ledger.of_kind(LedgerKind.REVIEW_DECISION)) == n
    # two edits keep the first original
    first = p.event
    ctl.edit(p.id, edge_event(eid="GUE-E2"), by="kim")
    ctl.edit(p.id, edge_event(eid="GUE-E3"), by="kim")
    assert ctl.proposals[p.id].edited_from == first and ctl.proposals[p.id].event.id == "GUE-E3"
    # keeping every op approves the proposal as it is, with no edit
    edits = len([e for e in ctl.engine.ledger.of_kind(LedgerKind.REVIEW_DECISION) if e.payload["action"] == "edited"])
    ctl.approve(p.id, "kim", keep=[0])
    assert ctl.proposals[p.id].status == ProposalStatus.APPROVED
    assert len([e for e in ctl.engine.ledger.of_kind(LedgerKind.REVIEW_DECISION)
                if e.payload["action"] == "edited"]) == edits
    with pytest.raises(ControllerError, match="is already approved"):
        ctl.reject(p.id, "kim", "late")


def _frontier_promotion(ctl):
    from axelrod_wm.engine.initialize import Initializer, SeedFile
    from axelrod_wm.learning.frontier_test import promotion_event

    eng = ctl.engine
    (cm, *_rest) = Initializer(eng).load_frontier_seeds(SeedFile.load(SEEDS), now=eng.wm.clock)
    co = eng.ltm.correlation_frontier.entries[cm]
    ev = promotion_event(co, eng.context(learn=False, now=ctl.now))
    return co, ctl.propose(ProposalKind.FRONTIER_PROMOTION, ev, subject_id=co.id, reasons=["passed"])


def test_approving_a_frontier_promotion_closes_the_pair(ctl):
    co, p = _frontier_promotion(ctl)
    assert p.needs_review
    ctl.approve(p.id, "kim")
    eng = ctl.engine
    # the learned edge between the pair closes its frontier entry, and supports its hypothesis
    assert co.id not in eng.ltm.correlation_frontier.entries
    assert eng.wm.hypotheses[co.hypothesis_id].status == HypothesisStatus.SUPPORTED
    assert any(str(i.edge_type) == "learned_causal" and i.source_id == co.earlier_id and i.target_id == co.later_id
               for i in eng.wm.graph.interactions.values())


def test_a_promotion_edited_to_another_edge_marks_the_pair_promoted(ctl):
    co, p = _frontier_promotion(ctl)
    ctl.edit(p.id, edge_event(eid="GUE-OTHER"), by="kim")       # the reviewer draws a different edge instead
    ctl.approve(p.id, "kim")
    assert ctl.engine.ltm.correlation_frontier.entries[co.id].status == CoMovementStatus.PROMOTED


def test_rejecting_a_frontier_promotion_blocks_the_pair_and_refutes_its_hypothesis(ctl):
    from axelrod_wm.memory.frontier import pair_key

    co, p = _frontier_promotion(ctl)
    ctl.reject(p.id, "kim", "a confounder")
    eng = ctl.engine
    fr = eng.ltm.correlation_frontier
    assert fr.entries[co.id].status == CoMovementStatus.DECAYED
    assert eng.wm.hypotheses[co.hypothesis_id].status == HypothesisStatus.REFUTED
    assert fr.blocked_until[pair_key(co.earlier_id, co.later_id)] == ctl.now + timedelta(
        days=float(ctl.config.frontier.reject_cooldown_days))


def test_rejecting_a_promotion_whose_hypothesis_is_gone(ctl):
    co, p = _frontier_promotion(ctl)
    eng = ctl.engine
    with eng.mutator.begin("drop", at=ctl.now) as txn:
        txn.remove("wm.hypotheses", co.hypothesis_id)
    ctl.reject(p.id, "kim", "no")
    assert eng.ltm.correlation_frontier.entries[co.id].status == CoMovementStatus.DECAYED
    assert co.hypothesis_id not in eng.wm.hypotheses


def test_a_world_event_with_no_operations_folds_without_learning(ctl):
    ev = edge_event(eid="GUE-W").model_copy(update={"ops": []})
    p = ctl.propose(ProposalKind.GRAPH_UPDATE, ev, world=True)
    assert p.status == ProposalStatus.PENDING and p.market_event_id is None
    ctl.approve(p.id, "kim")
    applied = []
    ctl.listeners.append(lambda kind, **info: applied.append(info.get("result", "none")))
    d = int(ctl.engine.wm.last_processed_day) + 1
    cs = ctl.fold_world_event(p, d)
    assert cs is None and p.folded_day == d and p.changeset_id is None and applied == [None]
    entry = ctl.engine.ledger.of_kind(LedgerKind.REVIEW_DECISION)[-1].payload
    assert entry["action"] == "folded" and entry["late_from"] is None


def test_deferring_the_awaited_proposal_resumes_the_run(ctl):
    feed(ctl, [news("N1", 1, "Oil jumps by 20%")])
    run = request(ctl, 2)
    assert run.state == UpdateState.AWAITING_REVIEW
    ctl.auto_resume = True
    ctl.defer(run.waiting_on, "kim")
    assert run.state == UpdateState.DONE and run.report.deferred == 1


# ---------------------------------------------------------------------------------------------------------------
# update runs
# ---------------------------------------------------------------------------------------------------------------
def test_update_requests_as_dicts_continued_and_unknown(ctl):
    feed(ctl, [data("D1", 1, {CPI: 2.8})])
    run = ctl.request_update({"requested_by": "user", "until": until(2).isoformat(),
                              "requested_at": at(2, 23).isoformat()}, run_to_end=False)
    assert run.state == UpdateState.RUNNING and run.current_day == 0
    assert ctl.continue_update(run.id).state == UpdateState.DONE
    assert ctl.continue_update(run.id) is run and run.state == UpdateState.DONE      # nothing left to do
    with pytest.raises(ControllerError, match="unknown update UPD-9"):
        ctl.get_update("UPD-9")


def test_pinned_theses_survive_a_new_controller_and_unknown_pins_are_skipped(ctl):
    request(ctl, 0)
    ctl.pose_thesis(oil_thesis(ctl.now, "T-00", delta=0.0, horizon_days=10, targets=[CPI]))
    ctl.pin_thesis("T-00")
    v = ctl.engine.version
    ctl.pin_thesis("T-00")                              # already pinned: no commit
    assert ctl.engine.version == v and ctl.theses["T-00"].pinned
    ctl.pin_thesis("T-ghost")                           # pinned, but never posed
    assert "T-ghost" not in ctl.theses
    fresh = WorldModelController(ctl.engine, scenario_dir=ctl.scenario_dir)
    assert fresh.repose_pinned() == ["T-00"]            # read back from the forecast layer; T-ghost is skipped
    assert fresh.theses["T-00"].pinned
    ctl.pin_thesis("T-ghost", False)
    assert "T-ghost" not in ctl.engine.wm.forecast_layer.pinned


# ---------------------------------------------------------------------------------------------------------------
# theses and hypotheses
# ---------------------------------------------------------------------------------------------------------------
def test_a_thesis_whose_ends_stay_fuzzy_is_unbound(ctl):
    th = oil_thesis(ctl.now, "T-U", targets=[CPI]).model_dump(mode="json")
    th["event"]["ops"][0]["target"] = {"kind": "abstract", "mention": "energy prices"}
    th["event"]["ops"].append({"op": "add_interaction", "source": {"kind": "abstract", "mention": "chip makers"},
                               "target": {"kind": "concrete", "subentity_id": CPI}, "label": "lifts", "polarity": 1})
    with pytest.raises(UnboundThesis) as err:
        ctl.pose_thesis(Thesis.model_validate(th))
    (only,) = err.value.unbound                         # the change's end; the interaction's hedge is not asked
    assert only["op_index"] == 0 and only["end"] == "subject" and only["candidates"]
    assert only["candidates"] == sorted(only["candidates"], key=lambda c: -c[1])
    assert "T-U" not in ctl.theses


def test_hypotheses_posed_and_their_status(ctl):
    with pytest.raises(ControllerError, match="unknown hypothesis H-9"):
        ctl.pose_hypothesis("H-9")
    h = ctl.add_hypothesis(hypothesis("H-link"))
    with pytest.raises(ControllerError, match="only entity-decision hypotheses"):
        ctl.pose_hypothesis(h.id)
    d = ctl.add_hypothesis(hypothesis("H-hold", kind="entity_decision", statement="The Fed holds",
                                      source_id=None, target_id=None,
                                      decision_subentity_id="federal_reserve.policy_stance", decision_change=0.0,
                                      subject_entity_ids=["federal_reserve"]))
    with pytest.raises(ControllerError, match="unknown thesis T-9"):
        ctl.pose_hypothesis(d.id, "T-9")
    with pytest.raises(ControllerError, match="unknown hypothesis H-9"):
        ctl.set_hypothesis_status("H-9", "refuted")
    assert ctl.set_hypothesis_status(h.id, "refuted").status == HypothesisStatus.REFUTED
    assert ctl.engine.wm.hypotheses[h.id].status == HypothesisStatus.REFUTED


# ---------------------------------------------------------------------------------------------------------------
# reading back from the ledger, re-running, annotations
# ---------------------------------------------------------------------------------------------------------------
def test_a_fresh_controller_reads_forecasts_theses_and_explanations_from_the_ledger(ctl):
    feed(ctl, [data("D1", 1, {CPI: 2.8})])
    request(ctl, 1)
    extra = {"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": RATE},
             "target": {"kind": "concrete", "subentity_id": CPI}, "label": "cools", "polarity": -1}
    fc = ctl.pose_thesis(oil_thesis(ctl.now, "T-01", horizon_days=20, targets=[CPI], extra_ops=[extra]))
    stored = next(iter(ctl.engine.ltm.prior_states.explanations))
    fresh = WorldModelController(ctl.engine, scenario_dir=ctl.scenario_dir)
    assert fresh.explanation(stored) is ctl.engine.ltm.prior_states.explanations[stored]
    assert fresh.explanation("EX-nope") is None
    assert [f.id for f in fresh.forecasts_of("T-01")] == [fc.id] and not fresh.forecasts
    assert fresh.forecast(fc.id).id == fc.id and fc.id in fresh.forecasts           # read once, then kept
    assert fresh.thesis_of("T-01").id == "T-01" and fresh.thesis_of("T-9") is None
    # re-running moves the shock by the time since it was asked; an op without a time stays as it was
    fresh.advance_now(ctl.now + timedelta(days=3))
    again = fresh.rerun_forecast(fc.id)
    th = fresh.theses["T-01"]
    assert again.id != fc.id and th.posed_at == fresh.now
    assert th.event.ops[0].at == fc_thesis_at(ctl, "T-01") + timedelta(days=3)
    assert th.event.ops[1].op == "add_interaction"
    with pytest.raises(KeyError):
        fresh.rerun_forecast("FC-nope")
    orphan = fc.model_copy(update={"id": "FC-orphan", "thesis_id": "T-gone"})
    fresh.forecasts[orphan.id] = orphan
    with pytest.raises(ControllerError, match="the thesis of FC-orphan is not on record"):
        fresh.rerun_forecast(orphan.id)


def fc_thesis_at(ctl, tid: str) -> datetime:
    return ctl.theses[tid].event.ops[0].at


def test_annotations_are_read_back_with_removals(ctl):
    request(ctl, 0)
    a = ctl.pose_thesis(oil_thesis(ctl.now, "T-00", delta=0.0, horizon_days=10, targets=[CPI]))
    b = ctl.pose_thesis(oil_thesis(ctl.now, "T-01", horizon_days=10, targets=[CPI]))
    with pytest.raises(ControllerError, match="needs some text"):
        ctl.annotate(a.id, "brief", "   ")
    n1 = ctl.annotate(a.id, "", "first", by="")
    n2 = ctl.annotate(a.id, "chart", "second")
    ctl.annotate(b.id, "brief", "other forecast")
    assert n1["anchor"] == "brief" and n1["by"] == "reader"
    ctl.remove_annotation(a.id, n1["id"])
    fresh = WorldModelController(ctl.engine, scenario_dir=ctl.scenario_dir)
    assert [n["id"] for n in fresh.annotations(a.id)] == [n2["id"]]
    assert [n["text"] for n in fresh.annotations(b.id)] == ["other forecast"]


# ---------------------------------------------------------------------------------------------------------------
# decisions
# ---------------------------------------------------------------------------------------------------------------
def test_a_decision_from_record_to_outcome_and_trace(ctl):
    feed(ctl, [data(f"D{i}", i, {CPI: 2.5 + 0.4 * i}) for i in range(12)])
    request(ctl, 0)
    base = ctl.pose_thesis(oil_thesis(ctl.now, "T-00", delta=0.0, horizon_days=30, targets=[CPI]))
    later_ok = ctl.pose_thesis(oil_thesis(ctl.now, "T-01", horizon_days=30, targets=[CPI]))
    review_after = (ctl.now + timedelta(days=1)).isoformat()
    payload = {"agent_id": "a", "recommendation": "r", "forecast_ids": [base.id], "thesis_ids": ["T-00"],
               "state_version": base.based_on_version, "review_after": review_after}
    with pytest.raises(DecisionError, match="cited forecast FC-nope does not exist"):
        ctl.record_decision({**payload, "forecast_ids": ["FC-nope"]})
    with pytest.raises(DecisionError, match="differs from the baseline"):
        ctl.record_decision({**payload, "state_version": base.based_on_version + 100})
    ctl.add_hypothesis(hypothesis("H-x"))               # a commit: the next forecast is on a later version
    newer = ctl.pose_thesis(oil_thesis(ctl.now, "T-02", horizon_days=30, targets=[CPI]))
    assert newer.based_on_version > base.based_on_version
    with pytest.raises(DecisionError, match=f"forecast {newer.id} is based on a later version"):
        ctl.record_decision({**payload, "forecast_ids": [base.id, newer.id]})
    rec = ctl.record_decision({**payload, "forecast_ids": [base.id, later_ok.id]})
    assert re.fullmatch(r"D-\d{6}", rec.id) and ctl.decisions[rec.id] is rec      # numbered when not given
    assert ctl.engine.ledger.of_kind(LedgerKind.DECISION)[-1].payload["id"] == rec.id
    with pytest.raises(DecisionError, match="unknown decision D-9"):
        ctl.resolve_decision("D-9")
    with pytest.raises(DecisionError, match="can be resolved after"):
        ctl.resolve_decision(rec.id)
    request(ctl, 10)
    out = ctl.resolve_decision(rec.id)
    assert set(out.realized) == {CPI} and out.crps > 0 and rec.outcome is out
    assert "scored at day 10" in out.notes
    # the networks with CPI in them scored a hit or a miss on their track records
    assert any(e.payload.get("cause") == f"outcome:{rec.id}" for e in ctl.engine.ledger.of_kind(LedgerKind.CHANGESET))
    assert "decision-outcome" in ctl.engine.wm.pending_episode_tags or ctl.engine.ledger.of_kind(LedgerKind.OUTCOME)
    with pytest.raises(DecisionError, match="unknown decision D-9"):
        ctl.trace_decision("D-9")
    tr = ctl.trace_decision(rec.id)
    assert tr.hash_verified and tr.decision is rec and [f.id for f in tr.forecasts] == [base.id, later_ok.id]
    assert tr.changes_since and len(tr.explanations) == 2
