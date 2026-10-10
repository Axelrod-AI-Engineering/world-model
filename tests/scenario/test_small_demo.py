"""The small demo (Oct 8 restructure): a blank canvas built up by a chain of examples, one feature each, every one
grounded in a sample article and stopped at a staged review. Running an example plays the ones before it; running
an earlier one rewinds; library events add more of the same kind."""

from __future__ import annotations

import pytest

from axelrod_wm.control.controller import ControllerError
from axelrod_wm.control.stage import stage
from axelrod_wm.repo.ledger import LedgerKind
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.sim.examples.session import REVIEWER, run_examples
from axelrod_wm.sim.examples.small import SMALL
from axelrod_wm.sim.runner import build_runner
from axelrod_wm.trace import RecordingTracer


@pytest.fixture(scope="module")
def chain():
    records, runner = run_examples("small_demo")
    return {r["example"].id: r for r in records}, runner


def fresh():
    r = build_runner("small_demo", interactive=True, tracer=RecordingTracer(run_id="t"), storage=MemoryBackend(),
                     record_checklist=False)
    r.load()
    return r


def test_every_example_ran_from_a_blank_canvas(chain):
    by, runner = chain
    assert list(by) == [e.id for e in SMALL.examples]
    assert not fresh().controller.engine.wm.graph.entities
    g = runner.controller.engine.wm.graph
    assert {"resources_energy", "delta", "inflation", "federal_reserve", "skybridge", "northwind",
            "alpenflug"} <= set(g.entities)
    assert all(s == "done" for s in (x["status"] for x in runner.examples()))


def test_each_event_example_is_grounded_in_its_article_and_reviewed(chain):
    by, runner = chain
    ctl = runner.controller
    for ex in SMALL.examples:
        r = by[ex.id]["review"]
        if ex.kind == "thesis":
            continue
        assert r is not None and not r.error, ex.id
        assert [s.phase for s in r.stages] == ["intake", "working", "long_term", "review", "commit"]
        assert ctl.proposals[r.proposal_id].decided_by == REVIEWER
        if ex.kind == "event":
            assert r.article is not None and r.article["headline"] == ex.steps[-1].article.headline
            if ex.focus == "last" and ex.steps[-1].article.quotes and r.items:
                assert r.article["spans"], ex.id          # the phrases that asked for the operations


def test_working_memory_features(chain):
    by, runner = chain
    g = runner.controller.engine.wm.graph
    assert g.entities["resources_energy"].generalization_id == "gen:obj:commodity"
    assert "refinement step" in by["refine"]["review"].stages[0].output
    order = {a.subentity_id: a for a in by["ripple"]["review"].ripple}
    assert order["delta.fuel_cost"].order == 1 and order["delta.fuel_cost"].peak > 0
    assert order["delta.operating_margin"].order == 2 and order["delta.operating_margin"].peak < 0
    assert order["delta.share_price"].order == 3 and order["delta.share_price"].peak < 0
    fold = {x.kind: x for x in by["fold"]["review"].learned}
    assert fold["effect"].after > fold["effect"].before
    weak = next(x for x in by["weaken"]["review"].learned if x.kind == "existence")
    assert weak.after < weak.before
    assert by["delete"]["review"].marks["retired"]


