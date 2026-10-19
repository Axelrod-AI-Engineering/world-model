"""What every v1 route needs: the principal and its scopes, the world model registry (an organization's models; any
other answers 404), the state a read is pinned to, cursors, envelopes, idempotency, the audit log, and jobs."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from axelrod_wm.api.app import AppState
from axelrod_wm.api.tokens import Principal
from axelrod_wm.api.v1.problems import ApiError, as_api_error, problem_body
from axelrod_wm.lake.store import AuditRecord, LakeStore, WorldModelRecord

IDEMPOTENCY_TTL_S = 86400


@dataclass
class Model:
    """A registry entry: one world model, its owning organization, and the engine that serves it."""

    id: str
    org: str
    st: AppState


# -- the registry -----------------------------------------------------------------------------------------------------
def build_registry(app: Any) -> dict[str, Model]:
    """One world model per engine: the main engine's scenario, and each login's. An id two engines would share is
    prefixed by the login. Each is recorded in the lakehouse's registry with its owner."""
    from axelrod_wm.api.auth import org_of

    engines = [(None, app.state.axelrod), *app.state.axelrod_by_login.items()]
    taken = [st.first_scenario for _l, st in engines]
    out: dict[str, Model] = {}
    for login, st in engines:
        wid = st.first_scenario if taken.count(st.first_scenario) == 1 or login is None else f"{login}-{st.first_scenario}"
        rec = lake(app).register_world_model(WorldModelRecord(id=wid, org_id=org_of(login), name=st.first_scenario,
                                                              created_at=datetime.now(UTC)))
        out[wid] = Model(id=wid, org=rec.org_id, st=st)
    return out


def lake(app: Any) -> LakeStore:
    return app.state.lake


def principal(request: Request) -> Principal:
    """The verified principal the front door (api/auth.py) put on every /v1 request; nothing reaches v1 without one."""
    return request.scope["axelrod_principal"]


def require(request: Request, scope: str) -> Principal:
    p = principal(request)
    if scope not in p.scopes:
        raise ApiError("insufficient_scope", f"this needs the {scope} scope",
                       headers={"WWW-Authenticate": f'Bearer error="insufficient_scope", scope="{scope}"'})
    return p


def models_of(request: Request, org: str) -> list[Model]:
    return [m for _i, m in sorted(request.app.state.world_models.items()) if m.org == org]


def model(request: Request, world_model_id: str, scope: str) -> Model:
    """The world model in the path, if it belongs to the credential's organization (else 404), and the scope."""
    p = principal(request)
    m = request.app.state.world_models.get(world_model_id)
    if m is None or m.org != p.org:
        raise ApiError("world_model_not_found", f"no world model {world_model_id}")
    require(request, scope)
    return m


# -- the state a read is of -------------------------------------------------------------------------------------------
def version_ref(st: AppState, v: int | None = None) -> dict:
    eng = st.controller.engine
    n = eng.version if v is None else v
    info = eng.snapshots.version_info(n) if n > 0 else None
    return {"number": n, "state_hash": info.state_hash if info else eng.state_hash,
            "committed_at": (info.recorded_at if info else eng.wm.clock).isoformat(), "latest": eng.version,
            "clock": eng.wm.clock.isoformat()}


def pinned(st: AppState, version: int | None, as_of: datetime | None) -> tuple[Any, Any, int]:
    """(working memory, long-term memory, version): the current state, or a past one by version or date."""
    eng = st.controller.engine
    if as_of is not None:
        # the last whole processed day at or before the date (a day's close); a model with no closed day yet (a
        # seeded one, before its first change) answers with its latest version at or before the date
        t = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
        known = [v for v in eng.snapshots.storage.versions() if v.recorded_at <= t]
        closes = [v.version for v in known if v.cause.startswith(("close:", "consolidation:"))]
        best = max(closes) if closes else max((v.version for v in known), default=0)
        if best == 0:
            raise ApiError("version_not_found", f"the world model has no state at or before {t.isoformat()}")
        wm, ltm = eng.snapshots.restore(best)
        return wm, ltm, best
    if version is None or version == eng.version:
        return eng.wm, eng.ltm, eng.version
    if not 0 < version < eng.version:
        raise ApiError("version_not_found", f"version {version} is not in this world model (latest {eng.version})")
    wm, ltm = eng.snapshots.restore(version)
    return wm, ltm, version


def etag(ref: dict) -> str:
    return f'"{ref["state_hash"]}"'


# -- cursors and envelopes --------------------------------------------------------------------------------------------
def decode_cursor(cursor: str | None) -> tuple[int, int | None]:
    """(offset, version) of a cursor this service issued; (0, None) for the first page."""
    if not cursor:
        return 0, None
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor.encode() + b"=" * (-len(cursor) % 4)))
        off, ver = int(raw["o"]), raw.get("v")
        if off < 0 or (ver is not None and int(ver) < 1):
            raise ValueError(cursor)
        return off, None if ver is None else int(ver)
    except (ValueError, KeyError, TypeError) as err:
        raise ApiError("invalid_cursor", "this cursor was not issued by this service") from err


