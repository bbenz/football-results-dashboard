"""Shared context for the deterministic tools: the store plus cached derived data."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from ..reference import Reference, get_reference
from ..store import CuratedStore
from . import ratings


@dataclass
class ToolContext:
    store: CuratedStore
    reference: Reference = field(default_factory=get_reference)
    _ratings: ratings.RatingHistory | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    cache: dict[str, Any] = field(default_factory=dict)

    @property
    def dataset_version(self) -> str:
        return self.store.version

    def ratings(self) -> ratings.RatingHistory:
        with self._lock:
            if self._ratings is None:
                rows = self.store.query(
                    "select match_id, year, home_team, away_team, home_score, away_score, neutral, k, "
                    "strftime(date, '%Y-%m-%d') from matches order by match_id")
                self._ratings = ratings.compute(
                    ratings.MatchInput(int(r[0]), int(r[1]), r[2], r[3], int(r[4]), int(r[5]), bool(r[6]), int(r[7]),
                                       str(r[8]))
                    for r in rows)
            return self._ratings


def slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_").replace("__", "_")


def pct(numerator: float, denominator: float, digits: int = 1) -> float:
    return round(100.0 * numerator / denominator, digits) if denominator else 0.0
