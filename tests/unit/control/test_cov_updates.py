"""The update loop's edges (§7.8): one run at a time, naive times, failures, duplicates typed in twice, a market
event with several proposals, runs that do not pause, the late queue's strays, and cancelling at each point."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from axelrod_wm.control.controller import ControllerError
from axelrod_wm.control.updates import UpdateRequest, UpdateState, UserMarketEventInput
from axelrod_wm.events.graph_update import GraphUpdateEvent
from axelrod_wm.intake.translators import MarketEventTranslator, TranslationResult
from axelrod_wm.repo.review import ProposalStatus
from tests.conftest import constructed_engine, make_controller, warm_taxonomies
from tests.unit.control.test_update_loop import ListSource, at, data, news

CPI, OIL = "inflation.headline_cpi", "resources_energy.oil_price"


@pytest.fixture
def ctl():
    c = make_controller(constructed_engine(build=True))
    warm_taxonomies(c.engine)
    c.auto_resume = False
    return c


def feed(ctl, events) -> None:
    ctl.register_source("feed", ListSource(events))
    ctl.engine.config.update.sources = ["feed"]


def req(day: int, at_time: datetime | None = None, **kw) -> UpdateRequest:
    until = (datetime(2023, 1, 2, tzinfo=UTC) + timedelta(days=day)).date()
    return UpdateRequest(requested_by="user", until=until,
                         requested_at=at_time or datetime.combine(until, datetime.max.time(), tzinfo=UTC), **kw)


class TwoEvents(MarketEventTranslator):
    """Every news item becomes two world events: an observation of oil and one of CPI."""

    def translate(self, event, ctx):
        def ev(i: int, sid: str, value: float) -> GraphUpdateEvent:
            return GraphUpdateEvent.model_validate({
                "id": f"GUE-{event.id}-{i}", "kind": "real", "occurred_at": event.published_at.isoformat(),
                "recorded_at": event.published_at.isoformat(), "produced_by": "test",
                "market_event_id": event.id,
                "ops": [{"op": "observe_value", "target": {"kind": "concrete", "subentity_id": sid}, "value": value,
                         "observed_at": event.published_at.isoformat()}]})

        return TranslationResult(market_event_id=event.id, events=[ev(1, OIL, 90.0), ev(2, CPI, 3.1)])


def test_one_run_at_a_time_and_naive_times_are_utc(ctl):
    feed(ctl, [news("N1", 1, "Oil jumps by 20%")])
    run = ctl.request_update(req(2))
    assert run.state == UpdateState.AWAITING_REVIEW
    with pytest.raises(ControllerError, match=f"update run {run.id} is still active"):
        ctl.request_update(req(3))
    ctl.cancel_update(run.id)
    naive = ctl.request_update(req(3, at_time=datetime(2023, 1, 5, 20, 0)))
    assert naive.requested_at == datetime(2023, 1, 5, 20, 0, tzinfo=UTC)
    assert ctl.engine.wm.source_cursors["feed"] == naive.requested_at


def test_a_run_that_fails_while_collecting_is_marked_failed(ctl):
    feed(ctl, [])
    drawn = GraphUpdateEvent.model_validate({
        "id": "UG-W", "kind": "real", "occurred_at": at(0).isoformat(), "recorded_at": at(0).isoformat(),
        "produced_by": "human",
        "ops": [{"op": "observe_value", "target": {"kind": "concrete", "subentity_id": CPI}, "value": 3.0,
                 "observed_at": at(0).isoformat()}]})
    with pytest.raises(ControllerError, match="cannot contain observe_value"):
        ctl.request_update(req(1, user_graph_update_events=[drawn]))
    (run,) = ctl.updates.values()
    assert run.state == UpdateState.FAILED and run.error.startswith("ControllerError: a drawn event")
    assert ctl.active_update is None
    assert ctl.request_update(req(1)).state == UpdateState.DONE       # the next run is free to start


def test_naive_user_times_are_utc_and_an_article_already_collected_is_dropped(ctl):
    feed(ctl, [news("N1", 1, "Oil jumps by 20%")])
    ctl.set_review_policy("auto_approve_all")
    first = ctl.request_update(req(2, user_market_events=[
        UserMarketEventInput(headline="Oil fell by 5%", published_at=datetime(2023, 1, 3, 15, 0))]))
    assert first.queue[1] == ["N1", "ME-U-1"]
    assert ctl.market_events["ME-U-1"].published_at == datetime(2023, 1, 3, 15, 0, tzinfo=UTC)
    # the person adds the same article (same URL) by hand: it is a duplicate of the scraped one
    pasted = news("N1-pasted", 3, "Oil jumps by 20%").model_copy(update={"url": ctl.market_events["N1"].url})
    again = ctl.request_update(req(3, user_market_events=[pasted]))
    assert again.collected["user"] == 0 and again.duplicates_dropped == 1 and again.duplicate_ids == ["N1-pasted"]


def test_a_market_event_with_two_proposals_is_walked_in_order_across_pauses(ctl):
    feed(ctl, [news("N1", 1, "Two readings")])
    ctl._translators["news"] = [TwoEvents()]
    ctl.set_review_policy("review_all")
    ctl.auto_resume = True
    run = ctl.request_update(req(2))
    assert run.state == UpdateState.AWAITING_REVIEW
    first, second = run.walk["N1"]
    assert run.waiting_on == first
    ctl.approve(first, "kim")                           # folds the first, then pauses on the second
    assert run.state == UpdateState.AWAITING_REVIEW and run.waiting_on == second
    assert ctl.proposals[first].folded_day == 1 and run.handled == [first]
    ctl.approve(second, "kim")                          # the walk passes over the handled first one
    assert run.state == UpdateState.DONE and run.handled == [first, second]
    assert ctl.proposals[second].folded_day == 1 and run.report.approved == 2


def test_a_run_that_does_not_pause_defers_what_needs_review(ctl):
    feed(ctl, [news("N1", 1, "Oil jumps by 20%"), data("D1", 1, {CPI: 2.8})])
    ctl.engine.config.update.pause_for_review = False
    run = ctl.request_update(req(2))
    assert run.state == UpdateState.DONE and run.report.deferred == 1
    (p,) = [q for q in ctl.proposals.values() if q.market_event_id == "N1"]
    assert p.status == ProposalStatus.DEFERRED and p.decided_by == "update"


def test_a_stray_in_the_late_queue_is_dropped(ctl):
    feed(ctl, [])
    with ctl.engine.mutator.begin("stray", at=ctl.now) as txn:
        txn.put("wm.late_queue", "PR-gone", 0)          # e.g. from a session whose proposals were not kept
    run = ctl.request_update(req(1))
    assert run.state == UpdateState.DONE and run.late_folded == 0 and ctl.engine.wm.late_queue == {}


def test_run_days_and_resume_leave_a_finished_run_alone(ctl):
    feed(ctl, [data("D0", 0, {CPI: 2.8})])
    run = ctl.request_update(req(1))
    assert run.state == UpdateState.DONE
    report = run.report
    assert ctl.cycle.run_days(run) is run and ctl.cycle.resume(run) is run and ctl.cycle.cancel(run) is run
    assert run.state == UpdateState.DONE and run.report is report


def test_a_cancel_requested_between_days_stops_after_the_day(ctl):
    feed(ctl, [data("D0", 0, {CPI: 2.8}), data("D3", 3, {CPI: 3.0})])
    run = ctl.request_update(req(4), run_to_end=False)
    ctl.cycle.run_days(run, max_days=1)
    assert run.state == UpdateState.RUNNING and run.current_day == 1
    run.cancel_requested = True                         # e.g. from the API while a day is processed
    ctl.continue_update(run.id)
    assert run.state == UpdateState.CANCELLED and ctl.engine.wm.last_processed_day == 1
    assert ctl.market_status["D3"] == "queued"          # collected again by the next run


def test_cancelling_before_any_day_or_after_the_cursor_time(ctl):
    feed(ctl, [data("D1", 1, {CPI: 2.8})])
    # nothing processed yet: the run stops at once and the cursor goes back to the model's clock
    run = ctl.request_update(req(3), run_to_end=False)
    ctl.cancel_update(run.id)
    eng = ctl.engine
    assert run.state == UpdateState.CANCELLED and eng.wm.last_processed_day == -1
    assert eng.wm.source_cursors["feed"] == eng.wm.clock and run.report.days == 0
    # a request made early in the window: after two days the clock is past the cursor, which stays
    run2 = ctl.request_update(req(3, at_time=at(0, 20)), run_to_end=False)
    ctl.cycle.run_days(run2, max_days=2)
    cursor = eng.wm.source_cursors["feed"]
    assert cursor == at(0, 20) < eng.wm.clock
    ctl.cancel_update(run2.id)
    assert run2.state == UpdateState.CANCELLED and eng.wm.source_cursors["feed"] == cursor


def test_a_failure_while_resuming_marks_the_run_failed(ctl, monkeypatch):
    feed(ctl, [news("N1", 1, "Oil jumps by 20%"), data("D2", 2, {CPI: 2.8})])
    run = ctl.request_update(req(3))
    assert run.state == UpdateState.AWAITING_REVIEW
    ctl.approve(run.waiting_on, "kim")
    monkeypatch.setattr(ctl.engine.learning, "close_day", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk")))
    with pytest.raises(RuntimeError, match="disk"):
        ctl.continue_update(run.id)
    assert run.state == UpdateState.FAILED and run.error == "RuntimeError: disk" and ctl.active_update is None


def test_failing_or_finishing_an_older_run_leaves_the_active_run_alone(ctl):
    feed(ctl, [news("N1", 1, "Oil jumps by 20%")])
    old = ctl.request_update(req(0))
    run = ctl.request_update(req(2))
    assert old.state == UpdateState.DONE and run.state == UpdateState.AWAITING_REVIEW
    ctl.cycle._fail(old, RuntimeError("late report"))
    assert old.state == UpdateState.FAILED and ctl.active_update == run.id
    ctl.cycle._finish(old)
    assert old.state == UpdateState.DONE and ctl.active_update == run.id
