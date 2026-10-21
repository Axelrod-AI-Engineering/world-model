"""Service tokens (api/tokens.py): what a core-minted ES256 token must be to be accepted, the JWKS cache (fresh, refetched
on an unknown key at most once a minute, stale for a day when the issuer is down), the deny lists, and the principal a
token becomes. Tokens are signed with an ephemeral key; the JWKS is served by an httpx.MockTransport."""

from __future__ import annotations

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from axelrod_wm.api import tokens
from axelrod_wm.api.tokens import (
    Issuer,
    Principal,
    TokenError,
    Verifier,
    deny_list,
    jwks_of,
    looks_like_jwt,
    trusted_issuers,
)
from tests.service.helpers import AUDIENCE, ISSUER, JWKS_URL, Signer


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def signer(monkeypatch):
    s = Signer()
    monkeypatch.setattr(tokens, "transport", s.transport())
    return s


@pytest.fixture
def clock():
    return Clock()


def verifier(clock, deny=frozenset()):
    return Verifier([Issuer(ISSUER, JWKS_URL, AUDIENCE)], deny, clock=clock)


def refused(v, token, code="invalid_token", why=""):
    with pytest.raises(TokenError) as err:
        v.verify(token)
    assert err.value.code == code and why in err.value.detail, err.value.detail


# -- configuration ----------------------------------------------------------------------------------------------------------
def test_issuers_and_deny_lists_parse(monkeypatch):
    assert trusted_issuers(f" {ISSUER} ; {JWKS_URL} ; {AUDIENCE} ,") == [Issuer(ISSUER, JWKS_URL, AUDIENCE)]
    with pytest.raises(RuntimeError, match="issuer;jwks_url;audience"):
        trusted_issuers("a;b")
    assert deny_list("kid:k1, org:o1 ,sub:u1,") == {("kid", "k1"), ("org", "o1"), ("sub", "u1")}
    for bad in ("jti:x", "kid:"):
        with pytest.raises(RuntimeError, match="WORLD_MODEL_DENY"):
            deny_list(bad)
    monkeypatch.delenv("WORLD_MODEL_TRUSTED_ISSUERS", raising=False)
    monkeypatch.delenv("WORLD_MODEL_DENY", raising=False)
    assert trusted_issuers() == [] and deny_list() == frozenset()
    assert not Verifier([]) and Verifier(trusted_issuers(f"{ISSUER};{JWKS_URL};{AUDIENCE}"))


def test_what_looks_like_a_jwt():
    assert looks_like_jwt("eyJa.b.c") and not looks_like_jwt("k" * 32) and not looks_like_jwt("abc.d.e")


# -- a good token -----------------------------------------------------------------------------------------------------------------
def test_a_good_token_is_its_principal(signer, clock):
    p = verifier(clock).verify(signer.token(scope="world_model:read changes:create telepathy", jti="j1"))
    assert p == Principal(kind="token", org="default", sub="org_user_9",
                          scopes=frozenset({"world_model:read", "changes:create"}), name="Ada Reviewer",
                          azp="core-web", act=None, jti="j1")
    assert p.human and p.actor()["jti"] == "j1"


ALL = "world_model:read documents:create changes:create simulations:create changes:approve admin"


@pytest.mark.parametrize("claims", [{"azp": "core-mcp"}, {"act": {"sub": "mcp-client:claude", "name": "Claude"}}])
def test_core_mcp_and_any_agent_read_only(signer, clock, claims):
    """The access boundary (Oct 19): core's backend MCP channel and any agent-driven token read only, whatever the
    token says."""
    p = verifier(clock).verify(signer.token(scope=ALL, **claims))
    assert p.scopes == frozenset({"world_model:read"}) and not p.human


def test_who_counts_as_a_person(signer, clock):
    v = verifier(clock)
    assert v.verify(signer.token()).human
    assert not v.verify(signer.token(azp="core-mcp")).human
    assert v.verify(signer.token(azp=None, name=None, act={"sub": "x"})).act == {"sub": "x", "name": None}
    assert Principal(kind="session", org="o", sub="u", scopes=frozenset()).human
    assert not Principal(kind="key", org="o", sub="u", scopes=frozenset()).human
    assert not Principal(kind="local", org="o", sub="u", scopes=frozenset()).human


def test_a_token_without_scopes_has_none(signer, clock):
    body = jwt.decode(signer.token(), options={"verify_signature": False})
    body.pop("scope")
    tok = jwt.encode(body, signer.key, algorithm="ES256", headers={"kid": signer.kid, "typ": "at+jwt"})
    assert verifier(clock).verify(tok).scopes == frozenset()


# -- what is refused --------------------------------------------------------------------------------------------------------------
def test_a_token_that_is_not_one(signer, clock):
    refused(verifier(clock), "eyJ.not.ajwt", why="not a JWT")


