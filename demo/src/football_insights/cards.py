"""The seven question cards: what each asks, the data and method, the expected
result, and why it matters. The numbers on each card come from its tool call."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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


CARDS: tuple[Card, ...] = (
    Card(
        number=3,
        question=("What trends have there been in international football throughout the ages - home advantage, "
                  "total goals scored, distribution of teams' strength etc"),
        tool="trends",
        arguments={"metric": "home_advantage"},
        asks="Has playing at home always mattered as much as it does now?",
        data_method=("Every non-neutral match in results.csv, grouped by decade: the share of home wins, draws, and "
                     "away wins, with a 95% interval for the home win share."),
        expected=("A line per result type by decade; the home win share stays near half of all matches, with "
                  "early decades noisy because few matches were played."),
        why=("Home advantage is the oldest pattern in the sport. Seeing it over 150 years shows how stable a "
             "pattern can be even while the game around it changes completely."),
    ),
)


def by_number() -> dict[int, Card]:
    return {card.number: card for card in CARDS}
