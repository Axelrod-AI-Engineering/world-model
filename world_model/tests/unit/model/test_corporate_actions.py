"""Corporate actions (model/corporate_actions.py): declaring a split, loading it, and the import rule that converts a
per-share value reported after the split to the model's pre-split basis (intake/bundle.py)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
import yaml
from pydantic import ValidationError

from axelrod_ingest.contract.bundle import ImportItem, Link, Move, Observe
from axelrod_wm.engine.initialize import ConstructionError, ConstructionSpec, load_vocabulary
from axelrod_wm.intake.structured import market_event_of, signal_conversion, signal_ops, translate_item
from axelrod_wm.model.corporate_actions import CorporateAction, is_per_share, splits_in_force, to_model_basis
from tests.unit.engine.test_cov_initialize import _taxonomy
from tests.unit.model.test_business_construction import ATTRS, _s, acme_construction, build, world

SPLIT = {"type": "split", "ratio": 15, "effective": "2024-04-01"}
AFTER = datetime(2024, 4, 2, tzinfo=UTC)
BEFORE = datetime(2024, 3, 29, tzinfo=UTC)


def split_world(tmp_path, *, in_entities=False, actions=None):
    c = acme_construction()
    c["subentities"].append({"entity": "acme", **_s("acme.share_price", unit="¥", mean=6000.0, scale=300.0,
                                                    features={"per_share": "true"})})
    c["subentities"].append({"entity": "acme", **_s("acme.dps", unit="¥ per share", mean=100.0, scale=10.0)})
    acts = actions if actions is not None else [SPLIT]
    if in_entities:
        d = world(tmp_path, c)
        ent = yaml.safe_load((d / "entities.yaml").read_text())
        ent["entities"][1]["corporate_actions"] = acts
        (d / "entities.yaml").write_text(yaml.safe_dump(ent))
        return d
    c["corporate_actions"] = [{"entity": "acme", **a} for a in acts]
    return world(tmp_path, c)


@pytest.fixture
def graph(tmp_path):
    return build(split_world(tmp_path), tmp_path)


# -- the declaration ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [{**SPLIT, "ratio": 1}, {**SPLIT, "ratio": 0}, {**SPLIT, "type": "merger"},
                                 {**SPLIT, "surprise": 1}])
def test_a_split_must_change_something(bad):
    with pytest.raises(ValidationError):
        CorporateAction.model_validate(bad)


def test_what_counts_as_per_share():
    v = SimpleNamespace
    assert is_per_share(v(features={"per_share": "True"}, unit="¥"))
    assert is_per_share(v(features={}, unit="¥ per  share")) and is_per_share(v(features=None, unit="$/share"))
    assert not is_per_share(v(features={"per_share": "false"}, unit="$/bbl")) and not is_per_share(1)
    a, b = (CorporateAction.model_validate({**SPLIT, "effective": d}) for d in ("2024-06-01", "2024-04-01"))
    assert splits_in_force([a, b], date(2024, 7, 1)) == [b, a] and splits_in_force([a, b], date(2024, 3, 1)) == []


def test_a_split_loads_from_a_construction_file_or_entities_yaml(tmp_path, graph):
    assert graph.entities["acme"].corporate_actions == [CorporateAction.model_validate(SPLIT)]
    assert graph.entities["macro"].corporate_actions == []
    tax = _taxonomy(tmp_path, attrs=ATTRS)
    spec = ConstructionSpec.load(split_world(tmp_path / "e", in_entities=True), tax)
    assert next(e for e in spec.entities if e.id == "acme").corporate_actions[0].ratio == 15


@pytest.mark.parametrize("change, msg", [
    ("unknown", "corporate action names unknown entity 'ghost'"),
    ("twice", "two corporate actions on the same day"),
    ("no_per_share", "a split changes no value"),
])
def test_a_bad_split_refuses_to_load(tmp_path, change, msg):
    tax = _taxonomy(tmp_path, attrs=ATTRS)
    if change == "unknown":
        c = acme_construction()
        c["corporate_actions"] = [{"entity": "ghost", **SPLIT}]
        d = world(tmp_path, c)
    elif change == "twice":
        d = split_world(tmp_path, actions=[SPLIT, {**SPLIT, "ratio": 2}])
    else:
        c = acme_construction()
        c["corporate_actions"] = [{"entity": "acme", **SPLIT}]
        d = world(tmp_path, c)
    with pytest.raises(ConstructionError, match=msg):
        ConstructionSpec.load(d, tax).validate_spec(load_vocabulary(tax))


def test_a_kind_default_can_mark_its_value_per_share(tmp_path):
    objects = {"root": "gen:obj:root", "nodes": [
        {"id": "gen:obj:root", "name": "Object", "parent": None},
        {"id": "gen:obj:firm", "name": "Firm", "parent": "gen:obj:root", "instances": ["acme"],
         "defaults": [{"slot": "share_price", "name": "share price", "attribute_kind": "flow", "unit": "local ccy",
                       "mean": 100.0, "scale": 8.0, "features": {"per_share": "true"}}]}]}
    tax = _taxonomy(tmp_path, attrs=ATTRS, objects=objects)
    c = acme_construction()
    c["corporate_actions"] = [{"entity": "acme", **SPLIT}]
    spec = ConstructionSpec.load(world(tmp_path, c), tax)
    spec.validate_spec(load_vocabulary(tax))
    sp = next(s for e in spec.entities for s in e.subentities if s.id == "acme.share_price")
    assert sp.features == {"per_share": "true"}


# -- the import rule ---------------------------------------------------------------------------------------------------
def test_a_post_split_price_converts_to_the_pre_split_basis(graph):
    assert to_model_basis(graph, "acme.profit", 5.0, AFTER.date()) == (5.0, None)        # not per share
    assert to_model_basis(graph, "acme.share_price", 400.0, BEFORE.date()) == (400.0, None)   # before the split
    value, conv = to_model_basis(graph, "acme.share_price", 400.0, AFTER.date())
    assert value == 6000.0 and conv == {"value_of": "acme.share_price", "reported": 400.0, "model_basis": 6000.0,
                                        "factor": 15.0, "dated": "2024-04-02",
                                        "splits": [{"ratio": 15.0, "effective": "2024-04-01"}]}
    ops, why = signal_ops(Observe(type="observe", value_of="acme.share_price", value=400.0), graph, AFTER)
    assert why is None and ops[0]["value"] == 6000.0
    assert signal_ops(Observe(type="observe", value_of="acme.share_price", value=6100.0), graph, BEFORE)[0][0][
        "value"] == 6100.0
    absolute = Move(type="move", value_of="acme.dps", delta=2.0, mode="absolute")
    assert signal_ops(absolute, graph, AFTER)[0][0]["delta"] == 30.0
    relative = Move(type="move", value_of="acme.share_price", delta=-0.05, mode="relative")
    assert signal_ops(relative, graph, AFTER)[0][0]["delta"] == -0.05 and signal_conversion(relative, graph, AFTER) is None
    assert signal_conversion(Link(type="link", source="acme.auto", target="acme.profit", label="l", effect=1.0),
                             graph, AFTER) is None
    assert signal_conversion(Observe(type="observe", value_of="acme.none", value=1.0), graph, AFTER) is None


def test_the_review_says_what_converted(graph):
    item = ImportItem(id="S1", published_at=AFTER, source="Exchange", headline="Acme closes at 400",
                      signals=[Observe(type="observe", value_of="acme.share_price", value=400.0),
                               Observe(type="observe", value_of="acme.profit", value=11.0)])
    res, dropped = translate_item(item, market_event_of(item, "IM-S1"), graph)
    assert dropped == [] and [op.value for op in res.events[0].ops] == [6000.0, 11.0]
    assert res.rationale == ("Exchange (news) Converted for a split: acme.share_price 400 is 6000 on the pre-split "
                             "basis (x15; 15-for-1 on 2024-04-01).")
