"""The grounding validator: every number in a narrative must come from a tool result.

It extracts each number the model wrote and accepts it only if a tool returned
the same value at the precision the narrative uses (47% matches 47.2; 1.7
million matches 1,712,345). Numbers that appear in the viewer's own question
and small ordinal positions ("1st" to "10th") are exempt. Signs are compared
by magnitude, so "fell by 6.6 points" matches a change of -6.6.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from ..schemas import Grounding, ToolResult

_NUMBER = re.compile(
    r"(?<![\w.])(?P<sign>[-+−])?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<suffix>st|nd|rd|th|s)?(?![\w.]*\d)"
    r"(?:\s*(?P<scale>million|billion|thousand))?",
    re.IGNORECASE,
)
_SCALES = {"thousand": 1e3, "million": 1e6, "billion": 1e9}


@dataclass(frozen=True)
class NarrativeNumber:
    text: str
    value: float
    decimals: int
    scale: float
    ordinal: bool


@dataclass
class AllowedNumbers:
    values: set[float] = field(default_factory=set)

    def add(self, value: float) -> None:
        if math.isfinite(value):
            self.values.add(abs(float(value)))

    def add_text(self, text: str) -> None:
        for number in extract_numbers(text):
            self.add(number.value)

    def matches(self, number: NarrativeNumber) -> bool:
        target = abs(number.value)
        if target in self.values:
            return True
        tolerance = 0.5 * (10 ** -number.decimals) * number.scale
        return any(abs(v - target) <= tolerance + 1e-9 for v in self.values)


def extract_numbers(text: str) -> list[NarrativeNumber]:
    found = []
    for match in _NUMBER.finditer(text or ""):
        raw = match.group("num")
        decimals = len(raw.split(".", 1)[1]) if "." in raw else 0
        scale = _SCALES.get((match.group("scale") or "").lower(), 1.0)
        value = float(raw.replace(",", "")) * scale
        if match.group("sign") in ("-", "−"):
            value = -value
        suffix = (match.group("suffix") or "").lower()
        found.append(NarrativeNumber(text=match.group(0).strip(), value=value, decimals=decimals, scale=scale,
                                     ordinal=suffix in ("st", "nd", "rd", "th")))
    return found


def _walk(value: Any, allowed: AllowedNumbers) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int | float):
        allowed.add(float(value))
    elif isinstance(value, str):
        allowed.add_text(value)
    elif isinstance(value, dict):
        for item in value.values():
            _walk(item, allowed)
    elif isinstance(value, list | tuple):
        for item in value:
            _walk(item, allowed)


def allowed_numbers(results: Iterable[ToolResult], question: str = "") -> AllowedNumbers:
    """Every number a tool returned, anywhere in its result, plus numbers in the question."""
    allowed = AllowedNumbers()
    for result in results:
        _walk(result.model_dump(mode="json", exclude={"dataset_version", "method_version", "tool"}), allowed)
    allowed.add_text(question)
    return allowed


def check(narrative: str, results: list[ToolResult], question: str = "") -> tuple[int, list[str]]:
    """Returns (numbers checked, ungrounded number texts)."""
    allowed = allowed_numbers(results, question)
    numbers = extract_numbers(narrative)
    ungrounded = [n.text for n in numbers if not (n.ordinal and 1 <= n.value <= 10) and not allowed.matches(n)]
    return len(numbers), ungrounded


def grounding(status: str, checked: int, ungrounded: list[str]) -> Grounding:
    return Grounding(status=status, numbers_checked=checked, ungrounded=ungrounded)  # type: ignore[arg-type]