def encode_cursor(offset: int, version: int | None) -> str:
    raw = json.dumps({"o": offset, "v": version}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def page(items: list, offset: int, limit: int, version: int | None) -> tuple[list, str | None]:
    chunk = items[offset:offset + limit]
    return chunk, encode_cursor(offset + limit, version) if offset + limit < len(items) else None


def jsonable(x: Any) -> Any:
    if isinstance(x, BaseModel):
        return x.model_dump(mode="json")
    if isinstance(x, list):
        return [jsonable(v) for v in x]
    return x


def one(request: Request, data: Any, ref: dict | None = None, *, status: int = 200, tag: bool = False,
        location: str | None = None) -> JSONResponse:
    meta: dict = {"request_id": request.state.request_id}
    if ref is not None:
        meta["version"] = ref
    headers = {}
    if tag and ref is not None:
        headers["ETag"] = etag(ref)
    if location:
        headers["Location"] = location
    return JSONResponse({"data": jsonable(data), "meta": meta}, status_code=status, headers=headers)


def many(request: Request, items: list, limit: int, nxt: str | None, ref: dict | None = None) -> JSONResponse:
    meta: dict = {"request_id": request.state.request_id, "limit": limit, "next_cursor": nxt}
    if ref is not None:
        meta["version"] = ref
    return JSONResponse({"data": jsonable(items), "meta": meta})


# -- idempotency ------------------------------------------------------------------------------------------------------
def fingerprint(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


async def idempotent(request: Request, m: Model, fp: str, make: Callable[[], Awaitable[JSONResponse]]) -> JSONResponse:
    """With an Idempotency-Key, the first answer to (organization, world model, route, key) is kept for a day: a retry
    with the same request gets it again; another request with the key is refused."""
    key = request.headers.get("idempotency-key")
    if key is None:
        return await make()
    if not 0 < len(key) <= 255:
        raise ApiError("invalid_request", "Idempotency-Key is 1-255 characters")
    store: dict = request.app.state.idempotency
    now = time.monotonic()
    for k in [k for k, v in store.items() if now - v[3] > IDEMPOTENCY_TTL_S]:
        del store[k]
    slot = (m.org, m.id, request.scope["route"].path, key)
    if slot in store:
        old_fp, status, body, _at, headers = store[slot]
        if old_fp != fp:
            raise ApiError("idempotency_key_reused", "this Idempotency-Key was used for another request")
        return JSONResponse(json.loads(body), status_code=status, headers=headers)
    resp = await make()                  # a failure raises, so only a success is kept
    headers = {k: v for k, v in resp.headers.items() if k.lower() in ("location", "etag")}
    store[slot] = (fp, resp.status_code, bytes(resp.body), now, headers)
    return resp


# -- the audit log ----------------------------------------------------------------------------------------------------
def audit(request: Request, m: Model, status: int, resource_ids: list[str]) -> None:
    p = principal(request)
    lake(request.app).put_audit(AuditRecord(
        org=m.org, id=f"aud_{secrets.token_hex(8)}", at=datetime.now(UTC), request_id=request.state.request_id,
        world_model_id=m.id, method=request.method, route=request.scope["route"].path, status=status,
        actor=p.actor(), scopes=sorted(p.scopes), resource_ids=resource_ids))


# -- jobs -------------------------------------------------------------------------------------------------------------
async def run_job(request: Request, m: Model, kind: str, work: Callable[[], Awaitable[dict]]) -> JSONResponse:
    """Record a job, run it, and answer 202 with it. The work runs before the answer; the contract has the client
    poll, so moving it to a queue later changes no client."""
    jobs: dict = request.app.state.jobs.setdefault((m.org, m.id), {})
    jid = f"job_{secrets.token_hex(8)}"
    job = {"id": jid, "type": kind, "status": "running", "created_at": datetime.now(UTC).isoformat(),
           "finished_at": None, "result": None, "error": None}
    jobs[jid] = job
    try:
        job["result"] = await work()
        job["status"] = "succeeded"
    except Exception as exc:
        err = as_api_error(exc)
        if err is None:
            raise
        job["status"] = "failed"
        job["error"] = problem_body(err.status, err.code, err.detail, request.url.path, request.state.request_id,
                                    err.errors)
    job["finished_at"] = datetime.now(UTC).isoformat()
    result = job["result"] or {}
    linked = [v for k, v in sorted((result.get("detail") or {}).items()) if k.endswith("_id") and isinstance(v, str)]
    audit(request, m, 202, [jid, *result.get("ids", []), *linked])
    return one(request, job, status=202, location=f"/v1/world-models/{m.id}/jobs/{jid}")


def job_of(request: Request, m: Model, job_id: str) -> dict:
    job = request.app.state.jobs.get((m.org, m.id), {}).get(job_id)
    if job is None:
        raise ApiError("job_not_found", f"no job {job_id}")
    return job
