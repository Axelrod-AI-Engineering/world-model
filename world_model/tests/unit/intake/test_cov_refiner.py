"""The refiner's rarer paths (§7.5): ends it cannot place, subentities it must name apart, pattern bonuses, and how a
hedge weighs later evidence (narrowing, mentions, moves for and against, spacing) and settles."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from axelrod_wm.events.graph_update import (
    AbstractTarget,
    AddInteraction,
    ChangeValue,
    ConcreteTarget,
    Specificity,
)
from axelrod_wm.intake.refiner import Refiner, TaxonomyRefiner
from axelrod_wm.memory.working import HedgeCheck, PendingRefinement
from axelrod_wm.trace import NullTracer
from tests.conftest import make_config, make_controller, real_event, warm_taxonomies

AT = datetime(2026, 2, 9, 14, 0, tzinfo=UTC)


@pytest.fixture
def ctl():
    c = make_controller()
    warm_taxonomies(c.engine)
    c.advance_now(AT)
    return c


def change(target: dict) -> dict:
    return {"op": "change_value", "target": {"kind": "abstract", **target}, "delta": 0.1, "mode": "relative",
            "at": AT.isoformat()}


def test_the_base_refiner_weighs_no_hedges():
    class Bare(Refiner):
        def refine(self, event, wm, ltm, ctx):
            return super().refine(event, wm, ltm, ctx)

    r = Bare()
    assert r.refine(None, None, None, None) is None
    assert r.weigh_hedges(None, None, None, None, None, None) == []


def test_given_vocabulary_wins_over_the_engines():
    vocab = object()
    assert TaxonomyRefiner(vocab=vocab).vocab is vocab
    assert TaxonomyRefiner().vocab.kinds == {}            # no engine: an empty vocabulary


def test_candidates_without_a_mention_or_attribute_stay_hedged(ctl):
    # no attribute kind: every candidate can take the change; no mention: none is named
    ref = ctl.refine(real_event([change({"candidate_entity_ids": ["inflation", "resources_energy"]})], "GUE-c", AT))
    (pend,) = ref.pending
    assert pend.reached == Specificity.GENERALIZATION
    assert set(pend.candidates) == {"inflation", "resources_energy"}


def test_unknown_entity_falls_back_to_the_taxonomy_walk(ctl):
    # an entity id not in the graph is ignored; with no attribute, constraint, or mention nothing narrows the walk
    ref = ctl.refine(real_event([change({"entity_id": "no_such_entity"})], "GUE-u", AT))
    (pend,) = ref.pending
    assert pend.reached == Specificity.GENERALIZATION and ref.event.ops == []


def test_constraints_steer_the_walk(ctl):
    ref = ctl.refine(real_event([change({"attribute_kind": "policy_rate", "constraints": {"region": "EA"},
                                         "mention": "rates"})], "GUE-k", AT))
    walked = [s.node_id for s in ref.steps if s.op_index == 0]
    assert walked, "the constraint should let the walk leave the root"


def test_a_created_subentity_never_reuses_an_existing_id(ctl):
    # the energy entity has no spending flow, so one is created; "oil price" would collide with oil_price
    ref = ctl.refine(real_event([change({"entity_id": "resources_energy", "attribute_kind": "spending_flow",
                                         "mention": "oil price"})], "GUE-n", AT))
    created = ref.event.ops[0]
    assert created.op == "add_subentity" and created.temp_id == "new:resources_energy.oil_price_2"
    assert ref.event.ops[1].target.subentity_id == "new:resources_energy.oil_price_2"


def test_relation_reads_features_and_skips_values_it_does_not_know(ctl):
    g = ctl.engine.wm.graph
    g.entities["federal_reserve"].generalization_id = None     # an entity not classified yet
    ops = [{"op": "add_entity", "temp_id": "new:acme", "name": "Acme", "kind": "company"},
           {"op": "add_subentity", "entity": "new:acme", "temp_id": "new:acme.sales", "name": "Sales",
            "attribute_kind": "spending_flow", "unit": "usd"},
           {"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": "new:acme.sales"},
            "target": {"kind": "abstract", "mention": "zzz"}, "label": "lifts", "polarity": 1},
           {"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": "federal_reserve.policy_stance"},
            "target": {"kind": "abstract", "mention": "zzz"}, "label": "lifts", "polarity": 1}]
    ref = ctl.refine(real_event(ops, "GUE-r", AT))
    assert len(ref.pending) == 2 and all(p.reached == Specificity.GENERALIZATION for p in ref.pending)


def test_a_pattern_relation_favors_the_patterns_members(ctl):
    op = {"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": "resources_energy.oil_price"},
          "target": {"kind": "abstract", "mention": "prices"}, "label": "raises", "polarity": 1,
          "pattern_relation": {"pattern_id": "S2", "relation_index": 0}}
    with_bonus = ctl.refine(real_event([op], "GUE-p", AT))
    r = TaxonomyRefiner(vocab=ctl.engine.vocab)
    eng = ctl.engine
    bonus = r._pattern_bonus(AddInteraction.model_validate(op), eng.wm, eng.ltm)
    assert {"inflation", "resources_energy"} <= bonus
    for bad in ({"pattern_id": "nope", "relation_index": 0}, {"pattern_id": "S2", "relation_index": 999}):
        assert r._pattern_bonus(AddInteraction.model_validate({**op, "pattern_relation": bad}), eng.wm, eng.ltm) == set()
    no_ref = AddInteraction.model_validate({k: v for k, v in op.items() if k != "pattern_relation"})
    assert r._pattern_bonus(no_ref, eng.wm, eng.ltm) == set()
    assert with_bonus.pending or with_bonus.event.ops
    # a role the pattern does not define, or one whose kind is not in the taxonomy, adds no members
    pat = SimpleNamespace(id="P", relations=[SimpleNamespace(source_role="a", target_role="b")],
                          role=lambda n: None if n == "a" else SimpleNamespace(generalization_id="gen:obj:none"))
    ltm = SimpleNamespace(object_generalizations=SimpleNamespace(patterns={"P": pat}, taxonomy=SimpleNamespace(nodes={})))
    wm = SimpleNamespace(graph=SimpleNamespace(instances={"i": SimpleNamespace(pattern_id="P", bindings={"a": "x"})}))
    odd = AddInteraction.model_validate({**op, "pattern_relation": {"pattern_id": "P", "relation_index": 0}})
    assert r._pattern_bonus(odd, wm, ltm) == {"x"}


def test_partial_op_leaves_a_concrete_end_as_it_is():
    op = ChangeValue(target=ConcreteTarget(subentity_id="a.b"), delta=0.1, mode="relative", at=AT)
    out = TaxonomyRefiner._partial_op(op, {"subject": {"level": Specificity.GENERALIZATION, "ref": "gen:obj:x"}})
    assert out.target == ConcreteTarget(subentity_id="a.b")


def test_hedge_candidates_drop_ids_no_longer_in_the_graph():
    g = SimpleNamespace(entities={}, subentities={"a.b": object()})
    r = TaxonomyRefiner(vocab=SimpleNamespace(is_a=lambda k, a: k == a))
    got = r._hedge_candidates(AbstractTarget(), {"candidates": [("gone", 0.9), ("a.b", 0.4), ("new:v.w", 0.3)]}, g,
                              [], 4)
    assert got == [("a.b", 0.4), ("v.w", 0.3)]


# -- weighing a hedge against later evidence -------------------------------------------------------------
NOW = datetime(2026, 3, 1, tzinfo=UTC)
DAY = 40


def _sub(sid, name, kind="price", aliases=()):
    return SimpleNamespace(id=sid, entity_id=sid.split(".")[0], name=name, aliases=list(aliases), attribute_kind=kind,
                           features={})


def _world(changes: dict[str, float]):
    subs = {s.id: s for s in [_sub("oil.price", "oil price"), _sub("delta.fare", "air fare"),
                              _sub("united.fare", "ticket price"), _sub("delta.cost", "jet fuel cost", kind="cost")]}
    ents = {"oil": SimpleNamespace(name="Oil", aliases=[], subentity_ids=["oil.price"]),
            "delta": SimpleNamespace(name="Delta", aliases=["DAL"], subentity_ids=["delta.fare", "delta.cost"]),
            "united": SimpleNamespace(name="United", aliases=[], subentity_ids=["united.fare"])}
    graph = SimpleNamespace(entities=ents, subentities=subs, interactions={})
    dev = SimpleNamespace(day_of=lambda t: DAY - (NOW - t).days, window_change=lambda sid, day, w: changes.get(sid, 0.0))
    return SimpleNamespace(graph=graph, deviations=dev, pending_refinements={})


class Txn:
    def __init__(self):
        self.updates = []

    def update(self, where, key, **fields):
        self.updates.append((where, key, fields))


def _ctx(wm):
    return SimpleNamespace(initializing=False, config=make_config(), today=DAY, notes={"headline": "news"}, now=NOW,
                           tracer=NullTracer(), recognition=2, wm=wm)


def _edge(source, target):
    return AddInteraction(source=source, target=target, label="raises", polarity=1)


def _pend(pid, op, alpha, *, ends=("target",), support=0.0, checks=(), soft=False):
    return PendingRefinement(id=pid, key=pid, op=op, end=ends[0], ends=list(ends), reached=Specificity.ENTITY,
                             node_id="x", candidates={k: 0.0 for k in alpha}, alpha=dict(alpha), open_alpha=0.5,
                             evidence=[], source_event_id="GUE-old", created_at=NOW - timedelta(days=5),
                             expires_at=NOW + timedelta(days=30), polarity=1, support=support, checks=list(checks),
                             soft=soft, attribute_filter=["price"])


def _weigh(wm, event, moved=None):
    r = TaxonomyRefiner(vocab=SimpleNamespace(is_a=lambda k, a: k == a))
    txn = Txn()
    fold = SimpleNamespace(day=DAY, innovations=moved or {})
    out = r.weigh_hedges(event, SimpleNamespace(shocks=[]), fold, wm, _ctx(wm), txn)
    return out, txn


def test_a_named_value_narrows_an_entity_candidate_and_counts_as_a_mention():
    wm = _world({})
    op = _edge(ConcreteTarget(subentity_id="oil.price"), AbstractTarget(mention="airlines"))
    wm.pending_refinements["P1"] = _pend("P1", op, {"delta": 1.0, "united.fare": 1.0})
    out, txn = _weigh(wm, real_event([], "GUE-new", NOW, mentions=["", "Delta's air fare"]))
    assert out == []
    (_, pid, fields), = [u for u in txn.updates if u[0] == "wm.pending_refinements"]
    assert pid == "P1" and set(fields["alpha"]) == {"delta.fare", "united.fare"}
    kinds = [(c.kind, c.candidate) for c in fields["checks"]]
    assert ("narrowed", "delta.fare") in kinds and ("mention", "delta.fare") in kinds
    assert fields["alpha"]["delta.fare"] == pytest.approx(1.0 + 1.5) and fields["support"] == 1


def test_moves_for_and_against_and_the_spacing_between_them():
    wm = _world({"oil.price": 1.0})
    op = _edge(ConcreteTarget(subentity_id="oil.price"), AbstractTarget(mention="fares"))
    recent = HedgeCheck(at=NOW - timedelta(days=2), event_id="E0", kind="move", candidate="united.fare")
    wm.pending_refinements["P1"] = _pend("P1", op, {"delta.fare": 1.0, "united.fare": 1.0, "delta.cost": 1.0},
                                         checks=[recent])
    # delta's fare rose with oil (for), its fuel cost fell (against), united's was checked two days ago (spaced out)
    out, txn = _weigh(wm, real_event([], "GUE-new", NOW), moved={"delta.fare": 0.8, "united.fare": 0.9,
                                                                    "delta.cost": -0.7})
    (_, _, fields), = [u for u in txn.updates if u[0] == "wm.pending_refinements"]
    kinds = sorted((c.kind, c.candidate) for c in fields["checks"] if c.event_id == "GUE-new")
    assert kinds == [("against", "delta.cost"), ("move", "delta.fare")]
    assert fields["checks"][0] == recent                     # the earlier checks are kept
    assert fields["alpha"]["delta.fare"] == pytest.approx(1.0 + 1.0 + 1.0 / 3)    # its move, and a share of the against
    assert fields["open_alpha"] == pytest.approx(0.5 + 1.0 / 3)
    assert not [u for u in txn.updates if u[0] == "wm.graph.interactions"]        # not soft: no interactions to move


def test_moves_need_both_ends_and_a_moving_driver():
    wm = _world({})
    both_fuzzy = _edge(AbstractTarget(mention="x"), AbstractTarget(mention="y"))
    wm.pending_refinements["P1"] = _pend("P1", both_fuzzy, {"delta.fare": 1.0})
    flat = _edge(ConcreteTarget(subentity_id="oil.price"), AbstractTarget(mention="y"))
    wm.pending_refinements["P2"] = _pend("P2", flat, {"delta.fare": 1.0})
    out, txn = _weigh(wm, real_event([], "GUE-new", NOW), moved={"delta.fare": 1.0})
    assert out == [] and txn.updates == []          # P1 has no source; P2's driver did not move


def test_a_non_soft_hedge_resolves_to_the_concrete_op():
    wm = _world({})
    op = _edge(ConcreteTarget(subentity_id="oil.price"), AbstractTarget(mention="fares"))
    wm.pending_refinements["P1"] = _pend("P1", op, {"delta.fare": 10.0, "united.fare": 0.1}, support=5)
    out, txn = _weigh(wm, real_event([], "GUE-new", NOW, mentions=["Delta"]))
    (prop,) = out
    assert prop["subject_id"] == "P1" and prop["reason"].startswith("delta.fare at")
    (new_op,) = prop["event"]["ops"]
    assert new_op["source"]["subentity_id"] == "oil.price" and new_op["target"]["subentity_id"] == "delta.fare"
    assert ("wm.pending_refinements", "P1", {"status": "resolution_proposed"}) in txn.updates


@pytest.mark.parametrize("winner_alpha, op", [
    # the winner is a whole entity: it still needs its value
    ({"delta": 10.0}, _edge(ConcreteTarget(subentity_id="oil.price"), AbstractTarget(mention="fares"))),
    # the other end is not concrete either
    ({"delta.fare": 10.0}, _edge(AbstractTarget(mention="oil"), AbstractTarget(mention="fares"))),
])
def test_a_resolution_that_cannot_be_made_concrete_keeps_hedging(winner_alpha, op):
    wm = _world({})
    wm.pending_refinements["P1"] = _pend("P1", op, winner_alpha, support=5)
    out, txn = _weigh(wm, real_event([], "GUE-new", NOW, mentions=["Delta"]))
    assert out == [] and not any(u[2].get("status") for u in txn.updates)


def test_soft_hedges():
    r = TaxonomyRefiner(vocab=SimpleNamespace(is_a=lambda k, a: k == a))
    g = SimpleNamespace(interactions={})
    op = _edge(ConcreteTarget(subentity_id="oil.price"), AbstractTarget(mention="fares"))
    assert r._soft_interactions(_pend("P", op, {"a": 1.0}), g) == {}             # not soft
    assert r._soft_interactions(_pend("P", op, {"a": 1.0}, soft=True).model_copy(update={"key": None}), g) == {}
    # a winner without a soft interaction of its own cannot be kept
    ctx = _ctx(_world({}))
    assert r._resolution(_pend("P", op, {"a": 1.0}, soft=True), "b", {"a": "i1"}, real_event([], "E", NOW), ctx) is None
