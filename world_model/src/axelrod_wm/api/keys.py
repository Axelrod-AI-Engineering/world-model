"""Static scoped keys for the outward service (Oct 18; docs/design/core-mcp-auth.md): how non-core callers (the LLM
harness, scripts, our own /mcp) call the world model.

WORLD_MODEL_API_KEYS holds comma-separated `caller:key:org[:scope+scope…]` entries. A request with
`Authorization: Bearer <key>` is that caller (a service, never a person) acting in that organization: it reaches that
organization's world models and documents, never another's. With no scopes listed, a key reads only
(`world_model:read`; Oct 19: direct access is read-only unless granted). The data-ingestion pipeline's key lists
`documents:create` and `changes:create`; `simulations:create` and `admin` may be added; `changes:approve` is refused,
so a key can never approve a change. A caller may hold two keys at once, so a key rotates by overlap. A key opens only the
service's paths (/v1/... and /mcp). Keys live in the environment (Railway), never in the repository; each is at least
24 characters, and every key is compared on every check, so the time taken does not say which matched.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

from axelrod_wm.api.tokens import APPROVE, READ, SCOPES

SERVICE_PREFIXES = ("/v1", "/mcp")
MIN_KEY = 24
MAX_KEYS_PER_CALLER = 2


@dataclass(frozen=True)
class ApiKey:
    caller: str
    key: str
    org: str
    scopes: frozenset[str] = frozenset({READ})


def api_keys(raw: str | None = None) -> list[ApiKey]:
    raw = os.environ.get("WORLD_MODEL_API_KEYS", "") if raw is None else raw
    out: list[ApiKey] = []
    for entry in (e.strip() for e in raw.split(",")):
        if not entry:
            continue
        parts = entry.split(":", 3)            # scopes hold colons (documents:create)
        if len(parts) not in (3, 4) or not all(parts[:3]):
            raise RuntimeError("WORLD_MODEL_API_KEYS entries are caller:key:org[:scope+scope]")
        if len(parts[1]) < MIN_KEY:
            raise RuntimeError(f"API key for {parts[0]} is shorter than {MIN_KEY} characters")
        scopes = frozenset(s for s in parts[3].split("+") if s) if len(parts) == 4 else frozenset({READ})
        unknown = sorted(scopes - set(SCOPES))
        if unknown or not scopes:
            raise RuntimeError(f"API key for {parts[0]} names unknown scopes: {', '.join(unknown) or '(none)'}")
        if APPROVE in scopes:
            raise RuntimeError(f"API key for {parts[0]} asks for {APPROVE}: only a person may approve a change")
        out.append(ApiKey(parts[0], parts[1], parts[2], scopes))
    for caller in {k.caller for k in out}:
        mine = [k for k in out if k.caller == caller]
        if len(mine) > MAX_KEYS_PER_CALLER:
            raise RuntimeError(f"WORLD_MODEL_API_KEYS names {caller} more than twice (two keys rotate by overlap)")
        if len({k.org for k in mine}) > 1:
            raise RuntimeError(f"WORLD_MODEL_API_KEYS gives {caller} two organizations")
    if len({k.key for k in out}) != len(out):
        raise RuntimeError("WORLD_MODEL_API_KEYS lists one key twice")
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
