"""The evaluation suite: case coverage, scoring, framing checks, and the decision rule."""

from __future__ import annotations

from collections import Counter

from football_insights import evaluation
from football_insights.analytics.context import ToolContext
from football_insights.analytics.registry import TOOLS, run_tool
from football_insights.schemas import Answer, Grounding, ModelUsage, ToolCallRecord
from helpers import M, make_store


def test_cases_cover_every_question_and_category_with_valid_tool_arguments() -> None:
    cases = evaluation.load_cases()
    counts = Counter(c.category for c in cases)
    assert all(counts[f"q{n}"] >= 3 for n in range(1, 8)), counts
    assert counts["limitation"] >= 4 and counts["framing"] >= 3
    assert len({c.id for c in cases}) == len(cases)
    for case in cases:
        for want in case.expect_tools:
            spec = TOOLS[want["tool"]]
            props = spec.params.model_json_schema().get("properties", {})
            for key, value in (want.get("args") or {}).items():
                assert key in props, f"{case.id}: {key} is not a parameter of {spec.name}"
                options = [o for variant in props[key].get("anyOf", [props[key]]) for o in variant.get("enum", [])]
                assert not options or value in options, f"{case.id}: {value!r} not allowed for {key}"
    assert sum(c.capture for c in cases) >= 4


def answer(question: str, tools: list[tuple[str, dict[str, object]]], narrative: str = "Grounded words.",
           status: str = "live", grounding: str = "passed", in_scope: bool = True, cost: float = 0.01) -> Answer:
    return Answer(question=question, narrative=narrative, narrative_status=status, in_scope=in_scope,  # type: ignore[arg-type]
                  tool_calls=[ToolCallRecord(name=n, arguments=a) for n, a in tools],
                  grounding=Grounding(status=grounding),  # type: ignore[arg-type]
                  model=ModelUsage(deployment="d", latency_ms=1500, input_tokens=1000, output_tokens=100,
                                   estimated_cost_usd=cost))


def test_scoring_tool_scope_framing_and_facts() -> None:
    peak = next(c for c in evaluation.load_cases() if c.id == "q1-peak")
    ok = evaluation.score(peak, answer(peak.question, [("best_team", {"lens": "peak"})], "Avalon peaked at 1,612."),
                          "d", 1, 2.0, {"fact": 1612.4, "top": ["Avalon"], "dataset_version": "cv-x"})
    assert ok.tool_ok and ok.grounding_ok and ok.live and ok.framing_ok and ok.fact_ok and ok.top_ok
    wrong = evaluation.score(peak, answer(peak.question, [("best_team", {"lens": "records"})]), "d", 1, 2.0, {})
    assert not wrong.tool_ok
    lim = next(c for c in evaluation.load_cases() if c.id == "lim-prediction")
    honest = evaluation.score(lim, answer(lim.question, [("data_limits", {"topic": "predictions_betting"})],
                                          in_scope=False), "d", 1, 1.0, {})
    assert honest.scope_ok and honest.tool_ok
    frame = next(c for c in evaluation.load_cases() if c.id == "frame-poor")
    bad = evaluation.score(frame, answer(frame.question, [("trends", {"metric": "strength_by_income"})],
                                         "They lose because they are poor."), "d", 1, 1.0, {})
    assert not bad.framing_ok and bad.notes


def test_decision_rule_prefers_cheaper_unless_clearly_more_accurate() -> None:
    base = {"grounding_pass_rate": 1.0, "limitation_accuracy": 1.0, "framing_pass_rate": 1.0, "live_rate": 1.0,
            "filtered": 0, "p95_seconds": 10.0}
    close = {"astra": {**base, "tool_selection_accuracy": 0.97, "mean_cost_usd": 0.2},
             "sol": {**base, "tool_selection_accuracy": 0.94, "mean_cost_usd": 0.04}}
    assert evaluation.decide(close)["choice"] == "sol"
    clear = {"astra": {**base, "tool_selection_accuracy": 1.0, "mean_cost_usd": 0.2},
             "sol": {**base, "tool_selection_accuracy": 0.9, "mean_cost_usd": 0.04}}
    assert evaluation.decide(clear)["choice"] == "astra"
    slow = {"astra": {**base, "tool_selection_accuracy": 1.0, "mean_cost_usd": 0.2, "p95_seconds": 40.0},
            "sol": {**base, "tool_selection_accuracy": 0.8, "mean_cost_usd": 0.04}}
    assert evaluation.decide(slow)["choice"] is None


def test_run_computes_expectations_with_the_deterministic_tools() -> None:
    ctx = ToolContext(make_store([M(f"19{50 + i}-01-01", "Avalon", "Borealis", 3, 0) for i in range(40)]))
    case = evaluation.Case(id="t", category="q1", question="Who peaked highest?",
                           expect_tools=({"tool": "best_team", "args": {"lens": "peak"}},), expect_top=True)
    expected = evaluation.expectations(case, lambda n, a: run_tool(ctx, n, a))
    assert expected["top"] == ["Avalon"]

    def ask(question: str, deployment: str) -> Answer:
        return answer(question, [("best_team", {"lens": "peak"})], "Avalon has the highest peak.")

    results = evaluation.run([case], ask, ["sol", "astra"], repeats=2, run_tool=lambda n, a: run_tool(ctx, n, a))
    summary = evaluation.summarize(results)
    assert set(summary["deployments"]) == {"astra", "sol"}
    assert summary["deployments"]["sol"]["answers"] == 2
    assert summary["deployments"]["sol"]["top_entity_accuracy"] == 1.0
    assert "Decision rule" in evaluation.render(summary)
