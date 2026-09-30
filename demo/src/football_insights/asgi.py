"""ASGI wrappers that sit outside the FastAPI apps, before routing and telemetry see a request."""

from __future__ import annotations

from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

TRACE_CONTEXT_HEADERS = frozenset({b"traceparent", b"tracestate", b"baggage"})


class IgnoreIncomingTraceContext:
    """Public requests always start a new trace, so a client can't pick a trace ID shown on stream or add
    spans to someone else's trace. Calls from web to insights still propagate context as usual."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = [(k, v) for k, v in scope["headers"] if k.lower() not in TRACE_CONTEXT_HEADERS]
            scope = {**scope, "headers": headers}
        await self.app(scope, receive, send)


class LimitRequestBody:
    """Rejects request bodies over max_bytes with 413, whether or not the client sends Content-Length.

    The body is read before the app runs and handed to it unchanged, which is fine because every body this
    app accepts is a short question.
    """

    def __init__(self, app: ASGIApp, max_bytes: int, headers: Iterable[tuple[str, str]] = ()) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.headers = [(k.lower().encode(), v.encode()) for k, v in headers]

    async def _reject(self, send: Send) -> None:
        body = b'{"detail":"request body too large"}'
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode()), *self.headers]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > self.max_bytes):
            await self._reject(send)
            return
        chunks: list[bytes] = []
        total = 0
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.max_bytes:
                await self._reject(send)
                return
            chunks.append(chunk)
            more = message.get("more_body", False)
        body = b"".join(chunks)
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
