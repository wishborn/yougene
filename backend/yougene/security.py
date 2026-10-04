"""Reject foreign and malformed Host headers before routing."""

import re

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from yougene.config import allowed_hosts

HOST = re.compile(r"(\[::1\]|[a-z0-9.-]+)(?::[0-9]+)?", re.I)


class LoopbackHostMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.allowed_hosts = allowed_hosts()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in {"http", "websocket"}:
            hosts = [v.decode("latin-1") for k, v in scope["headers"] if k == b"host"]
            match = HOST.fullmatch(hosts[0]) if len(hosts) == 1 else None
            if match is None or match[1].lower() not in self.allowed_hosts:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await PlainTextResponse("Invalid host", status_code=400)(
                        scope, receive, send
                    )
                return
        await self.app(scope, receive, send)
