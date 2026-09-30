"""The typed, read-only tools the insights agent may call.

Each question module exposes TOOL_NAME, DESCRIPTION, a strict Params model, and
run(ctx, params). Every tool validates its arguments, runs deterministic SQL
and Python over the curated store, and returns a bounded ToolResult. Results
are cached per curated version, so repeated calls return identical numbers.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from pydantic import BaseModel

from ..schemas import ToolResult
from . import q1_best, q2_eras, q3_trends, q4_geopolitics, q5_hosts, q6_hosting, q7_friendlies, scope
from .context import ToolContext

QUESTION_MODULES: tuple[ModuleType, ...] = (q1_best, q2_eras, q3_trends, q4_geopolitics, q5_hosts, q6_hosting,
                                            q7_friendlies)
QUESTIONS: dict[int, str] = {
    1: "Who is the best team of all time",
    2: "Which teams dominated different eras of football",
    3: ("What trends have there been in international football throughout the ages - home advantage, total goals "
        "scored, distribution of teams' strength etc"),
    4: ("Can we say anything about geopolitics from football fixtures - how has the number of countries changed, "
        "which teams like to play each other"),
    5: "Which countries host the most matches where they themselves are not participating in",
    6: "How much, if at all, does hosting a major tournament help a country's chances in the tournament",
    7: ("Which teams are the most active in playing friendlies and friendly tournaments - does it help or hurt "
        "them"),
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    question: int
    description: str
    params: type[BaseModel]
    func: Callable[[ToolContext, Any], ToolResult]


def _era_legend() -> str:
    from ..reference import get_reference

    return "Era ids: " + "; ".join(f"{e.id} = {e.label}" for e in get_reference().eras) + "."


def _build() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}
    legend = _era_legend()
    for number, module in enumerate(QUESTION_MODULES, start=1):
        description = f"Answers question {number}: \"{QUESTIONS[number]}\". {module.DESCRIPTION}"
        if "era" in module.Params.model_fields:
            description += " " + legend
        tools[module.TOOL_NAME] = ToolSpec(name=module.TOOL_NAME, question=number, description=description,
                                           params=module.Params, func=module.run)
    tools["data_limits"] = ToolSpec(
        name="data_limits", question=0,
        description=("Call this when the question asks about something the data cannot answer: club football "
                     "(for example the Premier League), women's football, tactics or play styles such as possession "
                     "or counterattacks, player statistics, predictions or betting, or dates outside the data. "
                     "Returns what the data covers and what data would be needed."),
        params=scope.LimitsParams, func=scope.data_limits)
    tools["dataset_facts"] = ToolSpec(
        name="dataset_facts", question=0,
        description="Returns an overview of the loaded data: matches, date range, teams, tournaments, and coverage.",
        params=scope.FactsParams, func=scope.dataset_facts)
    return tools


TOOLS: dict[str, ToolSpec] = _build()


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


def _strict(schema: dict[str, Any]) -> dict[str, Any]:
    """Shape a pydantic schema for strict function calling: inline refs, no titles, all properties required."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            out = {k: walk(v) for k, v in node.items() if k not in ("title", "default", "$defs")}
            if out.get("type") == "object":
                props = out.get("properties", {})
                out["properties"] = props
                out["required"] = list(props)
                out["additionalProperties"] = False
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


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
