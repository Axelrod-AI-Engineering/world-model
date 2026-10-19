"""Who is calling (Oct 18; docs/design/core-mcp-auth.md): the principal every v1 request acts as, and the verification
of core-minted service tokens.

A **principal** is the verified identity a request acts as: its kind (a core-minted `token`, a static `key`, a
`session` of our own logins, or an open `local` run), its organization (the tenant: path and body never override it),
its subject, the part of core that asked (`azp`), the agent host acting for the person (`act`), its scopes, and the
token's `jti` (the audit join key).

A **service token** is a short-lived ES256 JWT (`typ: at+jwt`, RFC 9068) that core mints per call. It is verified
against a trusted issuer's JWKS (`WORLD_MODEL_TRUSTED_ISSUERS`: `issuer;jwks_url;audience` entries): signature, `iss`,
`aud`, `exp`, `nbf` (60 s leeway), and the claims `sub`, `org`, `jti`. The JWKS is cached for ten minutes and fetched
again on an unknown `kid` (at most once a minute); the last good set serves for a day when the issuer cannot be
reached. `WORLD_MODEL_DENY` (`kid:…`, `org:…`, `sub:…`) refuses at once. Verification is off unless an issuer is
configured. Tests sign with an ephemeral key behind `transport` (an `httpx.MockTransport`); nothing calls core.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt

READ, DOCUMENTS, CHANGES, SIMULATIONS, REVIEW, ADMIN = (
    "read", "documents:write", "changes:write", "simulations:write", "changes:review", "admin")
SCOPES = (READ, DOCUMENTS, CHANGES, SIMULATIONS, REVIEW, ADMIN)
PROPOSE = frozenset({READ, DOCUMENTS, CHANGES, SIMULATIONS})
AGENT_CHANNEL = "core-mcp"
CACHE_S, REFETCH_S, STALE_S, LEEWAY_S = 600, 60, 86400, 60

# Replaced in tests with an httpx.MockTransport; None uses the network.
transport: httpx.BaseTransport | None = None


class TokenError(Exception):
    """A token that cannot be accepted: `code` is invalid_token (401) or issuer_unavailable (503)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code, self.detail = code, detail


@dataclass(frozen=True)
class Principal:
    kind: str                                   # token | key | session | local
    org: str
    sub: str
    scopes: frozenset[str]
    name: str | None = None
    azp: str | None = None
    act: dict | None = None                     # {"sub", "name"} of the agent host acting for the person
    jti: str | None = None

    @property
    def human(self) -> bool:
        """May decide a change: a person (a token or a session), with no agent acting and not through core's MCP."""
        return self.kind in ("token", "session") and self.act is None and self.azp != AGENT_CHANNEL

    def actor(self) -> dict:
        return {"kind": self.kind, "org": self.org, "sub": self.sub, "name": self.name, "azp": self.azp,
                "act": self.act, "jti": self.jti}


@dataclass(frozen=True)
class Issuer:
    issuer: str
    jwks_url: str
    audience: str


def trusted_issuers(raw: str | None = None) -> list[Issuer]:
    raw = os.environ.get("WORLD_MODEL_TRUSTED_ISSUERS", "") if raw is None else raw
    out = []
    for entry in (e.strip() for e in raw.split(",")):
        if not entry:
            continue
        parts = [p.strip() for p in entry.split(";")]
        if len(parts) != 3 or not all(parts):
            raise RuntimeError("WORLD_MODEL_TRUSTED_ISSUERS entries are issuer;jwks_url;audience")
        out.append(Issuer(*parts))
    return out


def deny_list(raw: str | None = None) -> frozenset[tuple[str, str]]:
    raw = os.environ.get("WORLD_MODEL_DENY", "") if raw is None else raw
    out = set()
    for entry in (e.strip() for e in raw.split(",")):
        if not entry:
            continue
        kind, _, value = entry.partition(":")
        if kind not in ("kid", "org", "sub") or not value:
            raise RuntimeError("WORLD_MODEL_DENY entries are kid:<id>, org:<id> or sub:<id>")
        out.add((kind, value))
    return frozenset(out)


def looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2 and token.startswith("eyJ")


@dataclass
class _Keys:
    keys: dict[str, Any] = field(default_factory=dict)
    fetched: float = -1e18
    tried: float = -1e18


class Verifier:
    """Verifies service tokens from the trusted issuers, with a JWKS cache per issuer."""

    def __init__(self, issuers: list[Issuer], deny: frozenset[tuple[str, str]] = frozenset(),
                 clock: Any = time.monotonic) -> None:
        self.issuers = {i.issuer: i for i in issuers}
        self.deny = deny
        self.clock = clock
        self.cache: dict[str, _Keys] = {}

    def __bool__(self) -> bool:
        return bool(self.issuers)

    def _fetch(self, issuer: Issuer) -> dict[str, Any]:
        with httpx.Client(transport=transport, timeout=10) as client:
            body = client.get(issuer.jwks_url).raise_for_status().json()
        return {k["kid"]: jwt.PyJWK.from_dict(k).key for k in body.get("keys", []) if k.get("kid")}

    def key(self, issuer: Issuer, kid: str) -> Any:
        now = self.clock()
        c = self.cache.setdefault(issuer.issuer, _Keys())
        if (kid not in c.keys or now - c.fetched > CACHE_S) and now - c.tried > REFETCH_S:
            c.tried = now
            try:
                c.keys, c.fetched = self._fetch(issuer), now
            except (httpx.HTTPError, ValueError, KeyError, jwt.PyJWKError):
                if now - c.fetched > STALE_S:
                    c.keys = {}
        if kid in c.keys:
            return c.keys[kid]
        if now - c.fetched > CACHE_S:
            raise TokenError("issuer_unavailable", f"the signing key {kid!r} is unknown and {issuer.issuer}'s JWKS "
                                                   "cannot be reached")
        raise TokenError("invalid_token", f"the signing key {kid!r} is not in {issuer.issuer}'s JWKS")

    def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError as err:
            raise TokenError("invalid_token", f"not a JWT: {err}") from err
        issuer = self.issuers.get(str(unverified.get("iss")))
        if issuer is None:
            raise TokenError("invalid_token", "the token's issuer is not trusted")
        if header.get("alg") != "ES256" or header.get("typ") != "at+jwt" or not header.get("kid"):
            raise TokenError("invalid_token", "the token must be ES256, typ at+jwt, with a kid")
        if ("kid", header["kid"]) in self.deny:
            raise TokenError("invalid_token", "the token's signing key is denied")
        try:
            claims = jwt.decode(token, self.key(issuer, header["kid"]), algorithms=["ES256"], audience=issuer.audience,
                                issuer=issuer.issuer, leeway=LEEWAY_S,
                                options={"require": ["exp", "iat", "sub", "org", "jti"]})
        except jwt.PyJWTError as err:
            raise TokenError("invalid_token", f"the token is not valid: {err}") from err
        if ("org", str(claims["org"])) in self.deny or ("sub", str(claims["sub"])) in self.deny:
            raise TokenError("invalid_token", "the token's organization or subject is denied")
        act = claims.get("act")
        if act is not None and not (isinstance(act, dict) and act.get("sub")):
            raise TokenError("invalid_token", "act must be an object with a sub")
        scopes = frozenset(str(claims.get("scope", "")).split()) & frozenset(SCOPES)
        return Principal(kind="token", org=str(claims["org"]), sub=str(claims["sub"]), scopes=scopes,
                         name=claims.get("name"), azp=claims.get("azp"),
                         act=None if act is None else {"sub": str(act["sub"]), "name": act.get("name")},
                         jti=str(claims["jti"]))


def jwks_of(*public_keys: tuple[str, Any]) -> dict:
    """A JWKS document for (kid, public key) pairs: what an issuer serves (and what the tests serve)."""
    out = []
    for kid, key in public_keys:
        jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key))
        out.append({**jwk, "kid": kid, "use": "sig", "alg": "ES256"})
    return {"keys": out}
