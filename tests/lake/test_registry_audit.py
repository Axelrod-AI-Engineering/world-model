"""The lakehouse's world model registry and audit log (Oct 18; docs/design/core-mcp-auth.md): each world model is
upserted with its owning organization and survives a reopen; the audit log is append-only, read per organization and
world model, newest first, with the structured actor intact."""

from __future__ import annotations

from datetime import timedelta

from axelrod_wm.lake.sqlite import SQLiteLake
from axelrod_wm.lake.store import AuditRecord, WorldModelRecord
from tests.lake.conftest import T0

DAY = timedelta(days=1)


def test_the_registry_upserts_each_world_model_with_its_owner(lake, tmp_path):
    a = lake.register_world_model(WorldModelRecord(id="sally_demo", org_id="default", name="sally_demo", created_at=T0))
    assert a.org_id == "default" and a.created_at == T0
    moved = lake.register_world_model(WorldModelRecord(id="sally_demo", org_id="tokio", name="Sally",
                                                       created_at=T0 + DAY))
    assert moved.org_id == "tokio" and moved.name == "Sally" and moved.created_at == T0      # first registration kept
    lake.register_world_model(WorldModelRecord(id="small_demo", org_id="acme", name="small_demo", created_at=T0))
    assert [r.id for r in lake.world_models()] == ["sally_demo", "small_demo"]
    assert [r.id for r in lake.world_models(org_id="acme")] == ["small_demo"] and lake.world_models("none") == []
    lake.close()
    again = SQLiteLake(tmp_path / "lk")
    assert [(r.id, r.org_id) for r in again.world_models()] == [("sally_demo", "tokio"), ("small_demo", "acme")]
    again.close()


def rec(id_, at, org="acme", wm="sally_demo"):
    return AuditRecord(org=org, id=id_, at=at, request_id=f"req_{id_}", world_model_id=wm, method="POST",
                       route="/v1/world-models/{world_model_id}/changes", status=202,
                       actor={"kind": "token", "sub": "u1", "act": {"sub": "mcp-client:x"}, "jti": "j"},
                       scopes=["read", "changes:write"], resource_ids=["job_1", "PR-1"])


def test_the_audit_log_is_per_organization_and_world_model_newest_first(lake):
    for r in (rec("a1", T0), rec("a2", T0 + DAY), rec("a0", T0 + DAY), rec("b1", T0, org="beta"),
              rec("c1", T0, wm="small_demo")):
        lake.put_audit(r)
    rows = lake.list_audit("acme", "sally_demo")
    assert [r.id for r in rows] == ["a2", "a0", "a1"]
    assert rows[0].actor["act"] == {"sub": "mcp-client:x"} and rows[0].resource_ids == ["job_1", "PR-1"]
    assert rows[0] == rec("a2", T0 + DAY)
    assert [r.id for r in lake.list_audit("beta", "sally_demo")] == ["b1"] and lake.list_audit("beta", "x") == []
