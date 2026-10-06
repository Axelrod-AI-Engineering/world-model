"""Taxonomies: classification paths, prior sources, ties, path updates, growth, derived signatures."""

from __future__ import annotations

from datetime import datetime, timezone

from axelrod_wm.core.distributions import Gaussian
from axelrod_wm.core.evidence import Origin
from axelrod_wm.core.taxonomy import (
    AttributeKind,
    AttributeVocabulary,
    Generalization,
    GeneralizationStats,
    Signature,
    Taxonomy,
    TaxonomyKind,
)
from axelrod_wm.engine.classify import SplitOnSharedFeatureGrower, descend
from tests.conftest import constructed_engine, real_event, warm_taxonomies

AT = datetime(2026, 2, 16, 5, 30, tzinfo=timezone.utc)

ME04_OPS = [
    {"op": "add_entity", "temp_id": "new:rbi", "name": "Reserve Bank of India", "kind": "agency",
     "category_tags": ["MF"], "features": {"region": "IN", "function": "monetary_policy"}, "aliases": ["RBI"]},
    {"op": "add_subentity", "entity": "new:rbi", "temp_id": "new:rbi.policy_stance", "name": "Repo rate decision",
     "attribute_kind": "policy_rate", "unit": "pct"},
    {"op": "add_subentity", "entity": "interest_rates", "temp_id": "new:interest_rates.india_policy_rate",
     "name": "India policy rate", "attribute_kind": "policy_rate", "unit": "pct", "features": {"region": "IN"}},
    {"op": "add_subentity", "entity": "credit_availability", "temp_id": "new:credit_availability.india_bank_funding_cost",
     "name": "Indian bank funding cost", "attribute_kind": "bank_funding_cost", "unit": "pct", "features": {"region": "IN"}},
    {"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": "new:rbi.policy_stance"},
     "target": {"kind": "concrete", "subentity_id": "new:interest_rates.india_policy_rate"}, "label": "sets", "polarity": 1},
    {"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": "new:interest_rates.india_policy_rate"},
     "target": {"kind": "concrete", "subentity_id": "new:credit_availability.india_bank_funding_cost"},
     "label": "raises funding costs", "polarity": 1},
]


def _int_between(eng, a, b):
    ids = eng.wm.graph.interaction_between(a, b)
    assert ids, (a, b)
    return eng.wm.graph.interactions[ids[0]]


def test_rbi_and_india_edge_classify_and_inherit(warm_engine):
    eng = warm_engine
    res = eng.learning.run(real_event(ME04_OPS, "GUE-ME04", AT, produced_by="hand_drawn"), AT, 0)
    paths = {c.item_id: c for c in res.shared.classifications}
    assert paths["rbi"].path == ["gen:obj:root", "gen:obj:actor", "gen:obj:monetary_authority", "gen:obj:central_bank"]
    g = eng.wm.graph
    assert g.subentities["rbi.policy_stance"].prior_source_id == "gen:obj:central_bank"
    assert g.subentities["interest_rates.india_policy_rate"].prior_source_id == "gen:obj:price_of_credit"
    funding = _int_between(eng, "interest_rates.india_policy_rate", "credit_availability.india_bank_funding_cost")
    assert funding.generalization_id == "gen:int:policy_rate_to_bank_funding"
    assert funding.prior_source_id == "gen:int:policy_rate_to_bank_funding"
    sets = _int_between(eng, "rbi.policy_stance", "interest_rates.india_policy_rate")
    assert sets.generalization_id == "gen:int:policy_setting"
    assert funding.forward.effect.mean() > 0 and funding.origin == Origin.EVENT_PARSING


def test_prior_source_respects_the_recall_threshold():
    eng = constructed_engine(build=True)          # supports are 0: nothing is supported
    eng.learning.run(real_event(ME04_OPS, "GUE-ME04", AT), AT, 0)
    sub = eng.wm.graph.subentities["rbi.policy_stance"]
    assert sub.prior_source_id in ("graph", "vocabulary")
    assert eng.ltm.object_generalizations.taxonomy.nodes["gen:obj:central_bank"].stats.support == 1.0


def test_chip_edge_classifies_under_technology_diffusion(warm_engine):
    eng = warm_engine
    eng.learning.run(real_event([{"op": "add_subentity", "entity": "cross_border_trade",
                                  "temp_id": "new:cross_border_trade.chip_exports", "name": "Chip exports",
                                  "attribute_kind": "trade_flow", "unit": "index",
                                  "features": {"product": "semiconductors"}}], "GUE-A", AT), AT, 0)
    eng.learning.run(real_event([{"op": "add_interaction",
                                  "source": {"kind": "concrete", "subentity_id": "cross_border_trade.chip_exports"},
                                  "target": {"kind": "concrete", "subentity_id": "productivity_tech.tech_capex"},
                                  "label": "supports investment by chip users", "polarity": 1}], "GUE-B", AT), AT, 0)
    inter = _int_between(eng, "cross_border_trade.chip_exports", "productivity_tech.tech_capex")
    assert inter.generalization_id == "gen:int:technology_diffusion"
    sub = eng.wm.graph.subentities["cross_border_trade.chip_exports"]
    assert sub.prior_source_id == "gen:obj:demand_flow" and sub.posterior.family == "lognormal"


