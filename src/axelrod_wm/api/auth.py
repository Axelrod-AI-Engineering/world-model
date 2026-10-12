"""Optional local Basic Auth; required and fail-closed for hosted demos.

Besides the main login (WORLD_MODEL_BASIC_AUTH_USERNAME and _PASSWORD), WORLD_MODEL_LOGINS adds logins that each open
their own scenario, as comma-separated `username:password:scenario` entries (Oct 11: Emily's login opens her demo). A
request's login is put in its scope (`axelrod_login`), and the app serves that login's engine (api/app.py).
"""

import base64
import binascii
import os
import secrets
from dataclasses import dataclass

from starlette.responses import PlainTextResponse


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

    def authorized(self, scope) -> str | None:
        """The username a request logged in as, or None."""
        headers = dict(scope.get("headers", []))
        try:
            scheme, token = headers.get(b"authorization", b"").split(b" ", 1)
            if scheme.lower() != b"basic":
                return None
            username, password = base64.b64decode(token, validate=True).split(b":", 1)
        except (ValueError, binascii.Error):
            return None
        found = None
        # every login is compared, so the time taken does not say which one matched
        for user, pw in [(self.username, self.password), *((x.username, x.password) for x in self.extra)]:
            user_ok = secrets.compare_digest(username, user.encode())
            password_ok = secrets.compare_digest(password, pw.encode())
            if user_ok and password_ok and found is None:
                found = user
        return found

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or not self.username:
            return await self.app(scope, receive, send)
        # Railway's unauthenticated readiness probe exposes no application data.
        if scope["type"] == "http" and scope["path"] == "/api/health" and scope["method"] in ("GET", "HEAD"):
            return await self.app(scope, receive, send)
        login = self.authorized(scope)
        if login is not None:
            scope["axelrod_login"] = login
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        response = PlainTextResponse("Authentication required", status_code=401,
                                     headers={"WWW-Authenticate": 'Basic realm="World Model", charset="UTF-8"',
                                              "Cache-Control": "no-store"})
        await response(scope, receive, send)
