"""The seven question cards: what each asks, the data and method, what the result
looks like, and why it matters. The numbers on each card come from its tool call."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

from .analytics.registry import QUESTION_MODULES, QUESTIONS, TOOLS
from .reference import get_reference


@dataclass(frozen=True)
class Card:
    number: int
    question: str
    tool: str
    arguments: dict[str, Any]
    asks: str
    data_method: str
    expected: str
    why: str


_TEXT: dict[int, tuple[str, str, str, str]] = {
    1: ("Which national team has been the strongest ever, and how does the answer change with the definition of "
        "best?",
        "Every match since 1872 feeds a transparent Elo-style rating: every team starts equal, home teams get a fixed "
        "advantage, and bigger tournaments and wider margins move ratings more. The card shows each team's peak rating "
        "after its 30th match; ask a question to switch to career average, time at the top, or plain records.",
        "A ranked bar chart of the ten highest peak ratings, with the date each peak was reached.",
        "Best is a definition, not a fact. Showing the lens and its parameters is how an analytics app earns trust."),
    2: ("Who led each era of international football, and by how much?",
        "Six fixed eras from 1872 to today. A team's era rating is the mean of its ratings after each of its matches "
        "in the era, and only teams with enough matches in the era are ranked.",
        "One bar per era showing the leader and its margin over the runner-up.",
        "Dominance is relative to who else was playing; era views show how the balance of power moved over 150 years."),
    3: ("Has playing at home always mattered as much as it does now?",
        "Every non-neutral match, grouped by decade: the share of home wins, draws, and away wins, with a 95% "
        "interval for the home win share. Other views cover goals per match, the spread of team strength, goal "
        "timing, and strength by World Bank region or income group.",
        "Three lines by decade for home wins, draws, and away wins, with an uncertainty band on home wins.",
        "Home advantage is the oldest pattern in the sport. Seeing it across 150 years shows how stable a pattern can "
        "be while the game around it changes completely."),
    4: ("How has the number of teams playing international football changed, and who plays whom?",
        "Distinct teams per year, first appearances by decade, and teams that stopped playing when their state "
        "dissolved, merged, or split. Other views show the most frequent pairings and the fixture network compared "
        "with World Bank regions.",
        "A line of active teams per year, with jumps as new states and football associations join.",
        "Fixture lists are a public trace of how the football world is organized. The patterns are descriptive, not "
        "claims about relations between countries."),
    5: ("Which countries most often host matches between two other teams?",
        "A match counts when the data flags it as neutral and the venue country, reconciled with its former names, is "
        "neither team. The card ranks hosts by such matches; other views show the trend, host cities, and hosts' "
        "World Bank region and income group.",
        "A ranked bar chart of the ten most frequent third-party hosts.",
        "Third-party hosting shows where international football is staged, and it is a clean example of reconciling "
        "historical place names before counting anything."),
    6: ("Do hosts do better at major tournaments than the same teams do when they are not hosting?",
        "Editions of eight major tournaments are rebuilt from match dates, and hosts come from the venue countries, "
        "including co-hosts. Each host's results against rating-based expectations, without the usual home bonus, are "
        "compared with its own editions as a non-host.",
        "A pooled host effect with a 95% interval, plus how much further hosts tend to progress; ask about the 2026 "
        "World Cup to see its three co-hosts.",
        "It turns a familiar belief into a measured comparison, with the uncertainty of small samples shown rather "
        "than hidden."),
    7: ("Who plays the most friendlies, and do teams that play more of them do better in the competitive matches that "
        "follow?",
        "Friendlies plus a reviewed list of invitational tournaments. The card ranks the most active teams; the effect "
        "view compares friendly volume in each four-year window with performance in the next window's competitive "
        "matches.",
        "A ranked bar chart of the most active teams and their share of friendly matches.",
        "It tests a common assumption with the data, and states the limits of observational comparisons up front."),
}


def _cards() -> tuple[Card, ...]:
    cards = []
    for number, module in enumerate(QUESTION_MODULES, start=1):
        asks, data_method, expected, why = _TEXT[number]
        cards.append(Card(number=number, question=QUESTIONS[number], tool=module.TOOL_NAME,
                          arguments=dict(module.CARD_ARGUMENTS), asks=asks, data_method=data_method,
                          expected=expected, why=why))
    return tuple(cards)


CARDS: tuple[Card, ...] = _cards()


def by_number() -> dict[int, Card]:
    return {card.number: card for card in CARDS}


VIEW_LABELS: dict[str, str] = {
    "peak": "Peak rating", "career_average": "Career average rating", "time_at_top": "Time at the top",
    "records": "Win rate and points per match", "wins_per_million": "Wins per million people (novelty)",
    "all": "Leader of every era",
    "home_advantage": "Home advantage", "goals_per_match": "Goals per match",
    "strength_spread": "Spread of team strength",
    "goal_timing": "Goal timing and penalties", "strength_by_region": "Strength by World Bank region",
    "strength_by_income": "Strength by World Bank income group",
    "team_counts": "How the number of teams changed", "frequent_pairings": "Most frequent pairings",
    "communities": "Fixture-network communities", "region_mixing": "Matches within and across regions",
    "ranking": "Top third-party hosts", "trend": "Third-party share by decade", "cities": "Top host cities",
    "host_groups": "Hosts by region and income group",
    "pooled": "Pooled host effect", "by_tournament": "Host effect by tournament",
    "edition": "Hosts of the latest FIFA World Cup", "gdp_split": "Host effect by host GDP per capita",
    "leaders": "Most active teams", "effect": "Friendlies and later competitive results",
    "by_income": "Friendlies by income group",
}
# Views that use the World Bank development indicators.
DEVELOPMENT_LENS = frozenset({"wins_per_million", "strength_by_region", "strength_by_income", "communities",
                              "region_mixing", "host_groups", "gdp_split", "by_income"})


@dataclass(frozen=True)
class View:
    label: str
    arguments: dict[str, Any]


def views(card: Card) -> tuple[View, ...]:
    """The card's views: each value of its tool's main choice, with optional filters left open.

    The web page offers exactly these, by index, so a visitor can switch views without the model and without
    sending free-form tool arguments.
    """
    eras = {era.id: era.label for era in get_reference().eras}
    options: dict[str, list[Any]] = {}
    for field, spec in TOOLS[card.tool].params.model_json_schema().get("properties", {}).items():
        variants = spec.get("anyOf", [spec])
        if any(variant.get("type") == "null" for variant in variants):
            options[field] = [None]
        else:
            options[field] = [value for variant in variants for value in variant.get("enum", [])]
    out = []
    for combo in itertools.product(*options.values()):
        choice = next(value for value in combo if value is not None)
        label = eras.get(choice) or VIEW_LABELS.get(choice, str(choice).replace("_", " ").capitalize())
        if choice in DEVELOPMENT_LENS:
            label += " (development lens)"
        out.append(View(label=label, arguments=dict(zip(options, combo, strict=True))))
    return tuple(out)


def default_view(card: Card) -> int:
    choices = views(card)
    return next((i for i, view in enumerate(choices) if view.arguments == card.arguments), 0)
