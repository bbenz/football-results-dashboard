"""Live checks against the Microsoft Foundry model deployments, marked `live`.

They skip unless FOUNDRY_PROJECT_ENDPOINT is set and the real data is downloaded, and they call the models with
your own Azure sign-in (`az login`), so each run costs a little. They check what the phase gates need from a
live model: every question answered live by every allowed deployment, each answer grounded, the out-of-scope
question honestly limited, and repeated answers citing identical numbers. The full, repeated evaluation with
the decision rule is `demo eval`.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from conftest import REAL_DATA, make_settings, requires_real_data
from football_insights import evaluation
from football_insights.analytics.context import ToolContext
from football_insights.analytics.registry import run_tool
from football_insights.schemas import Answer

pytestmark = [
    pytest.mark.live,
    requires_real_data,
    pytest.mark.skipif(not os.environ.get("FOUNDRY_PROJECT_ENDPOINT"),
                       reason="set FOUNDRY_PROJECT_ENDPOINT and sign in with az login to call the live models"),
]

# The first case of each question plus one the data can't answer.
CATEGORIES = ("q1", "q2", "q3", "q4", "q5", "q6", "q7", "limitation")


@pytest.fixture(scope="module")
def live(tmp_path_factory):  # type: ignore[no-untyped-def]
    from football_insights.agent.loop import InsightsAgent
    from football_insights.ingest.pipeline import run
    from football_insights.ingest.storage import LocalCuratedStorage, LocalRawSource
    from football_insights.store import load

    root = tmp_path_factory.mktemp("live")
    run(LocalRawSource(REAL_DATA), LocalCuratedStorage(root / "curated"), platform="Test")
    settings = make_settings(curated_dir=root / "curated", narrative_cache_dir=root / "narratives",
                             ai_narrative_mode="live")
    ctx = ToolContext(load(settings, cache_dir=root / "cache"))
    agent = InsightsAgent(settings, lambda name, args: (run_tool(ctx, name, args), 0.0))
    return settings, ctx, agent


def test_each_question_is_answered_live_and_grounded_on_every_deployment(live) -> None:  # type: ignore[no-untyped-def]
    settings, ctx, agent = live
    cases = [next(c for c in evaluation.load_cases() if c.category == category) for category in CATEGORIES]
    results = evaluation.run(cases, agent.answer, settings.allowed_deployments, repeats=1,
                             run_tool=lambda name, args: run_tool(ctx, name, args))
    problems = [f"{r.deployment} {r.case_id}: status={r.narrative_status} grounding={r.grounding} tools={r.tools} "
                f"notes={r.notes}"
                for r in results
                if not (r.live and r.grounding_ok and r.tool_ok and r.framing_ok and r.scope_ok is not False)]
    assert not problems, "\n".join(problems)


def facts(answer: Answer) -> dict[str, Any]:
    return {fact.id: fact.value for result in answer.results for fact in result.facts}


def test_repeated_answers_cite_identical_numbers(live) -> None:  # type: ignore[no-untyped-def]
    settings, _, agent = live
    question = next(c for c in evaluation.load_cases() if c.id == "q6-2026").question
    first, second = (agent.answer(question, settings.ai_model_deployment) for _ in range(2))
    assert first.narrative_status == second.narrative_status == "live"
    shared = facts(first).keys() & facts(second).keys()
    assert shared, "the two answers used no tool results in common"
    assert {key: facts(first)[key] for key in shared} == {key: facts(second)[key] for key in shared}