def test_classification_never_overwrites_supplied_priors(warm_engine):
    eng = warm_engine
    op = {"op": "add_subentity", "entity": "inflation", "temp_id": "new:inflation.services_cpi", "name": "Services CPI",
          "attribute_kind": "inflation_rate", "unit": "pct", "prior": {"family": "gaussian", "mu": 4.0, "sigma": 0.3},
          "scale": 0.3}
    edge = {"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": "new:inflation.services_cpi"},
            "target": {"kind": "concrete", "subentity_id": "inflation.core_cpi"}, "label": "feeds", "polarity": 1,
            "dynamics": {"effect": {"family": "gaussian", "mu": 0.77, "sigma": 0.1},
                         "kernel": {"delay_days": 3, "lag_days": 5, "duration_days": None}}}
    eng.learning.run(real_event([op, edge], "GUE-P", AT), AT, 0)
    sub = eng.wm.graph.subentities["inflation.services_cpi"]
    assert sub.prior == Gaussian(mu=4.0, sigma=0.3) and sub.scale == 0.3 and sub.anchor == 4.0
    inter = _int_between(eng, "inflation.services_cpi", "inflation.core_cpi")
    assert inter.forward.effect.mean() == 0.77 and inter.forward.kernel.means()[0] == 3.0


def test_path_update_increments_supports():
    eng = constructed_engine(build=True)
    tax = eng.ltm.object_generalizations.taxonomy
    before = {g: n.stats.support for g, n in tax.nodes.items()}
    warm_taxonomies(eng, rounds=1)
    assert tax.nodes["gen:obj:root"].stats.support == before["gen:obj:root"] + 48     # every entity
    assert tax.nodes["gen:obj:central_bank"].stats.support == 2
    assert tax.nodes["gen:obj:actor"].stats.support == 18    # agencies, people, and companies
    assert "policy_rate" in tax.nodes["gen:obj:central_bank"].stats.attribute_level


def _tiny_taxonomy() -> tuple[Taxonomy, AttributeVocabulary]:
    vocab = AttributeVocabulary(kinds={"x": AttributeKind(name="x", parent=None, family="gaussian")})
    nodes = {
        "r": Generalization(id="r", kind=TaxonomyKind.OBJECT, name="R", parent_id=None, child_ids=["a", "b"]),
        "a": Generalization(id="a", kind=TaxonomyKind.OBJECT, name="A", parent_id="r",
                            signature=Signature(required={"kind": ["agency"]}), stats=GeneralizationStats(support=2)),
        "b": Generalization(id="b", kind=TaxonomyKind.OBJECT, name="B", parent_id="r",
                            signature=Signature(required={"kind": ["agency"]}), stats=GeneralizationStats(support=5)),
    }
    return Taxonomy(kind=TaxonomyKind.OBJECT, root_id="r", nodes=nodes), vocab


def test_ties_go_to_support_then_id():
    tax, vocab = _tiny_taxonomy()

    class _L:
        attributes = vocab
        patterns = None

    path = descend(tax, {"kind": ["agency"]}, graph=None, ltm=_L())  # type: ignore[arg-type]
    assert path == ["r", "b"]
    tax.nodes["a"].stats.support = 5
    assert descend(tax, {"kind": ["agency"]}, graph=None, ltm=_L()) == ["r", "a"]  # type: ignore[arg-type]


def test_empty_signature_scores_zero():
    assert Signature().match({"kind": ["agency"]}, AttributeVocabulary(kinds={})) == 0.0


def test_grower_splits_on_a_shared_feature(m1_engine):
    eng = m1_engine
    # five firms under gen:obj:firm, four of them in the EU
    from axelrod_wm.core.entity import Entity

    with eng.mutator.begin("firms", at=AT) as txn:
        ids = []
        for k in range(5):
            eid = f"firm{k}"
            ids.append(eid)
            txn.add("entities", Entity(id=eid, name=f"Firm {k}", kind="company", category_tags={"SC"},
                                       features={"region": "EU" if k < 4 else "US"}, origin="human", created_at=AT,
                                       generalization_id="gen:obj:firm"))
        txn.update("generalizations.object", "gen:obj:firm", instance_ids=ids)
    ctx = eng.context(learn=True, now=AT)
    tax = eng.ltm.object_generalizations.taxonomy
    with eng.mutator.begin("grow", at=AT) as txn:
        created = SplitOnSharedFeatureGrower().maybe_split(tax, "gen:obj:firm", ctx, txn)
    assert len(created) == 1
    child = tax.nodes[created[0]]
    assert child.signature.required == {"region": ["EU"]}
    assert sorted(child.instance_ids) == ["firm0", "firm1", "firm2", "firm3"]
    assert tax.nodes["gen:obj:firm"].instance_ids == ["firm4"]
    assert eng.wm.graph.entities["firm0"].generalization_id == child.id
    with eng.mutator.begin("grow2", at=AT) as txn:   # three of a kind is not enough (recognition = 3)
        assert SplitOnSharedFeatureGrower().maybe_split(tax, child.id, ctx, txn) == []
