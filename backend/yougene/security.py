"""Reject foreign and malformed Host headers before routing."""

import re

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

HOST = re.compile(r"(?:127\.0\.0\.1|localhost|\[::1\])(?::[0-9]+)?", re.I)


class LoopbackHostMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in {"http", "websocket"}:
            hosts = [v.decode("latin-1") for k, v in scope["headers"] if k == b"host"]
            if len(hosts) != 1 or not HOST.fullmatch(hosts[0]):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await PlainTextResponse("Invalid host", status_code=400)(
                        scope, receive, send
                    )
                return
        await self.app(scope, receive, send)
