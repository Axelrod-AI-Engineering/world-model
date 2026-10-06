"""The update loop (§7.8, D14): collection, dedup, the day loop, review pauses, the late queue, cancel,
re-posing pinned theses, and simulated timestamps."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

import pytest

from axelrod_wm.control.review import ProposalStatus
from axelrod_wm.control.updates import UpdateRequest, UpdateState, UserMarketEventInput
from axelrod_wm.events.ledger import LedgerKind
from axelrod_wm.events.market import MarketEvent, MarketEventChannel, MarketEventKind
from axelrod_wm.ingest.scrapers import MockWebScraper, ScrapedItem, WebScraper
from axelrod_wm.ingest.sources import MarketEventSource, in_window
from tests.conftest import constructed_engine, make_controller, oil_thesis, warm_taxonomies

CPI, OIL = "inflation.headline_cpi", "resources_energy.oil_price"


def at(day: int, hour: int = 21, minute: int = 0) -> datetime:
    return datetime(2023, 1, 2, hour, minute, tzinfo=UTC) + timedelta(days=day)


def data(eid: str, day: int, values: dict, hour: int = 21) -> MarketEvent:
    t = at(day, hour)
    return MarketEvent(id=eid, kind=MarketEventKind.DATA, channel=MarketEventChannel.DATA_FEED, source="feed",
                       headline=f"release {eid}", published_at=t, occurred_at=t, data=values, synthetic=True)


def news(eid: str, day: int, headline: str, hour: int = 12, url: str | None = None, site: str = "wire") -> MarketEvent:
    t = at(day, hour)
    return MarketEvent(id=eid, kind=MarketEventKind.NEWS, channel=MarketEventChannel.SCRAPER, source=site,
                       headline=headline, published_at=t, occurred_at=t, url=url or f"https://x.example/{eid}",
                       synthetic=True)


class ListSource(MarketEventSource):
    def __init__(self, events: list[MarketEvent]) -> None:
        self.events = events

    def poll(self, since, until):
        return [e for e in self.events if in_window(e.published_at, since, until)]


class ListScraper(WebScraper):
    """A scraper over fixed items, to exercise WebScraper's dedup."""

    def __init__(self, items: list[ScrapedItem]) -> None:
        super().__init__()
        self.items = items

    def fetch(self, since, until):
        return [i for i in self.items if in_window(i.published_at, since, until)]


@pytest.fixture
def ctl():
    c = make_controller(constructed_engine(build=True))
    warm_taxonomies(c.engine)
    c.auto_resume = False
    return c


def _setup(ctl, events, name="feed", sources=None):
    ctl.register_source(name, ListSource(events))
    ctl.engine.config.update.sources = sources or [name]


def request(ctl, until_day: int, at_time: datetime | None = None, **kw) -> object:
    until = (datetime(2023, 1, 2, tzinfo=UTC) + timedelta(days=until_day)).date()
    return ctl.request_update(UpdateRequest(requested_by="user", until=until,
                                            requested_at=at_time or datetime.combine(until, time(23, 59, 59), tzinfo=UTC),
                                            **kw))


def test_days_are_processed_and_a_repeat_collects_nothing(ctl):
    _setup(ctl, [data("D0", 0, {CPI: 2.8}), data("D2", 2, {CPI: 2.9})])
    run = request(ctl, 3)
    assert run.state == UpdateState.DONE and run.report.days == 4
    assert run.report.collected == {"feed": 2} and run.report.auto_applied == 2
    wm = ctl.engine.wm
    assert wm.last_processed_day == 3 and wm.clock == wm.deviations.day_end(3)
    # every processed day has a point for every subentity
    assert all(wm.deviations.point(s, d) is not None for d in range(4) for s in wm.graph.subentities)
    # the same request again: nothing to collect, no days to process
    again = request(ctl, 3)
    assert again.state == UpdateState.DONE and again.report.days == 0 and sum(again.report.collected.values()) == 0
    # a later run collects only what was published after the previous cursors
    ctl._sources["feed"].events.append(data("D5", 5, {CPI: 3.0}))
    later = request(ctl, 6)
    assert later.report.collected == {"feed": 1} and later.queue == {5: ["D5"]}


