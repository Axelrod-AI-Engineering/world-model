"""The v1 layer's small pieces on their own (api/v1/problems.py, project.py, routes_ingest.py): how each kind of failure
becomes a problem, and the projections' edge cases that a scenario does not reach (a level without quantiles, a path
whose relationship is gone, a change the engine decided, a world without question templates)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from axelrod_wm.api.v1 import project
from axelrod_wm.api.v1.context import inverted_surfaces
from axelrod_wm.api.v1.problems import ApiError, as_api_error
from axelrod_wm.control.controller import ControllerError
from axelrod_wm.inference.task import UnboundThesis
from axelrod_wm.repo.snapshots import RestoreError


class Body(BaseModel):
    n: int


def invalid() -> ValidationError:
    with pytest.raises(ValidationError) as err:
        Body(n="x")
    return err.value


@pytest.mark.parametrize("exc, code", [
    (ApiError("chunk_not_found", "x"), "chunk_not_found"),
    (HTTPException(404, "gone"), "not_found"),
    (HTTPException(418, "teapot"), "invalid_request"),
    (UnboundThesis([]), "thesis_unbound"),
    (ControllerError("busy"), "conflict"),
    (RestoreError("no such version"), "version_not_found"),
    (KeyError("toyota"), "not_found"),
    (KeyError(), "not_found"),
    (ValueError("bad"), "invalid_request"),
])
def test_each_failure_becomes_its_problem(exc, code):
    assert as_api_error(exc).code == code


def test_a_validation_error_names_its_fields():
    err = as_api_error(invalid())
    assert err.code == "invalid_request" and err.errors[0]["location"] == ["n"]


def test_a_bug_is_not_a_problem():
    assert as_api_error(RuntimeError("bug")) is None


def test_a_level_without_quantiles():
    d = SimpleNamespace(mean=lambda: 1.5, sd=lambda: 0.5)
    lv = project.level(SimpleNamespace(posterior=d))
    assert lv.mean == 1.5 and lv.sd == 0.5 and lv.q05 is None and lv.q95 is None


def test_a_path_step_whose_relationship_is_gone_is_left_out():
    p = SimpleNamespace(id="P1", entity_id="toyota", name="n", trigger="toyota.a", endpoint="toyota.b",
                        description="", active_when="always", steps=[SimpleNamespace(interaction_id="gone", branch=None)])
    out = project.path(SimpleNamespace(interactions={}), p)
    assert out.steps == [] and out.uncalibrated_steps == 0 and out.steps_without_transition == 0


def test_a_change_the_engine_decided_names_the_system():
    p = SimpleNamespace(id="PR-1", kind="graph_update", status="approved", market_event_id="ME-1",
                        created_at=datetime(2026, 10, 1, tzinfo=UTC), decided_by="review_policy",
                        decided_at=datetime(2026, 10, 2, tzinfo=UTC), note=None, version_after=3, event=None,
                        review_reasons=["translated from text"])
    ch = project.change(p, "acme", None, None)
    assert ch.decided_by.model_dump(exclude_none=True) == {"kind": "system", "org": "acme", "sub": "review_policy"}
    assert ch.operation_count == 0 and ch.review_reasons == ["translated from text"]


def test_a_world_without_question_templates(tmp_path):
    assert inverted_surfaces(SimpleNamespace(controller=SimpleNamespace(world_dir=lambda: None))) == []
    assert inverted_surfaces(SimpleNamespace(controller=SimpleNamespace(world_dir=lambda: tmp_path))) == []
    (tmp_path / "templates.yaml").write_text("subjects:\n- {pattern: the euro, invert: true}\n- {pattern: oil}\n")
    assert inverted_surfaces(SimpleNamespace(controller=SimpleNamespace(world_dir=lambda: tmp_path))) == ["the euro"]