def test_an_untrusted_issuer_audience_or_expired(signer, clock):
    v = verifier(clock)
    refused(v, signer.token(iss="https://evil.test"), why="not trusted")
    refused(v, signer.token(aud="https://someone-else.test"), why="Audience")
    refused(v, signer.token(ttl=-120), why="expired")
    assert v.verify(signer.token(ttl=-30)).sub == "org_user_9"            # within the 60 s leeway


@pytest.mark.parametrize("headers, why", [({"typ": "JWT"}, "typ"), ({"kid": ""}, "kid")])
def test_the_header_must_be_es256_at_jwt_with_a_kid(signer, clock, headers, why):
    refused(verifier(clock), signer.token(headers=headers), why="ES256, typ at+jwt")


def test_another_algorithm_is_refused(signer, clock):
    body = jwt.decode(signer.token(), options={"verify_signature": False})
    tok = jwt.encode(body, "s" * 32, algorithm="HS256", headers={"kid": signer.kid, "typ": "at+jwt"})
    refused(verifier(clock), tok, why="ES256")


def test_a_token_signed_by_another_key(signer, clock):
    other = ec.generate_private_key(ec.SECP256R1())
    refused(verifier(clock), signer.token(key=other), why="not valid")


@pytest.mark.parametrize("claim", ["org", "jti", "sub"])
def test_required_claims(signer, clock, claim):
    body = jwt.decode(signer.token(), options={"verify_signature": False})
    body.pop(claim)
    tok = jwt.encode(body, signer.key, algorithm="ES256", headers={"kid": signer.kid, "typ": "at+jwt"})
    refused(verifier(clock), tok, why=claim)


@pytest.mark.parametrize("act", ["mcp-client", {"name": "no sub"}])
def test_a_malformed_act(signer, clock, act):
    refused(verifier(clock), signer.token(act=act), why="act must be")


def test_the_deny_lists(signer, clock):
    refused(verifier(clock, frozenset({("kid", signer.kid)})), signer.token(), why="signing key is denied")
    refused(verifier(clock, frozenset({("org", "default")})), signer.token(), why="organization or subject")
    refused(verifier(clock, frozenset({("sub", "org_user_9")})), signer.token(), why="organization or subject")


# -- the JWKS cache ---------------------------------------------------------------------------------------------------------------
def test_the_jwks_is_cached_and_refreshed(signer, clock):
    v = verifier(clock)
    v.verify(signer.token())
    v.verify(signer.token())
    assert signer.fetches == 1
    clock.t += tokens.CACHE_S + 1
    v.verify(signer.token())
    assert signer.fetches == 2


def test_an_unknown_kid_refetches_at_most_once_a_minute(signer, clock):
    v = verifier(clock)
    v.verify(signer.token())
    rotated = Signer(kid="rotated")
    refused(v, rotated.token(), why="not in")
    assert signer.fetches == 1                                            # fetched this minute already
    clock.t += tokens.REFETCH_S + 1
    refused(v, rotated.token(), why="not in")
    assert signer.fetches == 2
    refused(v, rotated.token(), why="not in")
    assert signer.fetches == 2                                            # not again within the minute
    clock.t += tokens.REFETCH_S + 1
    refused(v, rotated.token())
    assert signer.fetches == 3


def test_an_issuer_down_keeps_the_last_good_keys_for_a_day(signer, clock):
    v = verifier(clock)
    v.verify(signer.token())
    signer.served = False
    clock.t += tokens.CACHE_S + 1
    assert v.verify(signer.token()).sub == "org_user_9"                  # stale but kept
    refused(v, Signer(kid="new").token(), "issuer_unavailable")           # an unknown key cannot be checked
    clock.t += tokens.STALE_S
    refused(v, signer.token(), "issuer_unavailable")                      # after a day the keys are dropped


def test_an_issuer_down_at_the_first_token(signer, clock):
    signer.served = False
    refused(verifier(clock), signer.token(), "issuer_unavailable")


def test_a_bad_jwks_is_the_issuer_unavailable(monkeypatch, clock):
    import httpx

    s = Signer()
    monkeypatch.setattr(tokens, "transport", httpx.MockTransport(lambda r: httpx.Response(200, content=b"<html>")))
    refused(verifier(clock), s.token(), "issuer_unavailable")
    monkeypatch.setattr(tokens, "transport", httpx.MockTransport(lambda r: httpx.Response(500)))
    refused(verifier(clock), s.token(), "issuer_unavailable")


def test_a_jwks_entry_without_a_kid_is_skipped(monkeypatch, clock):
    import httpx

    s = Signer()
    doc = s.jwks()
    doc["keys"].append({k: v for k, v in doc["keys"][0].items() if k != "kid"})
    monkeypatch.setattr(tokens, "transport", httpx.MockTransport(lambda r: httpx.Response(200, json=doc)))
    assert verifier(clock).verify(s.token()).sub == "org_user_9"


def test_jwks_of_serves_public_keys():
    key = ec.generate_private_key(ec.SECP256R1())
    doc = jwks_of(("k1", key.public_key()))
    assert doc["keys"][0]["kid"] == "k1" and doc["keys"][0]["alg"] == "ES256" and "d" not in doc["keys"][0]