def test_duplicates_are_dropped_by_url_and_by_site_and_title(ctl):
    items = [ScrapedItem(url="https://a.example/1", site="wire", title="Oil jumps by 10%", body="",
                         published_at=at(1, 9), fetched_at=at(1, 23)),
             ScrapedItem(url="https://a.example/1", site="wire", title="Oil jumps by 10% (updated)", body="",
                         published_at=at(1, 10), fetched_at=at(1, 23)),
             ScrapedItem(url="https://b.example/mirror", site="wire", title="OIL JUMPS BY 10%!", body="",
                         published_at=at(1, 11), fetched_at=at(1, 23))]
    ctl.register_source("scraper", ListScraper(items))
    ctl.engine.config.update.sources = ["scraper"]
    ctl.set_review_policy("auto_approve_all")
    run = request(ctl, 1)
    assert run.report.collected == {"scraper": 1} and run.report.duplicates_dropped == 2
    (me,) = [m for m in ctl.market_events.values() if m.channel == MarketEventChannel.SCRAPER]
    assert me.id.startswith("ME-") and len(me.id) == 13 and me.url == "https://a.example/1"
    # a later run that sees the same item again drops it as a duplicate
    ctl._sources["scraper"].items.append(ScrapedItem(url="https://c.example/2", site="wire", title="Oil jumps by 10%",
                                                     body="", published_at=at(2, 9), fetched_at=at(2, 23)))
    run2 = request(ctl, 2)
    assert sum(run2.report.collected.values()) == 0 and run2.report.duplicates_dropped == 1


def test_user_market_events_land_on_their_day(ctl):
    _setup(ctl, [])
    ctl.set_review_policy("auto_approve_all")
    run = request(ctl, 4, user_market_events=[UserMarketEventInput(headline="Oil jumps by 10%", published_at=at(2, 15)),
                                              UserMarketEventInput(headline="Oil fell by 5%")])
    assert run.report.collected == {"feed": 0, "user": 2}
    by_id = {m.id: m for m in ctl.market_events.values() if m.channel == MarketEventChannel.USER}
    assert set(by_id) == {"ME-U-1", "ME-U-2"} and all(m.source == "user" for m in by_id.values())
    assert run.queue[2] == ["ME-U-1"]
    assert run.queue[4] == ["ME-U-2"]         # default published_at: the request time, kept inside the window


def test_a_pending_world_event_pauses_the_run_and_approval_resumes_in_order(ctl):
    _setup(ctl, [data("D1a", 1, {CPI: 2.8}, hour=9), news("N1", 1, "Oil jumps by 20%", hour=12),
                 data("D1b", 1, {CPI: 2.9}, hour=21), data("D3", 3, {CPI: 3.0})])
    run = request(ctl, 3)
    assert run.state == UpdateState.AWAITING_REVIEW and run.current_day == 1
    p = ctl.proposals[run.waiting_on]
    assert p.market_event_id == "N1" and p.world_event and p.needs_review
    # D1a (09:00) was folded before the pause; D1b (21:00) waits, so the day stays in time order
    folded = {q.market_event_id for q in ctl.proposals.values() if q.folded_day is not None}
    assert folded == {"D1a"}
    assert ctl.engine.wm.last_processed_day == 0
    ctl.approve(p.id, "kim")
    run = ctl.continue_update(run.id)
    assert run.state == UpdateState.DONE
    order = [q.market_event_id for q in sorted(ctl.proposals.values(), key=lambda q: q.version_after or 0)
             if q.folded_day == 1]
    assert order == ["D1a", "N1", "D1b"]
    assert run.report.approved == 1 and run.report.auto_applied == 3


def test_a_deferred_event_folds_in_late_on_the_next_processed_day(ctl):
    _setup(ctl, [news("N1", 1, "Oil jumps by 20%")])
    run = request(ctl, 2)
    assert run.state == UpdateState.AWAITING_REVIEW
    pid = run.waiting_on
    ctl.defer(pid, "kim")
    run = ctl.continue_update(run.id)
    assert run.state == UpdateState.DONE and run.report.deferred == 1
    assert ctl.proposals[pid].folded_day is None
    ctl.approve(pid, "kim")                                  # after its day: queued, never folded into the past
    assert ctl.engine.wm.late_queue == {pid: 1}
    run2 = request(ctl, 3)
    p = ctl.proposals[pid]
    assert p.folded_day == 3 and p.late_from == 1 and run2.report.late_folded == 1
    assert ctl.engine.wm.late_queue == {}
    entry = [e for e in ctl.engine.ledger.of_kind(LedgerKind.REVIEW_DECISION) if e.payload.get("action") == "folded"]
    assert entry and entry[-1].payload["late_from"] == 1


