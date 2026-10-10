"""Optional local Basic Auth; required and fail-closed for hosted demos."""

import base64
import binascii
import os
import secrets

from starlette.responses import PlainTextResponse


class BasicAuthMiddleware:
    def __init__(self, app):
        self.app = app
        self.username = os.environ.get("WORLD_MODEL_BASIC_AUTH_USERNAME", "")
        self.password = os.environ.get("WORLD_MODEL_BASIC_AUTH_PASSWORD", "")
        required = (os.environ.get("WORLD_MODEL_REQUIRE_BASIC_AUTH") == "1"
                    or bool(os.environ.get("RAILWAY_ENVIRONMENT_ID")))
        if (required or self.username or self.password) and not (self.username and self.password):
            raise RuntimeError("Basic Auth requires both username and password")

    def authorized(self, scope):
        headers = dict(scope.get("headers", []))
        try:
            scheme, token = headers.get(b"authorization", b"").split(b" ", 1)
            if scheme.lower() != b"basic":
                return False
            username, password = base64.b64decode(token, validate=True).split(b":", 1)
        except (ValueError, binascii.Error):
            return False
        user_ok = secrets.compare_digest(username, self.username.encode())
        password_ok = secrets.compare_digest(password, self.password.encode())
        return user_ok and password_ok

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or not self.username:
            return await self.app(scope, receive, send)
        # Railway's unauthenticated readiness probe exposes no application data.
        if scope["type"] == "http" and scope["path"] == "/api/health" and scope["method"] in ("GET", "HEAD"):
            return await self.app(scope, receive, send)
        if self.authorized(scope):
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        response = PlainTextResponse("Authentication required", status_code=401,
                                     headers={"WWW-Authenticate": 'Basic realm="World Model", charset="UTF-8"',
                                              "Cache-Control": "no-store"})
        await response(scope, receive, send)
