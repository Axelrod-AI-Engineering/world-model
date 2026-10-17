"""API keys for the outward service (Oct 17): how other services (MCP tools, the LLM harness, core) call the world model.

WORLD_MODEL_API_KEYS holds comma-separated `caller:key:login` entries. A request with `Authorization: Bearer <key>`
is that caller, acting as that login: it reaches that login's engine and that login's partition of the lakehouse
(its tenant), never another's. A key opens only the service's paths (/api/world-model/... and /mcp), never the
pages or the UI's API. Keys live in the environment (Railway), never in the repository; each is at least 24
characters, and every key is compared on every check, so the time taken does not say which matched.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

SERVICE_PREFIXES = ("/api/world-model", "/mcp")
MIN_KEY = 24


@dataclass(frozen=True)
class ApiKey:
    caller: str
    key: str
    login: str


def api_keys(raw: str | None = None) -> list[ApiKey]:
    raw = os.environ.get("WORLD_MODEL_API_KEYS", "") if raw is None else raw
    out: list[ApiKey] = []
    for entry in (e.strip() for e in raw.split(",")):
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) != 3 or not parts[0] or not parts[1]:
            raise RuntimeError("WORLD_MODEL_API_KEYS entries are caller:key:login")
        if len(parts[1]) < MIN_KEY:
            raise RuntimeError(f"API key for {parts[0]} is shorter than {MIN_KEY} characters")
        out.append(ApiKey(*parts))
    callers = [k.caller for k in out]
    if len(set(callers)) != len(callers):
        raise RuntimeError("WORLD_MODEL_API_KEYS names a caller twice")
    return out


def bearer(headers: dict) -> str | None:
    """The token of an `Authorization: Bearer <token>` header (bytes or str keys), or None."""
    raw = headers.get(b"authorization", headers.get("authorization", b""))
    value = raw.decode("latin-1") if isinstance(raw, bytes) else str(raw)
    scheme, _, token = value.strip().partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def match(keys: list[ApiKey], token: str | None) -> ApiKey | None:
    """The key this token is, or None; every key is compared."""
    found = None
    for k in keys:
        if secrets.compare_digest((token or "").encode(), k.key.encode()) and found is None:
            found = k
    return found if token else None


def is_service_path(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in SERVICE_PREFIXES)