def test_model_edits_never_pause_a_run(ctl):
    from axelrod_wm.events.graph_update import GraphUpdateEvent

    _setup(ctl, [data("D1", 1, {CPI: 2.8})])
    drawn = GraphUpdateEvent.model_validate({
        "id": "UG-T", "kind": "real", "occurred_at": at(0).isoformat(), "recorded_at": at(0).isoformat(),
        "produced_by": "analyst_bot",
        "ops": [{"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": "fed_chair.hawkishness"},
                 "target": {"kind": "concrete", "subentity_id": "interest_rates.long_term_yields"},
                 "label": "moves yields", "polarity": 1}]})
    run = request(ctl, 2, user_graph_update_events=[drawn])
    assert run.state == UpdateState.DONE
    (pid,) = run.model_edits
    assert ctl.proposals[pid].status == ProposalStatus.PENDING and not ctl.proposals[pid].world_event


def test_an_item_after_the_request_time_is_collected_exactly_once(ctl):
    late = data("D1-late", 1, {CPI: 2.9}, hour=22)          # published after the 20:00 request, same day
    _setup(ctl, [data("D1", 1, {CPI: 2.8}, hour=9), late])
    run = request(ctl, 1, at_time=at(1, 20))
    run2 = request(ctl, 2)
    seen = [i for r in (run, run2) for ids in r.queue.values() for i in ids]
    assert seen.count("D1-late") == 1
    assert len(ctl.engine.ledger.of_kind(LedgerKind.MARKET_EVENT)) == 2


def test_cancel_finishes_the_day_and_leaves_a_consistent_state(ctl):
    from axelrod_wm.memory.snapshots import state_hash

    _setup(ctl, [news("N1", 1, "Oil jumps by 20%"), data("D1", 1, {CPI: 2.8}), data("D4", 4, {CPI: 3.0})])
    run = request(ctl, 5)
    assert run.state == UpdateState.AWAITING_REVIEW and run.current_day == 1
    run = ctl.cancel_update(run.id)
    assert run.state == UpdateState.CANCELLED
    eng = ctl.engine
    assert eng.wm.last_processed_day == 1                   # day 1 closed; days 2..5 untouched
    assert ctl.proposals[[p for p in ctl.proposals if ctl.proposals[p].market_event_id == "N1"][0]].status \
        == ProposalStatus.DEFERRED
    assert eng.wm.source_cursors["feed"] == eng.wm.clock    # the rest is collected again next time
    assert state_hash(eng.wm, eng.ltm) == eng.state_hash
    run2 = request(ctl, 5)
    assert 4 in run2.queue and run2.queue[4] == ["D4"]
    assert len([e for e in eng.ledger.of_kind(LedgerKind.MARKET_EVENT) if e.payload["id"] == "D4"]) == 1


def test_pinned_theses_are_reposed_at_the_end(ctl):
    _setup(ctl, [data("D0", 0, {CPI: 2.8})])
    request(ctl, 0)
    th = oil_thesis(ctl.now, "T-00", delta=0.0, horizon_days=30, targets=[])
    fc = ctl.pose_thesis(th)
    ctl.pin_thesis("T-00")
    run = request(ctl, 2)
    assert run.report.reposed_theses == ["T-00"]
    latest = max((f for f in ctl.forecasts.values() if f.thesis_id == "T-00"), key=lambda f: f.based_on_version)
    assert latest.based_on_version == run.report.version_after > fc.based_on_version


def test_change_sets_carry_simulated_timestamps(ctl):
    _setup(ctl, [data("D1", 1, {CPI: 2.8}, hour=21)])
    request(ctl, 1)
    eng = ctl.engine
    dev = eng.wm.deviations
    stamps = {e.payload["cause"]: e.recorded_at for e in eng.ledger.of_kind(LedgerKind.CHANGESET)}
    d1 = dev.date_of(1).isoformat()
    assert stamps[f"predict:{d1}"] == dev.day_start(1)
    assert stamps[f"record:{d1}"] == dev.day_end(1) == stamps[f"consolidation:{d1}"]
    folded = next(p for p in ctl.proposals.values() if p.market_event_id == "D1")
    assert stamps[folded.id] == at(1, 21)
    times = [e.recorded_at for e in eng.ledger.of_kind(LedgerKind.CHANGESET)]
    assert times == sorted(times)                            # recorded times never go backwards


def test_mock_scraper_returns_scraper_items_and_drops_the_mirror():
    from datetime import date

    src = MockWebScraper(scenario_dir="data/scenarios/oil_shock_demo")
    evs = src.poll(datetime.combine(date(2026, 2, 8), time(0), tzinfo=UTC),
                   datetime.combine(date(2026, 2, 9), time(23, 59, 59), tzinfo=UTC))
    assert [e.id for e in evs] == ["ME-03"] and src.last_dropped == 1
    assert all(e.channel == MarketEventChannel.SCRAPER for e in evs)
