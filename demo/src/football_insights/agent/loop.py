"""The insights agent: a direct, bounded tool-calling loop over the Responses API.

One model deployment (from configuration) reads the question, calls typed
read-only tools, and returns a short narrative as structured JSON. The loop
enforces the limits (question length, tool calls, output tokens, time), checks
every narrative number against the tool results, retries once with feedback,
and otherwise falls back to the deterministic evidence with a visible notice.
A fallback never hides a broken model path: the answer's narrative_status and
the telemetry both say whether the narrative is live.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import trace

from ..config import Settings
from ..schemas import Answer, Grounding, ModelUsage, ToolCallRecord, ToolResult
from . import grounding, narratives, pricing
from .instructions import ANSWER_FORMAT, INSTRUCTIONS, RETRY_FEEDBACK

log = logging.getLogger("football_insights.agent")
tracer = trace.get_tracer(__name__)
PROVIDER = "azure.ai.openai"
AGENT_NAME = "football-insights"

ToolRunner = Callable[[str, dict[str, Any]], tuple[ToolResult, float]]


class QuestionRejected(ValueError):
    pass


@dataclass
class _Run:
    question: str
    deployment: str
    results: list[ToolResult] = field(default_factory=list)
    calls: list[ToolCallRecord] = field(default_factory=list)
    usage: ModelUsage | None = None
    started: float = field(default_factory=time.perf_counter)

    def add_usage(self, response: Any, latency_ms: float) -> None:
        usage = getattr(response, "usage", None)
        if self.usage is None:
            self.usage = ModelUsage(deployment=self.deployment)
        self.usage.calls += 1
        self.usage.latency_ms = round(self.usage.latency_ms + latency_ms, 1)
        if usage is not None:
            self.usage.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
            self.usage.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
            details = getattr(usage, "input_tokens_details", None)
            self.usage.cached_input_tokens += int(getattr(details, "cached_tokens", 0) or 0)
            out_details = getattr(usage, "output_tokens_details", None)
            self.usage.reasoning_tokens += int(getattr(out_details, "reasoning_tokens", 0) or 0)
        self.usage.estimated_cost_usd = pricing.estimate(self.deployment, self.usage.input_tokens,
                                                         self.usage.cached_input_tokens, self.usage.output_tokens)


def _item_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    return dict(item.model_dump(exclude_none=True))


def _is_content_filter(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        code = code or body.get("code") or (body.get("error") or {}).get("code")
    return code == "content_filter" or "content_filter" in str(exc)


class InsightsAgent:
    def __init__(self, settings: Settings, run_tool: ToolRunner, client_factory: Callable[[], Any] | None = None):
        self.settings = settings
        self.run_tool = run_tool
        self._client_factory = client_factory
        self._client: Any = None

    def client(self) -> Any:
        if self._client is None:
            if self._client_factory is not None:
                self._client = self._client_factory()
            else:
                from .client import openai_client

                self._client = openai_client(self.settings)
        return self._client

    def _validate(self, question: str, deployment: str | None) -> tuple[str, str]:
        question = " ".join((question or "").split())
        if not question:
            raise QuestionRejected("Type a question first.")
        if len(question) > self.settings.question_max_chars:
            raise QuestionRejected(f"Questions are limited to {self.settings.question_max_chars} characters.")
        chosen = deployment or self.settings.ai_model_deployment
        if chosen not in self.settings.allowed_deployments:
            raise QuestionRejected(f"Deployment {chosen!r} is not allowed here.")
        return question, chosen

    def answer(self, question: str, deployment: str | None = None, trace_id: str = "") -> Answer:
        question, chosen = self._validate(question, deployment)
        mode = self.settings.narrative_mode
        with tracer.start_as_current_span(f"invoke_agent {AGENT_NAME}") as span:
            span.set_attribute("gen_ai.operation.name", "invoke_agent")
            span.set_attribute("gen_ai.agent.name", AGENT_NAME)
            span.set_attribute("gen_ai.provider.name", PROVIDER)
            span.set_attribute("gen_ai.request.model", chosen)
            span.set_attribute("app.narrative_mode", mode)
            if mode == "cached":
                result = self._cached(question, "Showing a cached narrative (AI_NARRATIVE_MODE=cached).")
            elif mode == "off":
                result = self._unavailable(question, "The AI narrative is switched off in this deployment.")
            else:
                result = self._live(question, chosen)
            result.trace_id = trace_id or format(span.get_span_context().trace_id, "032x")
            span.set_attribute("app.narrative_status", result.narrative_status)
            span.set_attribute("app.grounding.status", result.grounding.status)
            span.set_attribute("app.tool_calls", len(result.tool_calls))
            if result.model:
                span.set_attribute("gen_ai.usage.input_tokens", result.model.input_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", result.model.output_tokens)
                span.set_attribute("app.estimated_cost_usd", result.model.estimated_cost_usd)
            log.info("answer", extra={"fields": {
                "narrative_status": result.narrative_status, "grounding": result.grounding.status,
                "tool_calls": [c.name for c in result.tool_calls], "deployment": chosen,
                "input_tokens": result.model.input_tokens if result.model else 0,
                "output_tokens": result.model.output_tokens if result.model else 0}})
            return result

    def _cached(self, question: str, notice: str) -> Answer:
        cached = narratives.load(self.settings.narrative_cache_dir, question)
        if cached is None:
            return self._unavailable(question, notice.replace("Showing a cached narrative", "No cached narrative "
                                                              "exists for this question"))
        return cached.model_copy(update={"narrative_status": "cached", "notice": notice, "trace_id": ""})

    def _unavailable(self, question: str, notice: str, run: _Run | None = None) -> Answer:
        results = run.results if run else []
        return Answer(question=question, narrative=None, narrative_status="unavailable", notice=notice,
                      results=results, tool_calls=run.calls if run else [], model=run.usage if run else None,
                      grounding=Grounding(status="not_applicable"), caveats=_caveats(results),
                      cannot_tell=_cannot(results))

    def _live(self, question: str, deployment: str) -> Answer:
        run = _Run(question=question, deployment=deployment)
        try:
            parsed = self._converse(run, [{"role": "user", "content": question}])
        except Exception as exc:
            if _is_content_filter(exc):
                return Answer(question=question, narrative=None, narrative_status="filtered",
                              notice="Foundry content filtering blocked this request. Nothing was generated.",
                              results=run.results, tool_calls=run.calls, model=run.usage,
                              grounding=Grounding(status="not_applicable"), caveats=_caveats(run.results),
                              cannot_tell=_cannot(run.results))
            log.warning("live model call failed", extra={"fields": {"error": type(exc).__name__}})
            trace.get_current_span().set_attribute("error.type", type(exc).__name__)
            cached = narratives.load(self.settings.narrative_cache_dir, question)
            if cached is not None:
                return cached.model_copy(update={
                    "narrative_status": "cached", "trace_id": "",
                    "notice": f"The live model is unavailable ({type(exc).__name__}); showing a cached narrative."})
            return self._unavailable(question, f"The AI narrative is unavailable right now ({type(exc).__name__}). "
                                               "The insight cards and any evidence below are deterministic.", run)
        return self._finish(run, parsed)

    def _call(self, run: _Run, input_items: list[dict[str, Any]], tool_choice: str | None = "auto") -> Any:
        budget = self.settings.ai_timeout_seconds - (time.perf_counter() - run.started)
        if budget <= 1:
            raise TimeoutError("answer time budget exhausted")
        kwargs: dict[str, Any] = {
            "model": run.deployment,
            "instructions": INSTRUCTIONS,
            "input": input_items,
            "max_output_tokens": self.settings.ai_max_output_tokens,
            "reasoning": {"effort": self.settings.ai_reasoning_effort},
            "text": {"format": ANSWER_FORMAT},
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        if tool_choice is not None:
            from ..analytics.registry import function_tools

            kwargs.update(tools=function_tools(), tool_choice=tool_choice, parallel_tool_calls=True)
        with tracer.start_as_current_span(f"chat {run.deployment}") as span:
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.provider.name", PROVIDER)
            span.set_attribute("gen_ai.request.model", run.deployment)
            span.set_attribute("gen_ai.request.max_tokens", self.settings.ai_max_output_tokens)
            start = time.perf_counter()
            response = self.client().responses.create(**kwargs, timeout=budget)
            latency = (time.perf_counter() - start) * 1000
            run.add_usage(response, latency)
            usage = getattr(response, "usage", None)
            span.set_attribute("gen_ai.response.model", str(getattr(response, "model", run.deployment)))
            span.set_attribute("gen_ai.response.id", str(getattr(response, "id", "")))
            if usage is not None:
                span.set_attribute("gen_ai.usage.input_tokens", int(getattr(usage, "input_tokens", 0) or 0))
                span.set_attribute("gen_ai.usage.output_tokens", int(getattr(usage, "output_tokens", 0) or 0))
            span.set_attribute("app.latency_ms", round(latency, 1))
            incomplete = getattr(response, "incomplete_details", None)
            if incomplete is not None and getattr(incomplete, "reason", "") == "content_filter":
                raise _ContentFiltered("completion filtered")
            return response

    def _converse(self, run: _Run, input_items: list[dict[str, Any]]) -> dict[str, Any]:
        max_calls = self.settings.ai_max_tool_calls
        response = self._call(run, input_items)
        for _ in range(max_calls + 1):
            calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
            if not calls:
                return _parse(response)
            input_items += [_item_dict(item) for item in response.output]
            for call in calls:
                input_items.append({"type": "function_call_output", "call_id": call.call_id,
                                    "output": self._execute(run, call, max_calls)})
            response = self._call(run, input_items, tool_choice="auto" if len(run.calls) < max_calls else "none")
        return _parse(response)

    def _execute(self, run: _Run, call: Any, max_calls: int) -> str:
        if len(run.calls) >= max_calls:
            run.calls.append(ToolCallRecord(name=call.name, ok=False, error="tool-call limit reached"))
            return json.dumps({"error": f"Tool-call limit of {max_calls} reached. Answer with the results you have."})
        try:
            arguments = json.loads(call.arguments or "{}")
            result, duration = self.run_tool(call.name, arguments)
        except Exception as exc:
            run.calls.append(ToolCallRecord(name=str(call.name), ok=False, error=f"{type(exc).__name__}: {exc}"[:300]))
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"[:300]})
        run.results.append(result)
        run.calls.append(ToolCallRecord(name=call.name, arguments=arguments, duration_ms=round(duration, 2),
                                        evidence_ids=result.evidence_ids, row_counts=result.row_counts))
        return result.model_dump_json(exclude={"chart"})

    def _finish(self, run: _Run, parsed: dict[str, Any]) -> Answer:
        narrative = str(parsed.get("narrative", "")).strip()
        in_scope = bool(parsed.get("in_scope", True))
        if not run.results:
            return Answer(question=run.question, in_scope=in_scope, narrative=None, narrative_status="fallback",
                          notice=("The model answered without consulting the analytics tools, so its answer is "
                                  "hidden. Try one of the seven questions, or rephrase."),
                          tool_calls=run.calls, model=run.usage,
                          grounding=grounding.grounding("failed_fallback", 0, ["(no tool was called)"]))
        known = {fid for r in run.results for fid in r.evidence_ids}
        key_ids = [e for e in parsed.get("key_evidence_ids", []) if e in known]
        checked, ungrounded = grounding.check(narrative, run.results, run.question)
        status = "passed"
        if ungrounded:
            retry = self._retry(run, narrative, ungrounded)
            if retry is not None:
                narrative, key_ids_retry, in_scope = retry
                key_ids = [e for e in key_ids_retry if e in known] or key_ids
                checked, ungrounded = grounding.check(narrative, run.results, run.question)
                status = "passed_after_retry" if not ungrounded else "failed_fallback"
            else:
                status = "failed_fallback"
        if status == "failed_fallback":
            return Answer(question=run.question, in_scope=in_scope, narrative=None, narrative_status="fallback",
                          notice=("The AI narrative contained numbers the tools did not return, so it is hidden. "
                                  "The evidence below comes straight from the deterministic tools."),
                          results=run.results, key_evidence_ids=key_ids, tool_calls=run.calls, model=run.usage,
                          grounding=grounding.grounding(status, checked, ungrounded), caveats=_caveats(run.results),
                          cannot_tell=_cannot(run.results))
        return Answer(question=run.question, in_scope=in_scope, narrative=narrative, narrative_status="live",
                      results=run.results, key_evidence_ids=key_ids, tool_calls=run.calls, model=run.usage,
                      grounding=grounding.grounding(status, checked, []), caveats=_caveats(run.results),
                      cannot_tell=_cannot(run.results))

    def _retry(self, run: _Run, narrative: str, ungrounded: list[str]) -> tuple[str, list[str], bool] | None:
        evidence = [{"tool": r.tool, "view": r.view, "result": r.model_dump(exclude={"chart"}, mode="json")}
                    for r in run.results]
        items = [
            {"role": "user", "content": run.question},
            {"role": "user", "content": "Tool results (JSON): " + json.dumps(evidence)},
            {"role": "assistant", "content": json.dumps({"narrative": narrative})},
            {"role": "user", "content": RETRY_FEEDBACK.format(numbers=", ".join(ungrounded[:10]))},
        ]
        try:
            parsed = _parse(self._call(run, items, tool_choice=None))
        except Exception as exc:
            log.warning("grounding retry failed", extra={"fields": {"error": type(exc).__name__}})
            return None
        return (str(parsed.get("narrative", "")).strip(), list(parsed.get("key_evidence_ids", [])),
                bool(parsed.get("in_scope", True)))


class _ContentFiltered(Exception):
    code = "content_filter"


def _parse(response: Any) -> dict[str, Any]:
    text = getattr(response, "output_text", "") or ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"narrative": text, "key_evidence_ids": [], "in_scope": True}
    return parsed if isinstance(parsed, dict) else {"narrative": str(parsed), "key_evidence_ids": [], "in_scope": True}


def _caveats(results: list[ToolResult]) -> list[str]:
    seen: list[str] = []
    for r in results:
        for c in r.caveats:
            if c not in seen:
                seen.append(c)
    return seen[:6]


def _cannot(results: list[ToolResult]) -> list[str]:
    seen: list[str] = []
    for r in results:
        if r.cannot_tell and r.cannot_tell not in seen:
            seen.append(r.cannot_tell)
    return seen[:4]
