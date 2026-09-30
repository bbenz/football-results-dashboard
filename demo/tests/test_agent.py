"""The insights agent against scripted model responses (replays, not live model output)."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import make_settings
from fake_responses import ContentFilterError, FakeClient, answer, tool_calls
from football_insights.agent import narratives
from football_insights.agent.loop import InsightsAgent, QuestionRejected
from football_insights.analytics.context import ToolContext
from football_insights.analytics.registry import run_tool
from helpers import M, make_store

pytestmark = pytest.mark.replay


@pytest.fixture
def ctx() -> ToolContext:
    # Three home wins and one draw per decade in the 1950s and 1960s (min_matches is 100 for the card, so the tool
    # uses the real threshold only where a test calls the registry; these tests read facts from the result).
    matches = [M(f"19{d}{i}-05-01", "Avalon", "Borealis", 2 if i < 3 else 1, 0 if i < 3 else 1)
               for d in (5, 6) for i in range(4)]
    return ToolContext(make_store(matches))


def make_agent(ctx: ToolContext, script: list[object], tmp_path: Path, **settings: object) -> tuple[InsightsAgent,
                                                                                                    FakeClient]:
    client = FakeClient(script)
    config = make_settings(foundry_project_endpoint="https://example.invalid/api/projects/p",
                           narrative_cache_dir=tmp_path / "narratives", **settings)
    agent = InsightsAgent(config, lambda name, args: (run_tool(ctx, name, args), 1.0), client_factory=lambda: client)
    return agent, client


def facts_of(ctx: ToolContext) -> dict[str, float]:
    result = run_tool(ctx, "dataset_facts", {})
    return {f.id: f.value for f in result.facts}


def test_live_answer_with_grounded_numbers(ctx: ToolContext, tmp_path: Path) -> None:
    f = facts_of(ctx)
    agent, client = make_agent(ctx, [
        tool_calls(("dataset_facts", {})),
        answer(f"The data holds {int(f['scope.matches'])} matches between {int(f['scope.teams'])} teams.",
               ["scope.matches", "not.a.real.id"]),
    ], tmp_path)
    result = agent.answer("How many matches are in the data?")
    assert result.narrative_status == "live"
    assert result.grounding.status == "passed"
    assert result.key_evidence_ids == ["scope.matches"]
    assert [c.name for c in result.tool_calls] == ["dataset_facts"]
    assert result.model is not None and result.model.calls == 2
    assert result.model.input_tokens == 1800 and result.model.output_tokens == 250
    assert result.model.estimated_cost_usd == pytest.approx((1800 * 10 + 250 * 50) / 1e6)
    first = client.responses.requests[0]
    assert first["model"] == "gpt-6-astra" and first["store"] is False
    assert first["tool_choice"] == "auto" and {t["name"] for t in first["tools"]} >= {"trends", "data_limits"}
    assert any(i.get("type") == "function_call_output" for i in client.responses.requests[1]["input"])


def test_ungrounded_number_is_retried_then_passes(ctx: ToolContext, tmp_path: Path) -> None:
    f = facts_of(ctx)
    agent, client = make_agent(ctx, [
        tool_calls(("dataset_facts", {})),
        answer("The data holds 99999 matches."),
        answer(f"The data holds {int(f['scope.matches'])} matches."),
    ], tmp_path)
    result = agent.answer("How many matches?")
    assert result.narrative_status == "live"
    assert result.grounding.status == "passed_after_retry"
    retry = client.responses.requests[-1]
    assert "tools" not in retry and "99999" in retry["input"][-1]["content"]


def test_persistently_ungrounded_narrative_falls_back_to_evidence(ctx: ToolContext, tmp_path: Path) -> None:
    agent, _ = make_agent(ctx, [tool_calls(("dataset_facts", {})), answer("It holds 99999 matches."),
                                answer("It holds 88888 matches.")], tmp_path)
    result = agent.answer("How many matches?")
    assert result.narrative is None
    assert result.narrative_status == "fallback"
    assert result.grounding.status == "failed_fallback"
    assert result.grounding.ungrounded == ["88888"]
    assert result.results and result.notice


def test_out_of_scope_question_gets_an_honest_limitation(ctx: ToolContext, tmp_path: Path) -> None:
    agent, _ = make_agent(ctx, [
        tool_calls(("data_limits", {"topic": "club_football"})),
        answer("This data covers national teams only, so it cannot compare Premier League clubs.", in_scope=False),
    ], tmp_path)
    result = agent.answer("Which Premier League club counterattacks best?")
    assert result.in_scope is False
    assert result.narrative_status == "live"
    assert result.results[0].tool == "data_limits"
    assert any("Club match results" in c for c in result.caveats)


def test_content_filter_is_handled(ctx: ToolContext, tmp_path: Path) -> None:
    agent, _ = make_agent(ctx, [ContentFilterError("blocked")], tmp_path)
    result = agent.answer("something the filter blocks")
    assert result.narrative_status == "filtered"
    assert result.narrative is None and "content filtering" in (result.notice or "")


def test_model_outage_is_visible_and_serves_labeled_cache(ctx: ToolContext, tmp_path: Path) -> None:
    agent, _ = make_agent(ctx, [ConnectionError("down")], tmp_path)
    result = agent.answer("How many matches?")
    assert result.narrative_status == "unavailable" and "ConnectionError" in (result.notice or "")
    cached = result.model_copy(update={"narrative": "Cached words.", "narrative_status": "live"})
    narratives.save(tmp_path / "narratives", cached, "2026-10-07T10:00:00Z")
    agent2, _ = make_agent(ctx, [ConnectionError("down")], tmp_path)
    again = agent2.answer("  how many   MATCHES? ")
    assert again.narrative_status == "cached" and again.cached_at == "2026-10-07T10:00:00Z"
    assert "cached narrative" in (again.notice or "")


def test_tool_call_limit_forces_an_answer(ctx: ToolContext, tmp_path: Path) -> None:
    script = [tool_calls(("dataset_facts", {}), ("dataset_facts", {})), tool_calls(("dataset_facts", {})),
              answer("Done.")]
    agent, client = make_agent(ctx, script, tmp_path, ai_max_tool_calls=2)
    result = agent.answer("Loop please")
    assert [c.ok for c in result.tool_calls] == [True, True, False]
    assert client.responses.requests[-1]["tool_choice"] == "none"
    assert result.narrative_status == "live"


def test_invalid_tool_arguments_are_reported_to_the_model(ctx: ToolContext, tmp_path: Path) -> None:
    agent, client = make_agent(ctx, [tool_calls(("trends", {"metric": "possession"})),
                                     tool_calls(("dataset_facts", {})), answer("Covered.")], tmp_path)
    result = agent.answer("Possession trends?")
    assert result.tool_calls[0].ok is False and "invalid arguments" in (result.tool_calls[0].error or "")
    outputs = [i for i in client.responses.requests[1]["input"] if i.get("type") == "function_call_output"]
    assert "error" in outputs[0]["output"]


def test_answer_without_tools_is_hidden(ctx: ToolContext, tmp_path: Path) -> None:
    agent, _ = make_agent(ctx, [answer("Brazil, obviously.")], tmp_path)
    result = agent.answer("Who is best?")
    assert result.narrative is None and result.narrative_status == "fallback"
    assert "without consulting" in (result.notice or "")


def test_bounds_and_modes(ctx: ToolContext, tmp_path: Path) -> None:
    agent, client = make_agent(ctx, [], tmp_path, question_max_chars=20)
    with pytest.raises(QuestionRejected):
        agent.answer("x" * 21)
    with pytest.raises(QuestionRejected):
        agent.answer("   ")
    with pytest.raises(QuestionRejected):
        agent.answer("Who is best?", deployment="gpt-6.1-sol")
    off, _ = make_agent(ctx, [], tmp_path, ai_narrative_mode="off")
    assert off.answer("Who is best?").narrative_status == "unavailable"
    cached, _ = make_agent(ctx, [], tmp_path, ai_narrative_mode="cached")
    assert cached.answer("Never asked before").narrative_status == "unavailable"
    assert client.responses.requests == []