def test_long_term_memory_features(chain):
    by, runner = chain
    ltm = runner.controller.engine.ltm
    assert any("gains SkyBridge" in x for x in by["inherit"]["review"].lessons)
    assert any("entity memory records a decision: it raised" in x for x in by["memory"]["review"].lessons)
    analog = by["analog"]["review"]
    assert any(x["kind"] == "day" and "Brent jumps 20%" in x["label"] for x in analog.recalled)
    assert analog.adjusted
    # a fuzzy end is hedged: both carriers and an open share, a soft interaction to each margin
    hedge = by["pending"]["review"].pending[0]
    assert [c["id"] for c in hedge["candidates"]] == ["delta.operating_margin", "skybridge.operating_margin", "__open__"]
    assert hedge["soft"] and sum(1 for it in by["pending"]["review"].items if it.hedge) == 2
    # a named but unconfirmed mention narrows to Delta yet stays a hedge, until moves agree with it
    assert [it.probability for it in by["refine"]["review"].items if it.hedge] == [pytest.approx(2 / 3, abs=1e-3)]
    # later articles that name Delta's fuel cost carry the jet-fuel hedge past the bound, check by check
    jet = next(pd for pd in runner.controller.engine.wm.pending_refinements.values() if pd.key == "pending:GUE-EX-003:0")
    assert jet.status == "resolution_proposed" and jet.posterior()["delta.fuel_cost"] >= 0.75
    assert jet.support >= 2 and "mention" in {ck.kind for ck in jet.checks}
    # one later article is not enough: the resolution needs mentions and a move of SkyBridge's own margin; it keeps
    # SkyBridge and retires Delta's soft interaction
    res = by["resolve"]["review"]
    assert res.kind == "refinement" and res.resolves["winner"]["id"] == "skybridge.operating_margin"
    assert [c["kind"] for c in res.resolves["checks"]] == ["intake", "mention", "mention", "move"]
    assert [it.action for it in res.items] == ["reweight", "retire"] and "Delta" in res.items[1].label
    assert by["superentity"]["review"].kind == "superentity_admission"
    promo = by["frontier"]["review"]
    assert promo.kind == "frontier_promotion" and "fare" in promo.items[0].label
    assert any("splits off" in x for x in by["split"]["review"].lessons)
    # nesting (Oct 9): two superentities become the parts of one; expanding it leaves both parts
    nest = by["nest"]["review"]
    assert nest.kind == "superentity_admission"
    pats = ltm.object_generalizations.patterns
    assert pats["SE-NEST"].sub_pattern_ids[0] == "SE-POLICY" and str(pats["SE-NEST"].status) == "dissolved"
    assert str(pats["SE-POLICY"].status) == "admitted"
    # a correlation gains strength before it is proposed: a check it passes, and nothing raised yet
    corr = by["correlate"]["review"]
    assert any("Oil price (Brent) → Delta average fare" in x and "gains strength" in x for x in corr.lessons)
    assert corr.kind == "graph_update" and not corr.raises
    # a superentity the model itself admitted (example 13) is deleted by a person: dissolved, history kept
    gone = by["retire_superentity"]["review"]
    assert gone.kind == "superentity_dissolution" and any("admitted → dissolved" in x for x in gone.lessons)


def test_inference_learns_nothing(chain):
    by, _ = chain
    p = by["inference"]
    assert p["forecast"]["based_on_version"] == p["version_before"] == p["version_after"]


def test_staging_is_a_dry_run_and_a_selection_commits_only_itself():
    r = fresh()
    ctl, eng = r.controller, r.controller.engine
    out = r.run_example("select")
    pid = out["proposal_id"]
    assert out["played"] == ["create", "links", "refine", "ripple", "expert_add"]
    before = (eng.version, eng.state_hash, eng.ledger.next_seq, len(r.tracer.events))
    some = stage(ctl, pid, keep=[0, 1, 3, 4, 5, 6])          # leave out the Fed: its value and links go too
    assert some.keep == [0, 1, 4]
    assert (eng.version, eng.state_hash, eng.ledger.next_seq, len(r.tracer.events)) == before
    with pytest.raises(ControllerError):
        r.run_example("fold")                               # one example waits for review at a time
    ctl.approve(pid, by="backend user", keep=[0, 1, 4])
    r._settle()
    assert "federal_reserve" not in eng.wm.graph.entities and "inflation" in eng.wm.graph.entities
    actions = [e.payload["action"] for e in eng.ledger.of_kind(LedgerKind.REVIEW_DECISION) if e.payload["proposal_id"] == pid]
    assert actions[:2] == ["edited", "approved"]


