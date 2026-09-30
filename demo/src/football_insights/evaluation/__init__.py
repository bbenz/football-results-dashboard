"""Evaluation suite for the insights agent.

Runs hand-authored cases (cases.yaml) against one or more model deployments,
several times each because model output varies, and scores every answer on:
tool selection, grounding, live narrative, honest limitations, responsible
framing, and facts computed by the deterministic tools at run time. It reports
p50/p95 latency, tokens, and estimated cost per answer, and applies the model
decision rule below. Results are metrics only; answers are not stored unless
you capture them as labeled cached narratives.
"""

from __future__ import annotations

import json
import re
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from ..schemas import Answer

CASES_PATH = Path(__file__).parent / "cases.yaml"

# Decision rule (proposed; the presenter agrees it before the evaluation picks the livestream deployment).
GATES = {"grounding_pass_rate": 0.95, "tool_selection_accuracy": 0.90, "limitation_accuracy": 1.0,
         "framing_pass_rate": 1.0, "live_rate": 0.95}
MAX_P95_SECONDS = 25.0
ACCURACY_MARGIN = 0.05

# Value-laden or causal wording about countries and development that the framing check rejects.
FRAMING = re.compile(
    r"\b(inferior|superior|backward|uncivili[sz]ed|primitive|hate[sd]?|hatred|enem(y|ies)|deserve[sd]?|"
    r"better people|worse people|shameful)\b"
    r"|\b(because|due to|caused by|thanks to|as a result of)\b[^.]{0,40}\b(wealth|rich|poor|poverty|income|gdp|"
    r"development|developed)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    question: str
    expect_tools: tuple[dict[str, Any], ...]
    expect_in_scope: bool | None = None
    expect_fact: str | None = None
    expect_top: bool = False
    capture: bool = False


@dataclass
class CaseResult:
    case_id: str
    category: str
    deployment: str
    repeat: int
    narrative_status: str
    grounding: str
    tool_ok: bool
    grounding_ok: bool
    live: bool
    scope_ok: bool | None
    framing_ok: bool
    fact_ok: bool | None
    top_ok: bool | None
    wall_seconds: float
    model_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tools: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def load_cases(path: Path = CASES_PATH) -> list[Case]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Case(id=c["id"], category=c["category"], question=c["question"],
                 expect_tools=tuple(c["expect_tools"]), expect_in_scope=c.get("expect_in_scope"),
                 expect_fact=c.get("expect_fact"), expect_top=bool(c.get("expect_top", False)),
                 capture=bool(c.get("capture", False))) for c in data["cases"]]


def _tool_matches(answer: Answer, expected: tuple[dict[str, Any], ...]) -> bool:
    for want in expected:
        for call in answer.tool_calls:
            if call.ok and call.name == want["tool"] and all(
                    call.arguments.get(k) == v for k, v in (want.get("args") or {}).items()):
                return True
    return False


def expectations(case: Case, run_tool: Callable[[str, dict[str, Any]], Any] | None) -> dict[str, Any]:
    """Facts the narrative must state, computed by the deterministic tool now (never stored in cases.yaml)."""
    if run_tool is None or not (case.expect_fact or case.expect_top):
        return {}
    want = case.expect_tools[0]
    from ..analytics.registry import TOOLS

    fields = TOOLS[want["tool"]].params.model_fields
    args = {name: (want.get("args") or {}).get(name) for name in fields}
    result = run_tool(want["tool"], args)
    out: dict[str, Any] = {"dataset_version": result.dataset_version}
    if case.expect_fact:
        fact = next((f for f in result.facts if f.id == case.expect_fact), None)
        out["fact"] = fact.value if fact else None
    if case.expect_top and result.chart and result.chart.x:
        label = result.chart.x[0].split(": ")[-1]
        out["top"] = [part.strip() for part in label.split(" v ")]
    return out


def score(case: Case, answer: Answer, deployment: str, repeat: int, wall_seconds: float,
          expected: dict[str, Any]) -> CaseResult:
    from ..agent.grounding import AllowedNumbers, extract_numbers

    narrative = answer.narrative or ""
    notes: list[str] = []
    live = answer.narrative_status == "live"
    grounding_ok = live and answer.grounding.status in ("passed", "passed_after_retry")
    scope_ok = None
    if case.expect_in_scope is not None:
        scope_ok = answer.in_scope == case.expect_in_scope
    flagged = FRAMING.search(narrative)
    framing_ok = answer.narrative_status != "filtered" and not flagged
    if flagged:
        notes.append("framing: " + flagged.group(0))
    fact_ok = top_ok = None
    answer_version = answer.results[0].dataset_version if answer.results else None
    same_data = not expected or answer_version is None or expected.get("dataset_version") == answer_version
    if not same_data:
        notes.append("fact checks skipped: the answer used a different dataset version")
    elif "fact" in expected:
        allowed = AllowedNumbers()
        if expected["fact"] is not None:
            allowed.add(float(expected["fact"]))
        fact_ok = any(allowed.matches(n) for n in extract_numbers(narrative))
    if same_data and "top" in expected:
        top_ok = all(name.lower() in narrative.lower() for name in expected["top"])
    model = answer.model
    return CaseResult(
        case_id=case.id, category=case.category, deployment=deployment, repeat=repeat,
        narrative_status=answer.narrative_status, grounding=answer.grounding.status,
        tool_ok=_tool_matches(answer, case.expect_tools), grounding_ok=grounding_ok, live=live, scope_ok=scope_ok,
        framing_ok=framing_ok, fact_ok=fact_ok, top_ok=top_ok, wall_seconds=round(wall_seconds, 2),
        model_ms=model.latency_ms if model else 0.0, input_tokens=model.input_tokens if model else 0,
        output_tokens=model.output_tokens if model else 0, cost_usd=model.estimated_cost_usd if model else 0.0,
        tools=[c.name for c in answer.tool_calls], notes=notes)


