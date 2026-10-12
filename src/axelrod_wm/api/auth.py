"""Sign-in for hosted demos: off locally, required and fail-closed when hosted.

The main login (WORLD_MODEL_BASIC_AUTH_USERNAME and _PASSWORD) opens the server's scenario; WORLD_MODEL_LOGINS adds
logins that each open their own, as comma-separated `username:password:scenario` entries (Oct 11: Emily's login opens
her demo). The credentials live in the environment (Railway), never in the repository; there is no user database.

A browser signs in on /login (a form, Oct 12; it replaced the browser's Basic Auth prompt) and gets a session cookie:
the username and an expiry, signed with HMAC-SHA256. /logout clears it. The session is the only credential: a script
signs in by posting to /login and keeping the cookie. (Oct 12: a Basic Authorization header is no longer accepted. A
browser that once answered the old Basic prompt keeps sending that header on its own, so Sign out could not sign it
out.) A request's login is put in its scope (`axelrod_login`), and the app serves that login's engine
(api/app.py). Pages without a session are sent to /login; the API and the WebSocket answer 401 and close instead.
"""

import base64
import binascii
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, quote

from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse

COOKIE = "axelrod_session"
SESSION_DAYS = 14
KDF_ROUNDS = 200_000              # PBKDF2 rounds for the session signing key
LOGIN_PAGE = Path(__file__).with_name("login.html")


@dataclass(frozen=True)
class Login:
    username: str
    password: str
    scenario: str


def extra_logins(raw: str | None = None) -> list[Login]:
    """The logins WORLD_MODEL_LOGINS adds, each with its own scenario."""
    raw = os.environ.get("WORLD_MODEL_LOGINS", "") if raw is None else raw
    out: list[Login] = []
    for entry in (e.strip() for e in raw.split(",")):
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) != 3 or not all(parts):
            raise RuntimeError("WORLD_MODEL_LOGINS entries are username:password:scenario")
        out.append(Login(*parts))
    return out