def test_rewind_replays_the_earlier_decisions():
    r = fresh()
    ctl = r.controller
    pid = r.run_example("select")["proposal_id"]
    ctl.approve(pid, by="backend user", keep=[0, 1, 4])     # no Fed
    r._settle()
    r.run_example("fold")
    ctl.approve(r.focus["pid"], by="backend user")
    r._settle()
    out = r.run_example("ripple")                            # rewind to example 4
    assert out["rewound"] and r.focus["id"] == "ripple"
    assert [x["status"] for x in r.examples()][:4] == ["done", "done", "done", "waiting"]
    assert "inflation" not in r.controller.engine.wm.graph.entities
    r.controller.approve(out["proposal_id"], by="backend user")
    r._settle()
    r.run_example("fold")                                    # plays 5 again, with the selection made before
    g = r.controller.engine.wm.graph
    assert "inflation" in g.entities and "federal_reserve" not in g.entities


def test_library_events_run_on_the_current_state():
    r = fresh()
    out = r.run_library("fuel-spike")
    assert out["played"] == ["create", "links", "refine", "ripple"]
    review = stage(r.controller, out["proposal_id"], with_graph=False)
    assert review.moves[0].subentity_id == "delta.fuel_cost"
    assert any(a.subentity_id == "delta.operating_margin" and a.order == 1 for a in review.ripple)
    more = next(x for x in r.examples() if x["id"] == "ripple")["more"]
    assert {m["id"] for m in more} >= {"oil-falls", "fuel-spike"}


def test_the_reviewers_confidence_goes_into_the_data():
    r = fresh()
    ctl, eng = r.controller, r.controller.engine
    pid = r.run_example("select")["proposal_id"]
    # staged at half confidence, with one interaction (oil -> CPI, op 4) at a fifth: nothing live changes
    half = stage(ctl, pid, confidence=0.5, op_confidence={4: 0.2}, with_graph=False)
    assert half.confidence == 0.5 and half.items[0].confidence == 0.5
    assert half.items[4].confidence == 0.2 and half.items[4].own_confidence
    ctl.approve(pid, by="backend user", confidence=0.5, op_confidence={4: 0.2})
    r._settle()
    g = eng.wm.graph
    assert g.entities["inflation"].user_confidence == 0.5 and g.subentities["inflation.headline_cpi"].user_confidence == 0.5
    oil_cpi = next(i for i in g.interactions.values() if i.target_id == "inflation.headline_cpi")
    assert oil_cpi.evidence[0].user_confidence == 0.2
    assert oil_cpi.existence.mean() < 0.8                   # the article's firm prior (0.9), shrunk toward 0.5
    actions = [e.payload["action"] for e in eng.ledger.of_kind(LedgerKind.REVIEW_DECISION) if e.payload["proposal_id"] == pid]
    assert "confidence" in actions
    # a report the reviewer half-trusts moves its value less
    fold_pid = r.run_example("fold")["proposal_id"]
    full = {x.ref: x for x in stage(ctl, fold_pid, with_graph=False).learned if x.kind != "effect"}
    weak = {x.ref: x for x in stage(ctl, fold_pid, confidence=0.2, with_graph=False).learned if x.kind != "effect"}
    ref = next(k for k in full if k in weak)
    assert abs(weak[ref].after - weak[ref].before) < abs(full[ref].after - full[ref].before)


def test_rejecting_a_resolution_keeps_the_hedge():
    r = fresh()
    ctl = r.controller
    pid = r.run_example("resolve")["proposal_id"]
    pend_id = ctl.proposals[pid].retires_pending_id
    before = ctl.engine.wm.pending_refinements[pend_id].posterior()
    ctl.reject(pid, by="backend user", note="not convinced yet")
    after = ctl.engine.wm.pending_refinements[pend_id]
    assert after.status == "holding" and after.checks[-1].kind == "rejected"
    top = max(before, key=lambda k: before[k] if k != "__open__" else -1)
    assert after.posterior()[top] < before[top]


