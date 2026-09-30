"""Telemetry: OpenTelemetry traces with W3C trace context, structured JSON logs,
and a local span collector for an immediate on-screen trace view.

With APPLICATIONINSIGHTS_CONNECTION_STRING set, the Azure Monitor OpenTelemetry
distro exports to Application Insights using a Microsoft Entra credential (the
resource has local authentication disabled). Without it, telemetry stays local.
Full prompts and model responses are never recorded; neither are secrets.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
from collections import OrderedDict, deque
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

from .config import Settings

NAMESPACE = "football-insights"
MAX_TRACES = 300
SAFE_ATTRIBUTE_PREFIXES = ("gen_ai.", "app.", "http.", "url.", "server.", "error.", "client.")
HEADER_PREFIXES = ("http.request.header", "http.response.header")


def _safe_attributes(attributes: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (attributes or {}).items():
        if not key.startswith(SAFE_ATTRIBUTE_PREFIXES) or key.startswith(HEADER_PREFIXES):
            continue
        out[key] = list(value) if isinstance(value, Sequence) and not isinstance(value, str) else value
    return out


def span_to_dict(span: ReadableSpan, service: str) -> dict[str, Any]:
    ctx = span.get_span_context()
    if ctx is None:
        raise ValueError("finished span without a context")
    parent = span.parent
    start, end = span.start_time or 0, span.end_time or 0
    return {
        "service": service,
        "name": span.name,
        "trace_id": format(ctx.trace_id, "032x"),
        "span_id": format(ctx.span_id, "016x"),
        "parent_id": format(parent.span_id, "016x") if parent else None,
        "start_ns": start,
        "duration_ms": round((end - start) / 1e6, 2),
        "status": span.status.status_code.name,
        "kind": span.kind.name,
        "attributes": _safe_attributes(span.attributes),
    }


class SpanCollector(SpanProcessor):
    """Keeps recent spans in memory, grouped by trace, for the local trace view."""

    def __init__(self, service: str, max_traces: int = MAX_TRACES) -> None:
        self.service = service
        self.max_traces = max_traces
        self._traces: OrderedDict[str, deque[dict[str, Any]]] = OrderedDict()
        self._lock = threading.Lock()

    def on_end(self, span: ReadableSpan) -> None:
        record = span_to_dict(span, self.service)
        with self._lock:
            spans = self._traces.setdefault(record["trace_id"], deque(maxlen=200))
            spans.append(record)
            self._traces.move_to_end(record["trace_id"])
            while len(self._traces) > self.max_traces:
                self._traces.popitem(last=False)

    def get(self, trace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._traces.get(trace_id, ()))

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class JsonLinesExporter(SpanExporter):
    """Appends finished spans to a local JSON Lines file (git-ignored)."""

    def __init__(self, path: Path, service: str) -> None:
        self.path = path
        self.service = service
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        lines = [json.dumps(span_to_dict(s, self.service), default=str) for s in spans]
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, platform: str) -> None:
        super().__init__()
        self.service = service
        self.platform = platform

    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span().get_span_context()
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "service": self.service,
            "platform": self.platform,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if span.is_valid:
            payload["trace_id"] = format(span.trace_id, "032x")
            payload["span_id"] = format(span.span_id, "016x")
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["error"] = repr(record.exc_info[1])
        return json.dumps(payload, default=str)


_collector: SpanCollector | None = None


def collector() -> SpanCollector | None:
    return _collector


def configure(service: str, settings: Settings, extra_resource: dict[str, str] | None = None) -> SpanCollector:
    """Set up tracing and logging once per process. Returns the local span collector."""
    global _collector
    if _collector is not None:
        return _collector

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service, settings.platform_name))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level.upper())
    for noisy in ("azure", "httpx", "httpcore", "urllib3", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    attributes = {
        "service.name": settings.otel_service_name or service,
        "service.namespace": NAMESPACE,
        "service.instance.id": os.environ.get("HOSTNAME") or socket.gethostname(),
        "app.platform": settings.platform_name,
        "cloud.region": settings.platform_region or "local",
        "app.image_digest": settings.image_digest or "local build",
    }
    attributes.update(extra_resource or {})
    resource = Resource.create(attributes)
    _collector = SpanCollector(service)
    processors: list[SpanProcessor] = [_collector]
    if settings.platform_name.lower() == "local":
        exporter = JsonLinesExporter(settings.local_trace_dir / f"{service}.jsonl", service)
        processors.append(SimpleSpanProcessor(exporter))

    if settings.applicationinsights_connection_string:
        from azure.monitor.opentelemetry import configure_azure_monitor

        from .identity import azure_credential

        configure_azure_monitor(
            connection_string=settings.applicationinsights_connection_string,
            credential=azure_credential(),
            resource=resource,
            sampling_ratio=1.0,
            span_processors=processors,
            enable_live_metrics=False,
        )
    else:
        provider = TracerProvider(resource=resource)
        for processor in processors:
            provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
    logging.getLogger(__name__).info("telemetry configured", extra={"fields": {
        "exporter": "azure-monitor" if settings.applicationinsights_connection_string else "local-only"}})
    return _collector


def instrument_app(app: Any) -> None:
    """Server spans for FastAPI requests and client spans for httpx, with W3C propagation."""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    def name_client_span(span: Any, request: Any) -> None:
        if span and span.is_recording():
            method = request.method.decode() if isinstance(request.method, bytes) else request.method
            path = request.url.path.decode() if isinstance(request.url.path, bytes) else request.url.path
            span.update_name(f"{method} {path}")

    async def name_client_span_async(span: Any, request: Any) -> None:
        name_client_span(span, request)

    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz,static", exclude_spans=["receive", "send"])
    HTTPXClientInstrumentor().instrument(request_hook=name_client_span, async_request_hook=name_client_span_async)


def tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
