"""Fixtures for the service's end-to-end flows on v1 (tests/README.md, Integration tests): a whole app (REST, MCP,
lakehouse, engine, snapshots) on directories of the test's own, with synthetic notes only. Callers use a static key
(read and propose); a person reviews with a service token signed by the tests' own ephemeral key (tests/service/
helpers.py), so nothing calls core."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.service.helpers import WM, Signer, data

# synthetic, dated notes: each names attributes the sally_demo model holds (no real event is reported)
RATES_NOTE = b"Data, September 1, 2026. The Fed held rates at 3.875%. Brent crude rose to $103 a barrel."
ECB_NOTE = b"Rates wire, September 3, 2026. The ECB cut its deposit rate by 25bp."
BOJ_NOTE = b"Rates wire, September 4, 2026. The BoJ raised its policy rate by 25bp to 1.25%."
SIGNER = Signer()


def upload(c: TestClient, payload: bytes, name: str, wm: str = WM, headers: dict | None = None, **form: str) -> dict:
    """Upload one file (a job); the job's result for it: document_id, new, status, bundle_id, chunks."""
    job = data(c.post(f"{wm}/documents", files=[("files", (name, payload, "text/plain"))], data=form,
                      headers=headers or {}), 202)
    assert job["status"] == "succeeded", job
    return job["result"]["detail"]["results"][0]


def propose(c: TestClient, bundle_id: str, wm: str = WM, headers: dict | None = None) -> dict:
    """Propose a bundle's changes (a job); the finished job: result.ids are the changes, result.detail the import."""
    job = data(c.post(f"{wm}/changes", json={"bundle_id": bundle_id}, headers=headers or {}), 202)
    assert job["status"] == "succeeded", job
    return job


def review_all(c: TestClient, wm: str = WM, headers: dict | None = None, approve: bool = True, note: str = "checked",
               **claims: Any) -> list[dict]:
    """Decide what waits for review, round after round, as a person in a review UI (a core-web token with
    changes:approve, If-Match on the version reviewed); each decision."""
    out = []
    while pending := data(c.get(f"{wm}/changes", headers=headers or {})):
        for ch in pending:
            tag = c.get(wm, headers=headers or {}).headers["etag"]
            r = c.post(f"{wm}/changes/{ch['id']}/{'approvals' if approve else 'rejections'}",
                       json={"note": note} if approve else {"reason": note},
                       headers={**SIGNER.bearer(**claims), "If-Match": tag})
            out.append(data(r, 201))
    return out


def version(c: TestClient, wm: str = WM, headers: dict | None = None) -> dict:
    """The version a world model is at: number, state_hash, committed_at, latest, clock."""
    return c.get(wm, headers=headers or {}).json()["meta"]["version"]


def attribute(c: TestClient, entity: str, key: str, wm: str = WM, headers: dict | None = None, **pin: Any) -> dict:
    """An attribute read (pinned with version or as_of): {"data": the attribute, "meta": its version}."""
    r = c.get(f"{wm}/entities/{entity}/attributes/{key}", params=pin, headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()
