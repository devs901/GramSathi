"""Small ASGI hardening middleware for GramSathi."""
from __future__ import annotations

import uuid


class SecurityHeadersMiddleware:
    """Attach browser security headers and a request correlation ID."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k.lower() == b"x-request-id"), None)
        if not request_id or len(request_id) > 100:
            request_id = str(uuid.uuid4())

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"cache-control", b"no-store"),
                    (b"x-request-id", request_id.encode("ascii", "ignore")),
                ])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
