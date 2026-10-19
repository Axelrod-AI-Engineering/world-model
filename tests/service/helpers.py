"""What the v1 service's tests share: paths, synthetic notes, credentials (a static key, and service tokens signed with
an ephemeral key whose JWKS is served by an httpx.MockTransport, so nothing calls core), problem checks, and the
upload -> propose -> decide steps."""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from axelrod_wm.api import tokens
from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import FilesBackend, MemoryBackend

ROOT = Path(__file__).resolve().parents[2]
V1 = "/v1"
WM = "/v1/world-models/sally_demo"
KEY = "k" * 32
ALL_BUT_APPROVE = "world_model:read+documents:create+changes:create+simulations:create+admin"
ISSUER, AUDIENCE, JWKS_URL = "https://core.test", "https://world-model.test", "https://core.test/.well-known/jwks.json"
# synthetic research notes (made up for the tests; no real event is reported)
NOTE = (b"Rates note, October 5, 2026.\n\n"
        b"The BoJ raised its policy rate by 25bp to 1.25% on a 7-2 vote. USD/JPY fell to 152 as the yen strengthened.\n\n"
        b"JPMorgan's net interest income rose 4% y/y. Lower Bund yields weigh on UniCredit's net interest income.")
FED_NOTE = b"Data, September 1, 2026. The Fed held rates at 3.875%. Brent crude rose to $103 a barrel."
ECB_NOTE = b"Rates wire, September 3, 2026. The ECB cut its deposit rate by 25bp."
BOJ_NOTE = b"Rates wire, September 4, 2026. The BoJ raised its policy rate by 25bp to 1.25%."


class Signer:
    """Core's side of a service token, for tests: an ephemeral ES256 key, its JWKS, and tokens with any claims."""

    def __init__(self, kid: str = "test-key-1") -> None:
        self.kid = kid
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.served = True
        self.fetches = 0

    def jwks(self) -> dict:
        return tokens.jwks_of((self.kid, self.key.public_key()))

    def transport(self) -> httpx.MockTransport:
        def answer(request: httpx.Request) -> httpx.Response:
            self.fetches += 1
            if not self.served:
                raise httpx.ConnectError("issuer down", request=request)
            return httpx.Response(200, json=self.jwks())

        return httpx.MockTransport(answer)

    def token(self, *, sub: str = "org_user_9", org: str = "default", scope: str = "world_model:read changes:approve",
              azp: str | None = "core-web", act: dict | None = None, name: str | None = "Sally Reviewer",
              ttl: int = 300, headers: dict | None = None, key: Any = None, **claims: Any) -> str:
        now = int(time.time())
        body = {"iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + ttl, "jti": uuid.uuid4().hex, "sub": sub,
                "org": org, "scope": scope, **({"azp": azp} if azp else {}), **({"name": name} if name else {}),
                **({"act": act} if act is not None else {}), **claims}
        return jwt.encode(body, key or self.key, algorithm="ES256",
                          headers={"kid": self.kid, "typ": "at+jwt", **(headers or {})})

    def bearer(self, **kw: Any) -> dict:
        return {"Authorization": f"Bearer {self.token(**kw)}"}


def env(keys: str = f"tester:{KEY}:default:{ALL_BUT_APPROVE}", **extra: str) -> dict[str, str]:
    return {"WORLD_MODEL_API_KEYS": keys, "WORLD_MODEL_TRUSTED_ISSUERS": f"{ISSUER};{JWKS_URL};{AUDIENCE}", **extra}


@contextmanager
def service(signer: Signer | None = None, root: Path | None = None, scenario: str = "sally_demo",
            headers: dict | None = None, **settings: str) -> Iterator[TestClient]:
    """The service on its own engine and lakehouse, with keys and a trusted issuer (`settings` adds to or replaces the
    environment; pass WORLD_MODEL_API_KEYS="" and WORLD_MODEL_TRUSTED_ISSUERS="" for an open local run)."""
    mp = pytest.MonkeyPatch()
    for k, v in {**env(), **settings}.items():
        mp.setenv(k, v)
    if signer is not None:
        mp.setattr(tokens, "transport", signer.transport())
    storage = FilesBackend(path=root / "snapshots") if root is not None else MemoryBackend()
    app = create_app(scenario=scenario, storage=storage, trace_dir=None, play_delay=0.0,
                     lake_dir=root / "lake" if root is not None else None)
    try:
        with TestClient(app, headers={"Authorization": f"Bearer {KEY}", **(headers or {})}) as c:
            yield c
    finally:
        mp.undo()


def problem(r: Any, status: int, code: str) -> dict:
    """The answer is an RFC 9457 problem with this status and code, and the standard headers."""
    assert r.status_code == status, r.text
    assert r.headers["content-type"].startswith("application/problem+json"), r.headers["content-type"]
    assert r.headers["x-axelrod-api-version"] == "1" and r.headers["x-request-id"]
    body = r.json()
    assert body["code"] == code and body["status"] == status, body
    assert body["type"] == f"https://docs.axelrod.ai/problems/{code}" and body["title"] and body["detail"]
    assert body["instance"] == r.request.url.path and body["request_id"] == r.headers["x-request-id"]
    return body


def data(r: Any, status: int = 200) -> Any:
    assert r.status_code == status, r.text
    return r.json()["data"]


def attributes(graph: dict) -> list[dict]:
    """Every attribute nested in an answer's entities."""
    return [a for e in graph["entities"] for a in e["attributes"]]


def upload(c: TestClient, payload: bytes, name: str = "note.txt", headers: dict | None = None, **form: str) -> dict:
    """Upload one file; the job's result for it (document_id, new, bundle_id, chunks, ...)."""
    job = data(c.post(f"{WM}/documents", files=[("files", (name, payload, "text/plain"))], data=form,
                      headers=headers or {}), 202)
    assert job["status"] == "succeeded", job
    return job["result"]["detail"]["results"][0]


def propose(c: TestClient, bundle_id: str, headers: dict | None = None, **body: Any) -> dict:
    """Propose a bundle's changes; the finished job."""
    job = data(c.post(f"{WM}/changes", json={"bundle_id": bundle_id, **body}, headers=headers or {}), 202)
    assert job["status"] == "succeeded", job
    return job


def etag_now(c: TestClient, headers: dict | None = None) -> str:
    return c.get(WM, headers=headers or {}).headers["etag"]


def decide_all(c: TestClient, reviewer: Signer, approve: bool = True, note: str = "checked", **claims: Any) -> list[dict]:
    """Decide every pending change as a person (a core-web token with changes:approve), round after round."""
    out = []
    while pending := data(c.get(f"{WM}/changes")):
        for ch in pending:
            h = {**reviewer.bearer(**claims), "If-Match": etag_now(c)}
            r = c.post(f"{WM}/changes/{ch['id']}/{'approvals' if approve else 'rejections'}",
                       json={"note": note} if approve else {"reason": note}, headers=h)
            out.append(data(r, 201))
    return out
