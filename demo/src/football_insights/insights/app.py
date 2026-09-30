"""insights: the internal service that owns the analytics tools and the agent.

It is never exposed publicly: only the web service calls it. Endpoints return
JSON; every tool call is a span with the tool name, duration, row counts, and
evidence IDs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from opentelemetry import trace
from pydantic import BaseModel, Field
from starlette.types import ASGIApp

from ..agent.loop import InsightsAgent, QuestionRejected
from ..analytics.context import ToolContext
from ..analytics.registry import TOOLS, ToolError, function_tools, run_tool
from ..asgi import LimitRequestBody
from ..cards import CARDS
from ..config import get_settings
from ..runtime import describe
from ..schemas import ToolResult
from ..store import CuratedStore, StoreError, load
from ..telemetry import collector, configure, instrument_app, tracer

log = logging.getLogger("football_insights.insights")
RETRY_SECONDS = 15
MAX_BODY_BYTES = 16_384


class AskBody(BaseModel):
    question: str = Field(max_length=2000)
    deployment: str | None = None


class State:
    def __init__(self) -> None:
        self.ctx: ToolContext | None = None
        self.agent: InsightsAgent | None = None
        self.error: str = "starting"
        self.loaded_at: float | None = None
        self._lock = threading.Lock()

    def set(self, store: CuratedStore) -> None:
        with self._lock:
            ctx = ToolContext(store)
            self.ctx = ctx
            self.agent = InsightsAgent(get_settings(), lambda name, args: traced_tool(ctx, name, args))
            self.error = ""
            self.loaded_at = time.time()


state = State()


def _load_once() -> bool:
    settings = get_settings()
    try:
        store = load(settings)
    except (StoreError, OSError) as exc:
        state.error = str(exc)
        log.warning("curated store not available yet", extra={"fields": {"reason": str(exc)}})
        return False
    except Exception as exc:  # blob or credential failures surface here
        state.error = f"{type(exc).__name__}: {exc}"
        log.exception("curated store failed to load")
        return False
    state.set(store)
    ctx = state.ctx
    assert ctx is not None
    ctx.ratings()
    for card in CARDS:
        run_tool(ctx, card.tool, card.arguments)
    log.info("curated store loaded", extra={"fields": {"version": store.version, "source": store.source}})
    return True


async def _load_until_ready() -> None:
    while not await asyncio.to_thread(_load_once):
        await asyncio.sleep(RETRY_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_load_until_ready())
    yield
    task.cancel()


def _ctx() -> ToolContext:
    if state.ctx is None:
        raise HTTPException(status_code=503, detail=f"curated store not loaded: {state.error}")
    return state.ctx


def traced_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> tuple[ToolResult, float]:
    with tracer(__name__).start_as_current_span(f"execute_tool {name}") as span:
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        span.set_attribute("gen_ai.tool.name", name)
        span.set_attribute("app.tool.arguments", json.dumps(arguments, sort_keys=True))
        start = time.perf_counter()
        try:
            result = run_tool(ctx, name, arguments)
        except ToolError as exc:
            span.set_status(trace.StatusCode.ERROR, str(exc))
            raise
        duration = (time.perf_counter() - start) * 1000
        span.set_attribute("app.tool.duration_ms", round(duration, 2))
        span.set_attribute("app.tool.row_counts", json.dumps(result.row_counts, sort_keys=True))
        span.set_attribute("app.evidence_ids", result.evidence_ids)
        span.set_attribute("app.method_version", result.method_version)
        span.set_attribute("app.dataset_version", result.dataset_version)
        return result, duration


def create_app() -> ASGIApp:
    settings = get_settings()
    configure("insights", settings)
    app = FastAPI(title="football-insights insights service", lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)
    instrument_app(app)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "insights"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        if state.ctx is None:
            return JSONResponse({"ready": False, "reason": state.error}, status_code=503)
        return JSONResponse({"ready": True, "version": state.ctx.dataset_version})

    @app.get("/v1/about")
    def about() -> dict[str, Any]:
        ctx = _ctx()
        return {
            "runtime": describe(settings).as_dict(),
            "dataset_version": ctx.dataset_version,
            "dataset_label": ctx.store.dataset_label,
            "curated_source": ctx.store.source,
            "model_deployment": settings.ai_model_deployment,
            "allowed_deployments": settings.allowed_deployments,
            "narrative_mode": settings.narrative_mode,
            "tools": sorted(TOOLS),
        }

    @app.get("/v1/tools")
    def tools() -> list[dict[str, Any]]:
        return function_tools()

    @app.post("/v1/tools/{name}")
    def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            result, _ = traced_tool(_ctx(), name, arguments)
        except ToolError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.model_dump(mode="json")

    @app.get("/v1/cards")
    def cards() -> list[dict[str, Any]]:
        ctx = _ctx()
        out = []
        for card in CARDS:
            result, _ = traced_tool(ctx, card.tool, card.arguments)
            out.append({"number": card.number, "result": result.model_dump(mode="json")})
        return out

    @app.get("/v1/data-quality")
    def data_quality() -> dict[str, Any]:
        ctx = _ctx()
        return {"version": ctx.dataset_version, "report": ctx.store.data_quality}

    @app.post("/v1/ask")
    def ask(body: AskBody) -> dict[str, Any]:
        _ctx()
        agent = state.agent
        assert agent is not None
        try:
            answer = agent.answer(body.question, body.deployment)
        except QuestionRejected as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return answer.model_dump(mode="json")

    @app.get("/v1/traces/{trace_id}")
    def trace_spans(trace_id: str) -> list[dict[str, Any]]:
        if len(trace_id) != 32 or any(c not in "0123456789abcdef" for c in trace_id):
            raise HTTPException(status_code=400, detail="trace id must be 32 lowercase hex characters")
        spans = collector()
        return spans.get(trace_id) if spans else []

    return LimitRequestBody(app, MAX_BODY_BYTES)


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.bind_host, port=settings.insights_port, log_config=None)


if __name__ == "__main__":
    main()
