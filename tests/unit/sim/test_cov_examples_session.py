"""Running examples: the chain's selection logic on hand-built state, and the small demo's runner on its own
catalog and on small catalogs made for the test (an article that changes nothing, a proposal that never comes)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from axelrod_wm.control.controller import ControllerError
from axelrod_wm.control.updates import UpdateState
from axelrod_wm.events.market import MarketEvent, MarketEventChannel, MarketEventKind
from axelrod_wm.repo.review import ProposalStatus
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.sim.examples import small as small_mod
from axelrod_wm.sim.examples.catalog import Article, Catalog, Example, Step
from axelrod_wm.sim.examples.session import (
    SETUP,
    WAIT_DAYS,
    WAIT_LIMIT,
    ExampleSession,
    ExampleTranslator,
    examples_text,
    feasible,
    run_examples,
)
from axelrod_wm.sim.examples.small import SMALL
from axelrod_wm.sim.runner import build_runner
from axelrod_wm.trace import RecordingTracer

AT = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)


def fresh():
    r = build_runner("small_demo", interactive=True, tracer=RecordingTracer(run_id="t"), storage=MemoryBackend(),
                     record_checklist=False)
    r.load()
    return r


# -- pure helpers -------------------------------------------------------------------------------------
def test_feasible_drops_ops_whose_ends_are_gone():
    graph = SimpleNamespace(entities={"delta": 1}, subentities={"delta.fuel_cost": 1}, interactions={"int-1": 1})
    ops = [
        {"op": "add_entity", "temp_id": "new:jet"},
        {"op": "add_subentity", "entity": "new:jet", "temp_id": "new:jet.price"},
        {"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": "new:jet.price"},
         "target": {"kind": "abstract", "candidate_entity_ids": ["delta", "ghost"]}},
        {"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": "delta.fuel_cost"},
         "target": {"kind": "abstract", "candidate_entity_ids": ["ghost"]}},                 # no candidate left
        {"op": "add_subentity", "entity": "new:never", "temp_id": "new:never.x"},         # its entity was dropped
        {"op": "reweight_interaction", "interaction_id": "int-1"},
        {"op": "retire_interaction", "interaction_id": "int-9"},                         # retired already
    ]
    kept = feasible(ops, graph)
    assert [o["op"] for o in kept] == ["add_entity", "add_subentity", "add_interaction", "reweight_interaction"]
    assert kept[2]["target"]["candidate_entity_ids"] == ["delta"]


def test_the_translator_ignores_articles_that_are_not_examples():
    me = MarketEvent(id="ME-X", kind=MarketEventKind.NEWS, channel=MarketEventChannel.SCRAPER, source="wire",
                     headline="Unrelated", published_at=AT, occurred_at=AT)
    out = ExampleTranslator(runner=SimpleNamespace(event_specs={})).translate(me, None)
    assert out.events == [] and out.rationale == "not an example's article"


# -- the focus a raised proposal gives: hand-built proposals ------------------------------------------
class _Event:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def model_dump(self, mode: str = "python") -> dict:
        return self.payload

    def model_dump_json(self) -> str:
        import json

        return json.dumps(self.payload)


def proposal(pid: str, kind: str, status: str, payload: dict, by: str | None = None):
    return SimpleNamespace(id=pid, kind=kind, status=status, decided_by=by, event=_Event(payload),
                           market_event_id=None)


class _Ctl:
    def __init__(self, *props) -> None:
        self.proposals = {p.id: p for p in props}
        self.deferred: list[str] = []
        self.engine = SimpleNamespace(wm=SimpleNamespace(graph=SimpleNamespace(
            entities={"resources_energy": 1, "delta": 1, "inflation": 1},
            interactions={"int-1": SimpleNamespace(source_id="resources_energy.oil_price", target_id="delta.fuel_cost")})))
        self.updates: dict = {}
        self.active_update = None
        self.now = AT

    def pending_proposals(self):
        return [p for p in self.proposals.values() if str(p.status) == "pending"]

    def defer(self, pid, by):
        self.deferred.append((pid, by))


class Host(ExampleSession):
    def __init__(self, ctl) -> None:
        self.controller = ctl
        self.reset_examples()


@pytest.fixture
def host():
    return Host(_Ctl(
        proposal("P1", "superentity", "pending", {"ops": ["inflation.headline_cpi"]}),
        proposal("P2", "superentity", "deferred", {"ops": ["new:int-1"]}, by=SETUP),       # oil and Delta
        proposal("P3", "superentity", "pending", {"note": "resources_energy"}),
        proposal("P4", "graph_update", "pending", {"ops": ["delta.fuel_cost"]}),
    ))


def test_raised_with_nothing_of_that_kind(host):
    assert host._raised("frontier_promotion") is None


def test_raised_prefers_one_about_every_entity_the_articles_touch(host):
    assert host._raised("superentity", about={"resources_energy", "delta"}) == "P2"
    assert host.controller.proposals["P2"].status == ProposalStatus.PENDING        # back in the queue


def test_raised_with_partial_overlap_waits_unless_settling(host):
    about = {"resources_energy", "delta", "inflation"}
    assert host._raised("superentity", about=about) is None
    assert host._raised("superentity", about=about, settle=True) == "P2"           # the most overlap


def test_raised_without_overlap_falls_back_to_the_story(host):
    assert host._raised("superentity", about={"skybridge"}, settle=True) == "P3"   # it mentions oil


def test_raised_late_takes_whatever_came():
    h = Host(_Ctl(proposal("P1", "superentity", "pending", {"ops": ["inflation.headline_cpi"]})))
    assert h._raised("superentity", preferred_only=True) is None
    assert h._raised("superentity") == "P1"


def test_remember_keeps_only_decided_examples():
    ctl = _Ctl(proposal("P1", "graph_update", "pending", {}), proposal("P2", "graph_update", "approved", {}))
    ctl.proposals["P2"].edited_from = None
    h = Host(ctl)
    h.done = [{"id": "a", "pid": "P1", "by_person": True}, {"id": "b", "pid": "P2", "by_person": True},
              {"id": "c", "pid": "P2", "by_person": False}, {"id": "d", "pid": None, "by_person": True}]
    h._remember()
    assert h.decisions == {"b": {"status": "approved", "ops": None, "manual": None}}


def test_decide_and_settle_leave_finished_work_alone():
    ctl = _Ctl(proposal("P1", "graph_update", ProposalStatus.APPROVED, {}))
    ctl.approve = ctl.reject = ctl.cycle = None            # would fail if called
    ctl.active_update = "U1"
    ctl.updates = {"U1": SimpleNamespace(state=UpdateState.DONE)}
    h = Host(ctl)
    h._decide("P1", "approve")
    h._settle()


def test_about_skips_builders_that_need_later_state():
    def boom(ctl, at):
        raise KeyError("not built yet")

    h = Host(_Ctl())
    h.catalog = SimpleNamespace(ops={"boom": boom, "ok": lambda ctl, at: [{"target": "delta.fuel_cost"}]})
    art = Article(headline="x")
    assert h._about([Step(article=art, ops="boom"), Step(article=art, ops="ok")]) == {"delta"}


def _waiting_host(found_after: int | None):
    ctl = _Ctl(proposal("PR-R", "superentity", "pending", {}), proposal("PR-X", "superentity", "pending", {}))
    h = Host(ctl)
    h.last_event = "EX-007"
    calls = {"advanced": [], "decided": [], "raised": []}
    h._about = lambda steps: {"resources_energy"}
    h._publish = lambda step, override: "PR-A"
    h._decide = lambda pid, action: calls["decided"].append((pid, action))
    h._set_aside = lambda keep_kind, keep=None: None
    h._advance = lambda days: calls["advanced"].append(days)

    def raised(kind, preferred_only=False, about=None, settle=False):
        calls["raised"].append(preferred_only)
        return "PR-R" if found_after is not None and len(calls["raised"]) > found_after else None

    h._raised = raised
    return h, calls


def test_waiting_for_a_raised_proposal():
    h, calls = _waiting_host(found_after=2)
    step = SMALL.example("create").steps[0]
    assert h._run_steps([step], auto=False, raises="superentity") == "PR-R"
    assert calls["decided"] == [("PR-A", "approve")]                 # the article itself is vetted by the setup
    assert calls["advanced"] == [WAIT_DAYS, WAIT_DAYS]
    assert h.controller.deferred == [("PR-X", SETUP)]                # the rest is set aside
    assert h.controller.proposals["PR-R"].market_event_id == "EX-007"  # grounded in the article that tipped it


def test_waiting_gives_up_after_the_limit():
    h, calls = _waiting_host(found_after=None)
    with pytest.raises(ControllerError, match=f"did not raise a superentity proposal in {WAIT_LIMIT} days"):
        h._run_steps([SMALL.example("create").steps[0]], auto=False, raises="superentity")
    assert sum(calls["advanced"]) == WAIT_LIMIT
    assert calls["raised"][1] is True and calls["raised"][-1] is False   # late, it takes whatever came


# -- the small demo's runner ---------------------------------------------------------------------------
def test_a_demo_runner_before_loading_and_its_sessions():
    r = build_runner("small_demo", interactive=True, storage=MemoryBackend(), record_checklist=False)
    st = r.status()
    assert st.loaded is False and st.scenario_id == "small_demo"
    with pytest.raises(ControllerError, match="do not keep sessions"):
        r.resume({})


def test_rerunning_the_waiting_example_and_what_waits_blocks():
    r = fresh()
    first = r.run_example("create")
    with pytest.raises(ControllerError, match="still waits for review"):
        r.run_example("ripple")
    again = r.run_example("1")
    assert again["proposal_id"] == first["proposal_id"] and again["played"] == [] and again["rewound"] is False
    with pytest.raises(ControllerError, match="still waits for review"):
        r.prepare_example("links")
    with pytest.raises(ControllerError, match="still waits for review"):
        r.run_library("rumor")


def test_a_rejected_example_is_skipped_and_replayed_as_rejected():
    r = fresh()
    ctl = r.controller
    pid = r.run_example("create")["proposal_id"]
    ctl.reject(pid, by="backend user", note="not now")
    assert r.examples()[0]["status"] == "skipped"
    links = r.run_example("links")["proposal_id"]
    ctl.approve(links, by="backend user")
    r._settle()
    again = r.run_example("links")                           # a rewind: create is replayed, rejected again
    assert again["rewound"] is True and again["proposal_id"] in {p.id for p in r.controller.pending_proposals()}
    assert "resources_energy" not in r.controller.engine.wm.graph.entities
    replayed = r.controller.proposals[r.done[0]["pid"]]
    assert replayed.status == ProposalStatus.REJECTED and replayed.decided_by == SETUP
    version = r.controller.engine.version
    r._decide(replayed.id, "approve")                       # decided already: nothing changes
    assert replayed.status == ProposalStatus.REJECTED and r.controller.engine.version == version


def test_a_manual_example_that_cannot_be_submitted_is_skipped():
    r = fresh()
    for key in ("create", "links", "refine", "ripple"):
        r.run_example(key)
        r.controller.approve(r.focus["pid"], by="backend user")
        r._settle()
    bad = {"entity": {"id": "air_travel", "name": "Air travel demand", "kind": "starship", "tags": ["SD"]},
           "values": [], "interactions": []}
    res = r.run_example("expert_add", manual=bad)
    assert res["proposal_id"] is None and res["note"].startswith("nothing to change:")
    assert r.examples()[4]["status"] == "skipped"
    assert r.manual_specs["expert_add"] == bad


def test_every_library_event_runs_after_what_it_needs():
    r = fresh()
    ctl = r.controller
    order = sorted(SMALL.library, key=lambda e: SMALL.index(e.after))
    seen = {}
    for ev in order:
        res = r.run_library(ev.id)
        seen[ev.id] = res
        assert res["event"] == ev.id and res["question"] == ev.question
        if res["proposal_id"]:
            assert r.status_of(r.library_runs[-1]) == "waiting"
            if ev.id == "rumor":
                ctl.reject(res["proposal_id"], by="backend user", note="a rumor")
            else:
                ctl.approve(res["proposal_id"], by="backend user")
            r._settle()
        else:
            assert ev.question is not None                    # only the questions raise nothing to review
    assert seen["group-airlines"]["proposal_id"] and seen["retire-northwind"]["proposal_id"]
    assert {x["id"] for x in r.examples()[0]["more"]} == {e.id for e in SMALL.library if e.feature == "creation"}
    assert "skyfreight" in ctl.engine.wm.graph.entities and "jet_fuel" in ctl.engine.wm.graph.entities
    assert "northwind" not in ctl.engine.wm.graph.entities


def test_small_catalog_edits_that_have_nothing_to_edit():
    ctl = fresh().controller
    for key in ("nest", "retire", "dissolve_learned"):
        with pytest.raises(ControllerError):
            SMALL.edits[key](ctl, "backend user")
    assert SMALL.ops["oil_down"](ctl, AT)[0]["delta"] == -0.08
    assert SMALL.ops["fed_hold"](ctl, AT)[0]["value"] == 4.5          # no Fed yet: the default level
    assert SMALL.ops["strengthen"](ctl, AT) == []                     # no oil-to-CPI link yet


# -- small catalogs made for the test -----------------------------------------------------------------
def _catalog(*examples: Example, **ops) -> Catalog:
    return Catalog(name="test", examples=[SMALL.example("create"), *examples], ops={**SMALL.ops, **ops},
                   edits=SMALL.edits)


def _example(eid: str, n: int, steps: list[Step], **kw) -> Example:
    return Example(id=eid, n=n, title=eid, memory="working", stage="working", feature=eid, isolates=eid, summary=eid,
                   watch=[], steps=steps, **kw)


def test_an_article_that_changes_nothing_and_a_quote_not_in_the_text(monkeypatch):
    unquoted = Step(ops="oil_up", article=Article(headline="Brent edges up", body="Oil rose 8%.",
                                                  quotes=[("a phrase it never says", [0]), ("Oil rose 8%", [0])]))
    idle = Step(ops="nothing", article=Article(headline="Markets were quiet"))
    cat = _catalog(_example("edge", 2, [unquoted]), _example("quiet", 3, [idle]), nothing=lambda ctl, at: [])
    monkeypatch.setattr(small_mod, "SMALL", cat)
    records, runner = run_examples("small_demo", only=["edge", "quiet"])
    assert [r["example"].id for r in records] == ["edge", "quiet"]          # create is played, not shown
    edge, quiet = records
    assert edge["review"] is not None and edge["review"].article["spans"]   # only the phrase it says
    assert quiet["review"] is None and quiet["forecast"] is None
    assert runner.done[2]["pid"] is None
    assert runner.examples()[2]["status"] == "skipped"
    assert runner.done[2]["note"] == "nothing to change: what it needs was left out earlier"


def test_a_raised_proposal_that_never_comes(monkeypatch):
    nudge = Step(ops="oil_up", article=Article(headline="Brent edges up", body="Oil rose 8%."))
    cat = _catalog(_example("never", 2, [nudge], focus="raised", raises="no_such_kind"))
    monkeypatch.setattr(small_mod, "SMALL", cat)
    r = fresh()
    r.run_example("create")
    r.controller.approve(r.focus["pid"], by="backend user")
    r._settle()
    day = int(r.controller.engine.wm.last_processed_day)
    with pytest.raises(ControllerError, match=f"did not raise a no_such_kind proposal in {WAIT_LIMIT} days"):
        r.run_example("never")
    assert int(r.controller.engine.wm.last_processed_day) == day + 1 + WAIT_LIMIT    # the article's day, then the wait


def test_examples_text_for_a_thesis():
    ex = SMALL.example("inference")
    text = examples_text([{"example": ex, "review": None, "version_before": 7, "version_after": 7,
                           "forecast": {"id": "FC-1", "based_on_version": 7,
                                        "transmission": [{"value": "delta.fuel_cost", "order": 1, "peak": 0.42}]}}])
    assert text.splitlines()[:2] == [f"{ex.n}. {ex.title}  [inference]", f"   isolates: {ex.isolates}"]
    assert "   forecast FC-1 on version 7 (nothing learned)" in text
    assert "     order 1: delta.fuel_cost peak +0.42 sd" in text and "   version 7 → 7" in text


def test_a_two_way_link_owns_separate_dynamics_for_each_direction():
    """Regression: a bidirectional link without its own reverse used the forward dynamics object for both
    directions, so refitting one moved the other, and a restored state no longer matched its hash."""
    from axelrod_wm.events.graph_update import GraphUpdateEvent
    from axelrod_wm.sim.examples.catalog import dyn

    r = fresh()
    r.run_example("links")
    ctl = r.controller
    ctl.approve(r.focus["pid"], by="backend user")
    r._settle()
    ev = GraphUpdateEvent.model_validate({
        "id": "GUE-TWO-WAY", "kind": "real", "occurred_at": ctl.now.isoformat(), "recorded_at": ctl.now.isoformat(),
        "produced_by": "human", "ops": [{"op": "add_interaction", "label": "move together", "polarity": 1,
                                         "direction": "bidirectional", "dynamics": dyn(0.3, 1, 7),
                                         "source": {"kind": "concrete", "subentity_id": "delta.operating_margin"},
                                         "target": {"kind": "concrete", "subentity_id": "delta.share_price"}}]})
    p = ctl.submit_graph_update(ev, by="backend user")
    if p.status == ProposalStatus.PENDING:
        ctl.approve(p.id, by="backend user")
    inter = next(i for i in ctl.engine.wm.graph.interactions.values() if i.label == "move together")
    assert inter.reverse is not None and inter.reverse is not inter.forward
    assert inter.forward is not ev.ops[0].dynamics
    r._advance(7)                                   # the daily refit runs on both directions
    for v in range(1, ctl.engine.version + 1):
        ctl.engine.snapshots.restore(v)             # raises RestoreError on a hash mismatch
