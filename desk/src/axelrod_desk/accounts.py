"""Accounts of the desk itself (Nov 2): a person signs in with an email and a password of ours, and their world models
are kept under their account.

These are never Claude credentials. A reader reads on the plan of whoever signed in to Claude Code on the machine it runs
on, through Claude Code's own sign-in; the desk only gives that reader a token of its own (kind `reader`) so it can take
documents and hand back figures. Passwords are kept as scrypt hashes; a session or reader token is kept as its SHA-256, so
the database never holds one that works.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from axelrod_desk.db import Db, now

KINDS = ("web", "reader")
N, R, P = 2**14, 8, 1


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    return f"scrypt${salt.hex()}${key.hex()}"


def check_password(password: str, stored: str) -> bool:
    _, salt, key = stored.split("$")
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)).split("$")[2], key)


def create(db: Db, email: str, name: str, password: str, *, admin: bool = False) -> dict[str, Any]:
    email = email.strip().lower()
    if "@" not in email:
        raise ValueError("an account needs an email address")
    if len(password) < 8:
        raise ValueError("a password needs at least 8 characters")
    if db.one("select id from accounts where email = ?", [email]):
        raise ValueError(f"{email} already has an account")
    aid = db.insert("accounts", {"email": email, "name": name.strip() or email, "pw": hash_password(password),
                                 "admin": int(admin), "created_at": now()})
    return public(db.one("select * from accounts where id = ?", [aid]))


def public(a: dict[str, Any]) -> dict[str, Any]:
    return {"id": a["id"], "email": a["email"], "name": a["name"], "admin": bool(a["admin"])}


def sign_in(db: Db, email: str, password: str) -> dict[str, Any] | None:
    a = db.one("select * from accounts where email = ?", [email.strip().lower()])
    return public(a) if a and check_password(password, a["pw"]) else None


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue(db: Db, account_id: int, kind: str = "web") -> str:
    """A new token for the account, shown once. A new reader token retires the account's earlier ones."""
    if kind not in KINDS:
        raise ValueError(f"a token is one of {KINDS}")
    if kind == "reader":
        db.run("delete from sessions where account_id = ? and kind = 'reader'", [account_id])
    token = secrets.token_urlsafe(32)
    db.insert("sessions", {"token": _digest(token), "account_id": account_id, "kind": kind, "created_at": now()})
    return token


def resolve(db: Db, token: str, kind: str) -> dict[str, Any] | None:
    s = db.one("select * from sessions where token = ? and kind = ?", [_digest(token), kind])
    if not s:
        return None
    db.update("sessions", "token", s["token"], {"last_used": now()})
    return public(db.one("select * from accounts where id = ?", [s["account_id"]]))


def revoke(db: Db, token: str) -> None:
    db.run("delete from sessions where token = ?", [_digest(token)])


def has_reader(db: Db, account_id: int) -> dict[str, Any] | None:
    return db.one("select created_at, last_used from sessions where account_id = ? and kind = 'reader'", [account_id])


__all__ = ["check_password", "create", "has_reader", "hash_password", "issue", "public", "resolve", "revoke", "sign_in"]