def check_examples_show_what_their_articles_say(records, runner) -> list[str]:
    """Each example's review is grounded in its own last article, and what it focuses on (and so draws) involves
    what its articles touch: a raised proposal involves every entity they touch. No hull is labelled with an entity
    outside it. (Oct 9: example 13 once drew a SkyBridge superentity for an article about Delta.)"""
    import re

    from axelrod_wm.api.views import build_graph_view

    ctl = runner.controller
    bad = []
    for rec in records:
        ex, rv = rec["example"], rec.get("review")
        if ex.kind == "thesis" or rv is None:
            continue
        if ex.kind == "event" and (rv.article or {}).get("headline") != ex.steps[-1].article.headline:
            bad.append(f"{ex.id}: grounded in {(rv.article or {}).get('headline')!r}")
        about = runner._about(ex.steps) if ex.steps else set()
        focus = runner._entities_in(ctl.proposals[rv.proposal_id].event.model_dump(mode="json"))
        if about and not about & focus:
            bad.append(f"{ex.id}: focus {sorted(focus)} shares nothing with {sorted(about)}")
        if about and ex.focus == "raised" and not about <= focus:
            bad.append(f"{ex.id}: raised focus {sorted(focus)} misses some of {sorted(about)}")
    g = ctl.engine.wm.graph
    view = build_graph_view(ctl.engine.wm, ctl.engine.ltm, ctl, ctl.engine.version)
    for h in view.hulls:
        for eid, e in g.entities.items():
            nm = e.name.split(" (")[0]
            if eid not in h.members and len(nm) >= 3 and re.search(r"\b" + re.escape(nm) + r"\b", h.label):
                bad.append(f"hull {h.label!r} names {nm}, outside it")
    return bad


def test_every_example_shows_what_its_articles_say(chain):
    by, runner = chain
    records = [by[e.id] for e in SMALL.examples]
    assert not check_examples_show_what_their_articles_say(records, runner)


def test_practitioner_knowledge_needs_no_article(chain):
    """Oct 9: the manual examples add what a backend user knows, with no article; it is reviewed like any article,
    carries their confidence and reason, and later news ripples through it."""
    by, runner = chain
    g = runner.controller.engine.wm.graph
    add = by["expert_add"]["review"]
    assert add.article is None and add.manual and "revenue management" in add.manual["note"]
    assert add.confidence == 0.7 and all(it.confidence == 0.7 for it in add.items)
    assert g.entities["air_travel"].user_confidence == 0.7
    link = next(i for i in g.interactions.values() if i.source_id == "air_travel.passengers")
    assert link.evidence[0].excerpt.startswith("From years") and link.evidence[0].user_confidence == 0.7
    assert by["expert_link"]["review"].confidence == 0.5
    ripple = {a.subentity_id: a.order for a in by["memory"]["review"].ripple}
    assert ripple.get("air_travel.passengers") == 1 and ripple.get("delta.operating_margin") == 2


def test_a_person_can_change_the_prefilled_form():
    r = fresh()
    spec = dict(SMALL.example("expert_add").manual)
    spec = {**spec, "confidence": 0.4, "values": [{**spec["values"][0], "typical": 95.0}]}
    pid = r.run_example("expert_add", manual=spec)["proposal_id"]
    assert stage(r.controller, pid, with_graph=False).confidence == 0.4
    r.controller.approve(pid, by="backend user")
    r._settle()
    assert r.controller.engine.wm.graph.entities["air_travel"].user_confidence == 0.4


def test_a_manual_example_opens_over_the_examples_before_it():
    """Oct 9: preparing a practitioner example brings the canvas to just before it (the earlier examples played, the
    example itself not run), so its form opens over what they built; staging it then plays nothing more."""
    r = fresh()
    out = r.prepare_example("expert_add")
    assert out["played"] == ["create", "links", "refine", "ripple"] and not out["rewound"]
    g = r.controller.engine.wm.graph
    assert "delta" in g.entities and "air_travel" not in g.entities and not r.controller.pending_proposals()
    staged = r.run_example("expert_add")
    assert staged["played"] == [] and staged["proposal_id"]
    r.controller.approve(staged["proposal_id"], by="backend user")
    r._settle()
    back = r.prepare_example("expert_add")                       # opening it again goes back to just before it
    assert back["rewound"] and "air_travel" not in r.controller.engine.wm.graph.entities
