"""Reject foreign Host headers, and cross-site requests that change data."""

import re
from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from yougene.config import allowed_hosts

HOST = re.compile(r"(\[::1\]|[a-z0-9.-]+)(?::[0-9]+)?", re.I)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _origin_host(origin: str) -> str | None:
    if origin == "null":
        return None
    parts = urlsplit(origin)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    return f"[{host}]" if host == "::1" else host


class LoopbackHostMiddleware:
    """DNS-rebinding and CSRF guard for a server that only serves this machine.

    - Every request must carry exactly one Host naming an allowed host.
    - State-changing requests that carry an Origin (all browsers send one for
      cross-origin and same-origin non-GET fetches) must come from an allowed
      host too, so another site open in the browser can't post to the API.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.allowed_hosts = allowed_hosts()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in {"http", "websocket"}:
            headers = scope["headers"]
            hosts = [v.decode("latin-1") for k, v in headers if k == b"host"]
            match = HOST.fullmatch(hosts[0]) if len(hosts) == 1 else None
            if match is None or match[1].lower() not in self.allowed_hosts:
                await self._reject(scope, receive, send, 400, "Invalid host")
                return
            if scope["type"] == "websocket" or scope["method"] not in SAFE_METHODS:
                origins = [v.decode("latin-1") for k, v in headers if k == b"origin"]
                if len(origins) > 1 or (
                    origins and _origin_host(origins[0]) not in self.allowed_hosts
                ):
                    await self._reject(scope, receive, send, 403, "Cross-site request")
                    return
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(scope, receive, send, status: int, text: str) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            await PlainTextResponse(text, status_code=status)(scope, receive, send)
