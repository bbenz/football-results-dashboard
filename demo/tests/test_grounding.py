"""The grounding validator on hand-written narratives."""

from __future__ import annotations

from football_insights.agent.grounding import check, extract_numbers
from football_insights.schemas import Fact, Table, ToolResult


def result(**overrides: object) -> ToolResult:
    base: dict[str, object] = dict(
        tool="trends", question=3, view="home_advantage", params={"metric": "home_advantage"}, title="t",
        headline="Home teams won 44.4% in the 1900s and 51.0% in the 2020s.",
        facts=[Fact(id="q3.home.1900s.home_win_pct", label="Home win share, 1900s", value=44.4, unit="%", decimals=1),
               Fact(id="q3.home.change_pts", label="Change", value=-6.6, unit="percentage points", decimals=1),
               Fact(id="q3.home.matches", label="Matches", value=36263, unit="matches"),
               Fact(id="x.population", label="Population", value=1712345.0)],
        table=Table(columns=["Era", "Leader rating"], rows=[["1946–1969", 2061], ["1970–1989", 2044]]),
        method="m", method_version="v1", dataset_version="cv-3fb8fad447eb")
    base.update(overrides)
    return ToolResult.model_validate(base)


def test_extracts_percent_thousands_decades_ordinals_and_scale() -> None:
    numbers = {n.text: (n.value, n.decimals, n.ordinal) for n in extract_numbers(
        "In the 1950s, 44.4% of 36,263 matches; Brazil ranked 1st; about 1.7 million people; it fell by -6.6.")}
    assert numbers["1950s"] == (1950.0, 0, False)
    assert numbers["44.4"] == (44.4, 1, False)
    assert numbers["36,263"] == (36263.0, 0, False)
    assert numbers["1st"] == (1.0, 0, True)
    assert numbers["1.7 million"] == (1_700_000.0, 1, False)
    assert numbers["-6.6"] == (-6.6, 1, False)


def test_version_strings_ids_and_names_are_not_numbers() -> None:
    assert extract_numbers("version 1.19.0 and q3.home.1900s.home_win_pct and Q3") == []


def test_grounded_narrative_passes_with_rounding_and_signs() -> None:
    narrative = ("Home teams won 44% of 36,263 non-neutral matches in the 1900s; the share changed by 6.6 points. "
                 "Leaders in 1946–1969 rated 2061, and about 1.7 million people live there.")
    checked, ungrounded = check(narrative, [result()])
    assert ungrounded == []
    assert checked >= 7


def test_invented_numbers_are_caught() -> None:
    _, ungrounded = check("Home teams won 58% of matches in 1990 and scored 3.1 goals.", [result()])
    assert set(ungrounded) == {"58", "1990", "3.1"}


def test_numbers_from_the_question_and_small_ordinals_are_exempt() -> None:
    _, ungrounded = check("Among the top 5 teams, Avalon is 2nd.", [result()], question="Show the top 5 teams")
    assert ungrounded == []


def test_no_results_means_every_number_is_ungrounded() -> None:
    _, ungrounded = check("Brazil won 63.4% of matches.", [])
    assert ungrounded == ["63.4"]
