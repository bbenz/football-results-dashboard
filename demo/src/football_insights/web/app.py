"""web: the only public service. Server-rendered pages over the insights API.

No admin, reset, or debug endpoints. Security headers on every response, a
per-client rate limit, and no third-party assets: the CSS and the small script
are served from this image.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from opentelemetry import trace

from ..cards import by_number
from ..charts import render as render_chart
from ..config import get_settings
from ..runtime import describe
from ..schemas import Answer, Chart, Fact, ToolResult
from ..telemetry import collector, configure, instrument_app

log = logging.getLogger("football_insights.web")
HERE = Path(__file__).parent
EXAMPLES = (
    "Did hosting help Canada, Mexico, and the United States at the 2026 World Cup?",
    "Who is the best team of all time, and does the answer change with the definition?",
    "How has home advantage changed since the early 1900s?",
    "Which Premier League team is best at counterattacks?",
)
SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class RateLimiter:
    """Fixed one-minute window per client and bucket, in memory (per replica)."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str, int], int] = {}
        self._lock = threading.Lock()

    def allow(self, client: str, bucket: str, limit: int) -> bool:
        window = int(time.time() // 60)
        key = (client, bucket, window)
        with self._lock:
            if len(self._hits) > 10_000:
                self._hits = {k: v for k, v in self._hits.items() if k[2] == window}
            self._hits[key] = self._hits.get(key, 0) + 1
            return self._hits[key] <= limit


def client_key(request: Request) -> str:
    # The platform ingress appends the caller's address; the last hop is the one it added.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def fact_display(fact: dict[str, Any]) -> str:
    return Fact.model_validate(fact).display


def chart_svg(chart: dict[str, Any] | None) -> Markup:
    if not chart:
        return Markup("")
    return Markup(render_chart(Chart.model_validate(chart)))  # noqa: S704 - SVG built from escaped tool data


def answer_view(answer: Answer) -> dict[str, Any]:
    """Pick what the answer page shows: key facts (cited by the model, else the first tool's top facts) and the
    first chart. All of it comes from tool results, never from model text."""
    facts = [f for r in answer.results for f in r.facts]
    by_id = {f.id: f for f in facts}
    key = [by_id[e] for e in answer.key_evidence_ids if e in by_id] or (answer.results[0].facts[:4]
                                                                         if answer.results else [])
    chart = next((r.chart for r in answer.results if r.chart), None)
    primary = next((r for r in answer.results if r.chart), answer.results[0] if answer.results else None)
    return {"key_facts": [f.model_dump() for f in key[:6]], "chart": chart.model_dump() if chart else None,
            "primary": primary.model_dump(mode="json") if primary else None}


def create_app(client: httpx.AsyncClient | None = None) -> FastAPI:
    settings = get_settings()
    configure("web", settings)
    client = client or httpx.AsyncClient(base_url=settings.insights_url, timeout=httpx.Timeout(10.0, read=90.0))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await client.aclose()

    app = FastAPI(title="football-insights web", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    instrument_app(app)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["fact"] = fact_display
    templates.env.globals["chart_svg"] = chart_svg
    limiter = RateLimiter()
    runtime = describe(settings)

    @app.middleware("http")
    async def headers_and_limits(request: Request, call_next):
        path = request.url.path
        if not path.startswith(("/static", "/healthz", "/readyz")):
            is_ask = request.method == "POST" and path in ("/ask", "/api/ask")
            bucket, limit = ("ask", settings.ask_rate_limit_per_minute) if is_ask \
                else ("page", settings.web_rate_limit_per_minute)
            if not limiter.allow(client_key(request), bucket, limit):
                response: Response = JSONResponse({"detail": "rate limit exceeded; try again in a minute"},
                                                  status_code=429)
                response.headers.update(SECURITY_HEADERS)
                return response
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        if path.startswith("/static"):
            response.headers["Cache-Control"] = "public, max-age=3600"
        else:
            response.headers["Cache-Control"] = "no-store"
        return response

    async def insights_get(path: str) -> Any:
        response = await client.get(path)
        response.raise_for_status()
        return response.json()

    async def badge() -> dict[str, Any]:
        info: dict[str, Any] = {**runtime.as_dict(), "dataset_version": "unavailable", "dataset_label": "",
                                "model_deployment": settings.ai_model_deployment, "narrative_mode": "unavailable",
                                "insights_digest": "", "insights_ok": False}
        try:
            about = await insights_get("/v1/about")
        except (httpx.HTTPError, ValueError) as exc:
            info["insights_error"] = type(exc).__name__
            return info
        info.update(dataset_version=about["dataset_version"], dataset_label=about["dataset_label"],
                    model_deployment=about["model_deployment"], narrative_mode=about["narrative_mode"],
                    insights_digest=about["runtime"]["short_digest"], insights_ok=True)
        return info

    def page(request: Request, template: str, status_code: int = 200, **context: Any) -> HTMLResponse:
        span = trace.get_current_span().get_span_context()
        context.setdefault("trace_id", format(span.trace_id, "032x") if span.is_valid else "")
        return templates.TemplateResponse(request, template, context, status_code=status_code)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "web"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        try:
            response = await client.get("/readyz")
            ready = response.status_code == 200
        except httpx.HTTPError:
            ready = False
        return JSONResponse({"ready": ready}, status_code=200 if ready else 503)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        info = await badge()
        cards: list[dict[str, Any]] = []
        error = ""
        try:
            meta = by_number()
            for item in await insights_get("/v1/cards"):
                result = ToolResult.model_validate(item["result"])
                cards.append({"card": meta[item["number"]], "result": result.model_dump(mode="json")})
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            error = f"The insights service is not ready yet ({type(exc).__name__})."
        return page(request, "index.html", badge=info, cards=cards, error=error, examples=EXAMPLES,
                    max_chars=settings.question_max_chars)

    async def ask_insights(question: str, deployment: str | None = None) -> tuple[int, dict[str, Any]]:
        payload: dict[str, Any] = {"question": question[: settings.question_max_chars * 2]}
        if deployment:
            payload["deployment"] = deployment
        try:
            response = await client.post("/v1/ask", json=payload)
        except httpx.HTTPError as exc:
            return 503, {"detail": f"The insights service is unreachable ({type(exc).__name__})."}
        if response.status_code != 200:
            detail = response.json().get("detail", response.text) if response.headers.get(
                "content-type", "").startswith("application/json") else response.text
            return response.status_code, {"detail": str(detail)}
        return 200, response.json()

    @app.post("/ask", response_class=HTMLResponse)
    async def ask_page(request: Request, question: str = Form(default="", max_length=4000)) -> HTMLResponse:
        info = await badge()
        status, body = await ask_insights(question)
        if status != 200:
            return page(request, "answer.html", badge=info, answer=None, question=question, error=body["detail"],
                        examples=EXAMPLES, max_chars=settings.question_max_chars,
                        status_code=400 if status == 400 else 503)
        answer = Answer.model_validate(body)
        return page(request, "answer.html", badge=info, answer=answer.model_dump(mode="json"),
                    view=answer_view(answer), question=answer.question, error="", examples=EXAMPLES,
                    max_chars=settings.question_max_chars)

    @app.post("/api/ask")
    async def ask_api(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse({"detail": "send JSON: {\"question\": \"...\"}"}, status_code=400)
        if not isinstance(body, dict) or not isinstance(body.get("question"), str):
            return JSONResponse({"detail": "send JSON: {\"question\": \"...\"}"}, status_code=400)
        deployment = body.get("deployment") if isinstance(body.get("deployment"), str) else None
        status, answer = await ask_insights(body["question"], deployment)
        return JSONResponse(answer, status_code=status)

    @app.get("/data", response_class=HTMLResponse)
    async def data_page(request: Request) -> HTMLResponse:
        info = await badge()
        try:
            dq = await insights_get("/v1/data-quality")
        except (httpx.HTTPError, ValueError) as exc:
            return page(request, "data.html", badge=info, dq=None, error=type(exc).__name__, status_code=503)
        return page(request, "data.html", badge=info, dq=dq["report"], version=dq["version"], error="")

    @app.get("/trace/{trace_id}", response_class=HTMLResponse)
    async def trace_view(request: Request, trace_id: str) -> HTMLResponse:
        info = await badge()
        if len(trace_id) != 32 or any(c not in "0123456789abcdef" for c in trace_id):
            return page(request, "trace.html", badge=info, spans=[], target=trace_id,
                        error="A trace ID is 32 lowercase hexadecimal characters.", status_code=400)
        local = collector()
        spans = list(local.get(trace_id)) if local else []
        with contextlib.suppress(httpx.HTTPError, ValueError):
            spans += await insights_get(f"/v1/traces/{trace_id}")
        spans.sort(key=lambda s: s["start_ns"])
        start = spans[0]["start_ns"] if spans else 0
        total = max(((s["start_ns"] - start) / 1e6 + s["duration_ms"]) for s in spans) if spans else 1.0
        depth: dict[str, int] = {}
        for span in spans:
            depth[span["span_id"]] = depth.get(span["parent_id"] or "", -1) + 1
            span["offset_ms"] = round((span["start_ns"] - start) / 1e6, 1)
            span["depth"] = depth[span["span_id"]]
            span["left_pct"] = round(100 * span["offset_ms"] / total, 2) if total else 0
            span["width_pct"] = max(0.4, round(100 * span["duration_ms"] / total, 2)) if total else 100
        return page(request, "trace.html", badge=info, spans=spans, target=trace_id, total_ms=round(total, 1),
                    error="" if spans else "No spans for this trace are held in memory by web or insights.")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host="0.0.0.0", port=settings.web_port, log_config=None)  # noqa: S104


if __name__ == "__main__":
    main()
