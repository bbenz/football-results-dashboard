"""Result shapes shared by the tools, the agent, and the web UI.

A tool result is bounded (aggregates, never raw tables), and every number in it
is either a fact with an evidence ID or a cell of a small table. The grounding
validator only accepts narrative numbers it can find here.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

Number = int | float
Cell = str | int | float | None

MAX_TABLE_ROWS = 30
MAX_CHART_POINTS = 200


class Fact(BaseModel):
    id: str
    label: str
    value: Number
    unit: str = ""
    decimals: int = 0

    @property
    def display(self) -> str:
        if isinstance(self.value, int) or self.decimals == 0:
            text = f"{round(self.value):,}"
        else:
            text = f"{self.value:,.{self.decimals}f}"
        if self.unit == "%":
            return text + "%"
        return f"{text} {self.unit}".strip()


class Table(BaseModel):
    columns: list[str]
    rows: Sequence[Sequence[Cell]] = Field(max_length=MAX_TABLE_ROWS)


class Series(BaseModel):
    name: str
    values: Sequence[Number | None]
    lower: Sequence[Number | None] | None = None
    upper: Sequence[Number | None] | None = None


class Chart(BaseModel):
    kind: Literal["line", "bar", "hbar"]
    title: str
    x: list[str] = Field(max_length=MAX_CHART_POINTS)
    series: list[Series]
    x_label: str = ""
    y_label: str = ""
    y_unit: str = ""
    y_min: Number | None = None
    y_max: Number | None = None
    summary: str


class ToolResult(BaseModel):
    tool: str
    question: int
    view: str
    params: dict[str, Any] = Field(default_factory=dict)
    title: str
    headline: str
    facts: list[Fact] = Field(default_factory=list)
    table: Table | None = None
    chart: Chart | None = None
    method: str
    coverage: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    cannot_tell: str = ""
    method_version: str
    dataset_version: str
    row_counts: dict[str, int] = Field(default_factory=dict)

    @property
    def evidence_ids(self) -> list[str]:
        return [fact.id for fact in self.facts]


class ToolCallRecord(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    error: str | None = None
    duration_ms: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)
    row_counts: dict[str, int] = Field(default_factory=dict)


class ModelUsage(BaseModel):
    deployment: str
    calls: int = 0
    latency_ms: float = 0.0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    estimated_cost_usd: float = 0.0


class Grounding(BaseModel):
    status: Literal["passed", "passed_after_retry", "failed_fallback", "not_applicable"]
    numbers_checked: int = 0
    ungrounded: list[str] = Field(default_factory=list)


NarrativeStatus = Literal["live", "cached", "unavailable", "fallback", "filtered"]


class Answer(BaseModel):
    question: str
    in_scope: bool = True
    narrative: str | None = None
    narrative_status: NarrativeStatus
    notice: str | None = None
    cached_at: str | None = None
    results: list[ToolResult] = Field(default_factory=list)
    key_evidence_ids: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    model: ModelUsage | None = None
    grounding: Grounding
    caveats: list[str] = Field(default_factory=list)
    cannot_tell: list[str] = Field(default_factory=list)
    trace_id: str = ""
