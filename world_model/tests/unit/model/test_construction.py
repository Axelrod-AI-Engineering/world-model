"""M1: the core model, construction, taxonomies, seeds, and super-interactions."""

from __future__ import annotations

import json

import pytest
import yaml

from axelrod_wm.engine.initialize import ConstructionError, ConstructionSpec, load_taxonomy
from axelrod_wm.memory.long_term import LongTermMemory
from axelrod_wm.memory.working import WorkingMemory
from axelrod_wm.model.distributions import DIST_ADAPTER
from axelrod_wm.model.entity import Entity, Subentity
from axelrod_wm.model.interaction import Interaction
from axelrod_wm.model.superentity import SuperentityPattern, SuperentityStatus
from axelrod_wm.model.taxonomy import TaxonomyKind
from tests.where import ECONOMY


def test_counts(m1_engine):
    g = m1_engine.wm.graph
    assert len(g.entities) == 53          # Figure 1's 33 (NVIDIA in Northwind's place) plus 20 real actors
    assert len(g.subentities) == 159     # 115 written out, 44 from the firms' kinds (world_model/taxonomy/objects.yaml)
    written = sorted(i for i in g.interactions if not i.startswith("d-"))
    assert written == sorted(f"e{i:02d}" for i in range(1, 103) if i not in (80, 81))   # e80, e81: the Airline kind's
    assert len(g.interactions) == 100 + 65
    assert not any(i.edge_type == "learned_causal" for i in g.interactions.values())


def test_seed_patterns_and_instances(m1_engine):
    pats = m1_engine.ltm.object_generalizations.patterns
    assert sorted(pats) == sorted([f"S{i}" for i in range(1, 21)] + ["HP1", "HP2"])
    assert all(p.status == SuperentityStatus.ADMITTED and p.origin == "seed" for p in pats.values())
    insts = {i.pattern_id for i in m1_engine.wm.graph.instances.values()}
    assert insts == {f"S{i}" for i in range(1, 21)}
    assert pats["S8"].rival_ids == {"S9"} and pats["S9"].rival_ids == {"S8"}
    assert [r.present for r in pats["S9"].relations] == [True, False]


def test_seeded_composite_nests_two_superentities_and_an_entity(m1_engine):
    g = m1_engine.wm.graph
    s10 = m1_engine.ltm.object_generalizations.patterns["S10"]
    assert s10.sub_pattern_ids == ["S2", "S1"]
    inst = g.instances["inst-S10"]
    assert inst.child_instance_ids == ["inst-S2", "inst-S1"]
    parts = g.members("inst-S2") | g.members("inst-S1")
    assert g.members("inst-S10") == parts | {"federal_reserve"}
    # no super-interaction joins a composite to its own parts
    for s in g.super_interactions.values():
        assert {s.source_instance_id, s.target_instance_id} not in ({"inst-S10", "inst-S2"}, {"inst-S10", "inst-S1"})


def test_loose_entities(m1_engine):
    g = m1_engine.wm.graph
    loose = {e for e in g.entities if not g.instances_of_entity(e)}
    assert loose == {"market_concentration", "geography", "ecb", "fed_chair"}


def _supers(engine):
    out = {}
    for s in engine.wm.graph.super_interactions.values():
        src = engine.wm.graph.instances[s.source_instance_id].pattern_id
        tgt = engine.wm.graph.instances[s.target_instance_id].pattern_id
        out[(src, tgt, str(s.kind))] = s
    return out


def test_super_interactions(m1_engine):
    sup = _supers(m1_engine)
    assert sup[("S2", "S1", "causal")].label == "raises costs"
    assert sup[("S2", "S1", "causal")].underlying_interaction_ids == ["e20"]
    assert sup[("S1", "S3", "causal")].label == "sparks crises"
    assert sup[("S3", "S4", "causal")].label == "cuts trade finance"
    assert sup[("S2", "S4", "shares_members")].shared_entity_ids == ["supply_chains", "wars"]
    assert sup[("S2", "S5", "causal")].underlying_interaction_ids == ["e22"]
    assert sup[("S7", "S4", "causal")].underlying_interaction_ids == ["e23"]
    assert ("S4", "S8", "causal") in sup and ("S4", "S9", "causal") in sup
    assert sup[("S8", "S9", "shares_members")].shared_entity_ids == ["federal_reserve", "inflation", "interest_rates"]


