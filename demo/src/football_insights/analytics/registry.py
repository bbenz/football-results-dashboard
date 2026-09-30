"""The typed, read-only tools the insights agent may call.

Each tool validates its arguments against a strict schema, runs deterministic
SQL and Python over the curated store, and returns a bounded ToolResult.
Results are cached per curated version, so repeated calls return identical
numbers.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import ToolResult
from . import q3_trends
from .context import ToolContext


class TrendsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: Literal["home_advantage", "goals_per_match"] = Field(
        description="home_advantage: home win/draw/away win shares per decade in non-neutral matches. "
                    "goals_per_match: average total goals per match per decade.")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    question: int
    description: str
    params: type[BaseModel]
    func: Callable[[ToolContext, BaseModel], ToolResult]


TOOLS: dict[str, ToolSpec] = {
    "trends": ToolSpec(
        name="trends",
        question=3,
        description=("Question 3, trends in international football throughout the ages. "
                     "Returns per-decade figures for one metric, with coverage and caveats."),
        params=TrendsParams,
        func=lambda ctx, p: q3_trends.run(ctx, p.metric),  # type: ignore[attr-defined]
    ),
}


class ToolError(ValueError):
    pass


def run_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> ToolResult:
    spec = TOOLS.get(name)
    if spec is None:
        raise ToolError(f"unknown tool {name!r}")
    try:
        params = spec.params.model_validate(arguments)
    except Exception as exc:
        raise ToolError(f"invalid arguments for {name}: {exc}") from exc
    key = f"{ctx.dataset_version}:{name}:{json.dumps(params.model_dump(), sort_keys=True)}"
    cached = ctx.cache.get(key)
    if cached is not None:
        return cached
    result = spec.func(ctx, params)
    ctx.cache[key] = result
    return result


def timed_run(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> tuple[ToolResult, float]:
    start = time.perf_counter()
    result = run_tool(ctx, name, arguments)
    return result, (time.perf_counter() - start) * 1000


def _strict(schema: dict[str, Any]) -> dict[str, Any]:
    """Shape a pydantic schema for strict function calling: no titles, all properties required."""
    out = {k: v for k, v in schema.items() if k not in ("title", "default")}
    if out.get("type") == "object":
        props = {k: _strict(v) for k, v in out.get("properties", {}).items()}
        out["properties"] = props
        out["required"] = list(props)
        out["additionalProperties"] = False
    if "anyOf" in out:
        out["anyOf"] = [_strict(s) for s in out["anyOf"]]
    return out


def function_tools(names: list[str] | None = None) -> list[dict[str, Any]]:
    """Tool definitions for the Responses API."""
    tools = []
    for spec in TOOLS.values():
        if names and spec.name not in names:
            continue
        tools.append({
            "type": "function",
            "name": spec.name,
            "description": spec.description,
            "parameters": _strict(spec.params.model_json_schema()),
            "strict": True,
        })
    return tools