class BasicAuthMiddleware:
    def __init__(self, app):
        self.app = app
        self.username = os.environ.get("WORLD_MODEL_BASIC_AUTH_USERNAME", "")
        self.password = os.environ.get("WORLD_MODEL_BASIC_AUTH_PASSWORD", "")
        required = (os.environ.get("WORLD_MODEL_REQUIRE_BASIC_AUTH") == "1"
                    or bool(os.environ.get("RAILWAY_ENVIRONMENT_ID")))
        if (required or self.username or self.password) and not (self.username and self.password):
            raise RuntimeError("Basic Auth requires both username and password")
        self.extra = extra_logins()
        if self.extra and not self.username:
            raise RuntimeError("WORLD_MODEL_LOGINS needs the main Basic Auth login as well")
        self.logins = [(self.username, self.password), *((x.username, x.password) for x in self.extra)]
        # DECISION: the signing key is WORLD_MODEL_SESSION_SECRET when set, else derived from every login's password,
        # so sessions survive a restart and changing any password signs everyone out. It is derived with PBKDF2 (a
        # slow key-derivation function, as anything made from passwords should be), once, when the server starts.
        secret = os.environ.get("WORLD_MODEL_SESSION_SECRET") or "|".join(f"{u}:{p}" for u, p in self.logins)
        self.key = hashlib.pbkdf2_hmac("sha256", secret.encode(), b"axelrod-world-model-session", KDF_ROUNDS)

    # -- credentials ------------------------------------------------------------------------------------------------
    def check(self, username: bytes, password: bytes) -> str | None:
        """The login these credentials belong to, or None. Every login is compared, so the time taken does not say
        which one matched."""
        found = None
        for user, pw in self.logins:
            user_ok = secrets.compare_digest(username, user.encode())
            password_ok = secrets.compare_digest(password, pw.encode())
            if user_ok and password_ok and found is None:
                found = user
        return found

    # -- the session cookie -----------------------------------------------------------------------------------------
    def sign(self, username: str) -> str:
        body = f"{username}|{int(time.time()) + SESSION_DAYS * 86400}"
        mac = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
        return base64.urlsafe_b64encode(f"{body}|{mac}".encode()).decode()

    def session(self, headers: dict) -> str | None:
        raw = headers.get(b"cookie", b"").decode("latin-1")
        for part in raw.split(";"):
            name, _, value = part.strip().partition("=")
            if name != COOKIE or not value:
                continue
            try:
                username, expires, mac = base64.urlsafe_b64decode(value.encode()).decode().rsplit("|", 2)
            except (ValueError, binascii.Error, UnicodeDecodeError):
                return None
            want = hmac.new(self.key, f"{username}|{expires}".encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(mac, want) or not expires.isdigit() or int(expires) < time.time():
                return None
            return username if any(username == u for u, _ in self.logins) else None
        return None

    def authorized(self, scope) -> str | None:
        """The username a request is signed in as (its session cookie), or None."""
        return self.session(dict(scope.get("headers", [])))

    @staticmethod
    def secure(scope) -> bool:
        headers = dict(scope.get("headers", []))
        return scope.get("scheme") == "https" or headers.get(b"x-forwarded-proto", b"").startswith(b"https")

    # -- the pages --------------------------------------------------------------------------------------------------
    @staticmethod
    def safe_next(value: str | None) -> str:
        # only a path on this site, never another host
        return value if value and value.startswith("/") and not value.startswith("//") else "/"

    def page(self, next_: str = "/", error: str = "", status: int = 200) -> HTMLResponse:
        html = LOGIN_PAGE.read_text().replace("{{next}}", escape(next_, quote=True)).replace(
            "{{error}}", f'<p class="err" role="alert">{escape(error)}</p>' if error else "")
        return HTMLResponse(html, status_code=status, headers={"Cache-Control": "no-store"})

    async def login(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        if scope["method"] != "POST":
            already = self.authorized(scope)
            nxt = self.safe_next(query.get("next", ["/"])[0])
            resp = RedirectResponse(nxt, status_code=303) if already else self.page(nxt)
            return await resp(scope, receive, send)
        body = b""
        while True:
            msg = await receive()
            body += msg.get("body", b"")
            if not msg.get("more_body") or len(body) > 16384:
                break
        form = parse_qs(body.decode("utf-8", "replace"))
        user = form.get("username", [""])[0].strip()
        nxt = self.safe_next(form.get("next", ["/"])[0])
        who = self.check(user.encode(), form.get("password", [""])[0].encode())
        if who is None:
            return await self.page(nxt, "That username and password do not match.", 401)(scope, receive, send)
        resp = RedirectResponse(nxt, status_code=303)
        resp.set_cookie(COOKIE, self.sign(who), max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=self.secure(scope), path="/")
        await resp(scope, receive, send)

    async def logout(self, scope, receive, send):
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(COOKIE, path="/")
        await resp(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if not self.username:
            # no sign-in configured (a local run): /login and /logout just go to the demo
            if scope["type"] == "http" and path in ("/login", "/logout"):
                return await RedirectResponse("/", status_code=303)(scope, receive, send)
            return await self.app(scope, receive, send)
        if scope["type"] == "http":
            # Railway's unauthenticated readiness probe exposes no application data.
            if path == "/api/health" and scope["method"] in ("GET", "HEAD"):
                return await self.app(scope, receive, send)
            if path == "/login":
                return await self.login(scope, receive, send)
            if path == "/logout":
                return await self.logout(scope, receive, send)
        login = self.authorized(scope)
        if login is not None:
            scope["axelrod_login"] = login
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        # a page goes to the sign-in form; anything else (the API, a script) is refused, with no browser prompt
        accept = dict(scope.get("headers", [])).get(b"accept", b"")
        if scope["method"] == "GET" and not path.startswith("/api") and b"text/html" in accept:
            qs = scope.get("query_string", b"").decode()
            return await RedirectResponse(f"/login?next={quote(path + ('?' + qs if qs else ''), safe='/')}",
                                          status_code=303)(scope, receive, send)
        await PlainTextResponse("Authentication required", status_code=401,
                                headers={"Cache-Control": "no-store"})(scope, receive, send)