def test_every_nonleaf_has_two_children(m1_engine):
    for tax in (m1_engine.ltm.object_generalizations.taxonomy, m1_engine.ltm.interaction_generalizations.taxonomy):
        for node in tax.nodes.values():
            assert len(node.child_ids) == 0 or len(node.child_ids) >= 2, node.id


def test_taxonomy_homes(m1_engine):
    g = m1_engine.wm.graph
    assert g.entities["federal_reserve"].generalization_id == "gen:obj:central_bank"
    assert g.interactions["e01"].generalization_id == "gen:int:policy_rate_to_bank_funding"
    assert m1_engine.ltm.object_generalizations.patterns["HP1"].generalization_id == "gen:obj:bank_run"


def test_entity_links_use_figure1_labels(m1_engine):
    links = {(l.source_entity_id, l.target_entity_id): l for l in m1_engine.wm.graph.entity_links()}
    assert links[("interest_rates", "credit_availability")].label == "limits"
    assert links[("resources_energy", "inflation")].interaction_ids == ["e08"]


def test_bidirectional_and_parameter(m1_engine):
    e45 = m1_engine.wm.graph.interactions["e45"]
    assert len(e45.channels()) == 2
    e13 = m1_engine.wm.graph.interactions["e13"]
    assert e13.parameters[0].moderator_id == "debt_cycle.household_debt"
    assert e13.evidence and e13.evidence[0].excerpt.startswith("Designer prior")


def _spec_dict():
    ent = yaml.safe_load(open(ECONOMY / "entities.yaml"))
    inter = yaml.safe_load(open(ECONOMY / "interactions.yaml"))
    return {"decision_variables": ent["decision_variables"], "entities": ent["entities"],
            "interactions": inter["interactions"], "entity_link_labels": inter["entity_link_labels"]}


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["interactions"].append(dict(d["interactions"][0], id="e999")), "duplicates source, target, and label"),
    (lambda d: d["interactions"][0].update(target="nowhere.x"), "not a known subentity"),
    (lambda d: d["interactions"][0].update(label=" "), "has no label"),
    (lambda d: d["entities"][0]["subentities"][0].update(id="wrong.prefix"), "must start with"),
    (lambda d: d["interactions"][1].update(id="e01"), "duplicate interaction id"),
])
def test_invalid_specs_raise_clear_errors(mutate, message):
    d = _spec_dict()
    mutate(d)
    spec = ConstructionSpec.model_validate(d)
    with pytest.raises(ConstructionError, match=message):
        spec.validate_spec()


def test_taxonomy_unknown_parent(tmp_path):
    p = tmp_path / "objects.yaml"
    p.write_text("root: r\nnodes:\n  - {id: r, name: R, parent: null}\n  - {id: a, name: A, parent: missing}\n")
    with pytest.raises(ConstructionError, match="unknown parent"):
        load_taxonomy(p, TaxonomyKind.OBJECT)


def test_serialization_round_trips(m1_engine):
    g = m1_engine.wm.graph
    for cls, coll in ((Entity, g.entities), (Subentity, g.subentities), (Interaction, g.interactions)):
        for obj in coll.values():
            again = cls.model_validate_json(obj.model_dump_json())
            assert again == obj
    for p in m1_engine.ltm.object_generalizations.patterns.values():
        assert SuperentityPattern.model_validate_json(p.model_dump_json()) == p
    for d in ({"family": "gaussian", "mu": 1, "sigma": 2}, {"family": "beta", "alpha": 2, "beta": 3},
              {"family": "lognormal", "mu": 0.1, "sigma": 0.2}, {"family": "gamma", "k": 2, "theta": 3}):
        dist = DIST_ADAPTER.validate_python(d)
        assert DIST_ADAPTER.validate_json(json.dumps(DIST_ADAPTER.dump_python(dist, mode="json"))) == dist
    wm2 = WorkingMemory.model_validate_json(m1_engine.wm.model_dump_json())
    ltm2 = LongTermMemory.model_validate_json(m1_engine.ltm.model_dump_json())
    assert wm2.model_dump() == m1_engine.wm.model_dump()
    assert ltm2.model_dump() == m1_engine.ltm.model_dump()
