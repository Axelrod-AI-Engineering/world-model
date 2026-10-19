"""The lakehouse's world model registry, audit log, idempotency keys and jobs (Oct 18; docs/design/core-mcp-auth.md): each world model is
upserted with its owning organization and survives a reopen; the audit log is append-only, read per organization and
world model, newest first, with the structured actor intact."""

from __future__ import annotations

from datetime import timedelta

from axelrod_wm.lake.sqlite import SQLiteLake
from axelrod_wm.lake.store import AuditRecord, IdempotencyRecord, WorldModelRecord
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
                       scopes=["world_model:read", "changes:create"], resource_ids=["job_1", "PR-1"])


def test_the_audit_log_is_per_organization_and_world_model_newest_first(lake):
    for r in (rec("a1", T0), rec("a2", T0 + DAY), rec("a0", T0 + DAY), rec("b1", T0, org="beta"),
              rec("c1", T0, wm="small_demo")):
        lake.put_audit(r)
    rows = lake.list_audit("acme", "sally_demo")
    assert [r.id for r in rows] == ["a2", "a0", "a1"]
    assert rows[0].actor["act"] == {"sub": "mcp-client:x"} and rows[0].resource_ids == ["job_1", "PR-1"]
    assert rows[0] == rec("a2", T0 + DAY)
    assert [r.id for r in lake.list_audit("beta", "sally_demo")] == ["b1"] and lake.list_audit("beta", "x") == []


def key(k, body='{"data": {"id": "job_1", "result": {"ids": ["doc_abc"]}}}', fp="fp1"):
    return IdempotencyRecord(org="acme", world_model_id="sally_demo", operation="/v1/world-models/{world_model_id}/documents",
                             key=k, fingerprint=fp, status=202, body=body, headers={"location": "/v1/x/jobs/job_1"},
                             created_at=T0)


def test_idempotency_keys_are_kept_forever_first_answer_wins(lake, tmp_path):
    op = "/v1/world-models/{world_model_id}/documents"
    assert lake.get_idempotency("acme", "sally_demo", op, "k1") is None
    lake.put_idempotency(key("k1"))
    lake.put_idempotency(key("k1", body="{}", fp="other"))                  # a later answer under the key is ignored
    got = lake.get_idempotency("acme", "sally_demo", op, "k1")
    assert got == key("k1")
    assert lake.get_idempotency("beta", "sally_demo", op, "k1") is None
    assert lake.get_idempotency("acme", "sally_demo", "/v1/other", "k1") is None
    lake.put_idempotency(key("content:abc", body='{"data": {"doc": "doc_other"}}'))
    assert lake.forget_idempotency("acme", "sally_demo", "doc_abc") == 1    # only the answers that name it
    assert lake.get_idempotency("acme", "sally_demo", op, "k1") is None
    assert lake.get_idempotency("acme", "sally_demo", op, "content:abc") is not None
    lake.close()
    again = SQLiteLake(tmp_path / "lk")
    assert again.get_idempotency("acme", "sally_demo", op, "content:abc").fingerprint == "fp1"
    again.close()


def test_jobs_are_kept_and_replaced_by_id(lake):
    assert lake.get_job("acme", "sally_demo", "job_1") is None
    lake.put_job("acme", "sally_demo", {"id": "job_1", "status": "running"})
    lake.put_job("acme", "sally_demo", {"id": "job_1", "status": "succeeded", "result": {"ids": ["d"]}})
    assert lake.get_job("acme", "sally_demo", "job_1") == {"id": "job_1", "status": "succeeded", "result": {"ids": ["d"]}}
    assert lake.get_job("beta", "sally_demo", "job_1") is None