def _rate(values: list[bool | None]) -> float | None:
    known = [v for v in values if v is not None]
    return round(sum(known) / len(known), 3) if known else None


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, max(0, round(q / 100 * (len(ordered) - 1))))], 2)


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    by_deployment: dict[str, dict[str, Any]] = {}
    for deployment in sorted({r.deployment for r in results}):
        rs = [r for r in results if r.deployment == deployment]
        limitation = [r for r in rs if r.category == "limitation"]
        walls = [r.wall_seconds for r in rs]
        by_deployment[deployment] = {
            "answers": len(rs),
            "grounding_pass_rate": _rate([r.grounding_ok for r in rs]),
            "tool_selection_accuracy": _rate([r.tool_ok for r in rs]),
            "limitation_accuracy": _rate([bool(r.scope_ok) and r.tool_ok for r in limitation]),
            "framing_pass_rate": _rate([r.framing_ok for r in rs]),
            "live_rate": _rate([r.live for r in rs]),
            "fact_accuracy": _rate([r.fact_ok for r in rs]),
            "top_entity_accuracy": _rate([r.top_ok for r in rs]),
            "filtered": sum(r.narrative_status == "filtered" for r in rs),
            "p50_seconds": _pct(walls, 50),
            "p95_seconds": _pct(walls, 95),
            "mean_input_tokens": round(statistics.mean(r.input_tokens for r in rs)) if rs else 0,
            "mean_output_tokens": round(statistics.mean(r.output_tokens for r in rs)) if rs else 0,
            "mean_cost_usd": round(statistics.mean(r.cost_usd for r in rs), 5) if rs else 0.0,
            "total_cost_usd": round(sum(r.cost_usd for r in rs), 4),
        }
    return {"deployments": by_deployment, "decision": decide(by_deployment)}


def decide(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    eligible, reasons = [], {}
    for name, m in metrics.items():
        failed = [f"{k} {m.get(k)} < {v}" for k, v in GATES.items() if (m.get(k) or 0) < v]
        if m.get("filtered"):
            failed.append(f"{m['filtered']} answers blocked by content filtering")
        if m.get("p95_seconds", 0) > MAX_P95_SECONDS:
            failed.append(f"p95 {m['p95_seconds']} s > {MAX_P95_SECONDS} s")
        reasons[name] = failed or ["meets every gate"]
        if not failed:
            eligible.append(name)
    if not eligible:
        return {"choice": None, "reasons": reasons, "rule": "no deployment met the gates"}
    cheapest = min(eligible, key=lambda n: (metrics[n]["mean_cost_usd"], n))
    best = max(eligible, key=lambda n: (metrics[n]["tool_selection_accuracy"] or 0, -metrics[n]["mean_cost_usd"]))
    margin = (metrics[best]["tool_selection_accuracy"] or 0) - (metrics[cheapest]["tool_selection_accuracy"] or 0)
    choice = best if margin >= ACCURACY_MARGIN else cheapest
    return {"choice": choice, "reasons": reasons,
            "rule": (f"eligible deployments meet all gates and p95 <= {MAX_P95_SECONDS} s; choose the cheaper unless "
                     f"another is at least {ACCURACY_MARGIN:.0%} more accurate at tool selection")}


def run(cases: list[Case], ask: Callable[[str, str], Answer], deployments: list[str], repeats: int,
        run_tool: Callable[[str, dict[str, Any]], Any] | None = None,
        on_result: Callable[[CaseResult], None] | None = None) -> list[CaseResult]:
    results = []
    expected = {case.id: expectations(case, run_tool) for case in cases}
    for repeat in range(1, repeats + 1):
        for deployment in deployments:
            for case in cases:
                start = time.perf_counter()
                answer = ask(case.question, deployment)
                result = score(case, answer, deployment, repeat, time.perf_counter() - start, expected[case.id])
                results.append(result)
                if on_result:
                    on_result(result)
    return results


def write_report(results: list[CaseResult], summary: dict[str, Any], out_dir: Path, label: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"eval-{stamp}-{label}.json"
    path.write_text(json.dumps({"summary": summary, "results": [asdict(r) for r in results]}, indent=2),
                    encoding="utf-8")
    return path


def render(summary: dict[str, Any]) -> str:
    rows = ["| Metric | " + " | ".join(summary["deployments"]) + " |",
            "| --- | " + " | ".join("---" for _ in summary["deployments"]) + " |"]
    metrics = next(iter(summary["deployments"].values())).keys() if summary["deployments"] else []
    for metric in metrics:
        rows.append(f"| {metric} | " + " | ".join(str(m[metric]) for m in summary["deployments"].values()) + " |")
    decision = summary["decision"]
    rows.append("")
    rows.append(f"Decision rule: {decision['rule']}. Choice: {decision['choice'] or 'none'}.")
    for name, why in decision["reasons"].items():
        rows.append(f"- {name}: {'; '.join(why)}")
    return "\n".join(rows)
