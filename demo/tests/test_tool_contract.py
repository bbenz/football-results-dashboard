"""Every tool, every parameter combination: valid results, stable evidence IDs, and
self-grounded text (every number in a headline or chart summary appears in the
tool's own facts, table, or chart data), on synthetic and, when present, real data."""

from __future__ import annotations

import itertools
import re
import time
from typing import Any

import pytest
from conftest import requires_real_data
from helpers import M, make_store

from football_insights.agent.grounding import check
from football_insights.analytics.context import ToolContext
from football_insights.analytics.registry import TOOLS, run_tool

EVIDENCE_ID = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")


def combinations(name: str) -> list[dict[str, Any]]:
    schema = TOOLS[name].params.model_json_schema()
    fields = schema.get("properties", {})
    options: dict[str, list[Any]] = {}
    for field, spec in fields.items():
        variants = spec.get("anyOf", [spec])
        values: list[Any] = []
        for variant in variants:
            if "enum" in variant:
                values += variant["enum"]
            elif variant.get("type") == "null":
                values.append(None)
            elif variant.get("type") == "integer":
                values.append(2026)
        options[field] = values
    keys = list(options)
    return [dict(zip(keys, combo, strict=True)) for combo in itertools.product(*(options[k] for k in keys))]


def assert_contract(ctx: ToolContext, name: str, args: dict[str, Any], budget_s: float | None = None) -> None:
    start = time.perf_counter()
    result = run_tool(ctx, name, args)
    elapsed = time.perf_counter() - start
    if budget_s is not None:
        assert elapsed < budget_s, f"{name}{args} took {elapsed:.2f}s"
    ids = result.evidence_ids
    assert len(ids) == len(set(ids)), f"duplicate evidence IDs in {name}{args}"
    assert all(EVIDENCE_ID.match(i) for i in ids), f"malformed evidence ID in {name}{args}: {ids}"
    assert result.dataset_version == ctx.dataset_version and result.method_version
    assert result.table is None or len(result.table.rows) <= 30
    for text in [result.headline] + ([result.chart.summary] if result.chart else []):
        _, ungrounded = check(text, [result])
        assert not ungrounded, f"{name}{args}: ungrounded {ungrounded} in {text!r}"


def synthetic_ctx() -> ToolContext:
    teams = ["Avalon", "Borealis", "Cascadia", "Dunmore"]
    matches = [M(f"{1950 + i}-06-0{1 + i % 5}", teams[i % 4], teams[(i + 1) % 4], i % 3, (i + 1) % 2,
                 "FIFA World Cup" if i % 7 == 0 else "Friendly") for i in range(40)]
    return ToolContext(make_store(matches))


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_every_combination_on_synthetic_data(name: str) -> None:
    ctx = synthetic_ctx()
    for args in combinations(name):
        assert_contract(ctx, name, args)


@pytest.mark.realdata
@requires_real_data
def test_every_combination_on_real_data(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from conftest import REAL_DATA, make_settings

    from football_insights.ingest.pipeline import run
    from football_insights.ingest.storage import LocalCuratedStorage, LocalRawSource
    from football_insights.store import load

    run(LocalRawSource(REAL_DATA), LocalCuratedStorage(tmp_path / "curated"), platform="Test")
    ctx = ToolContext(load(make_settings(curated_dir=tmp_path / "curated"), cache_dir=tmp_path / "cache"))
    ctx.ratings()
    for name in sorted(TOOLS):
        for args in combinations(name):
            assert_contract(ctx, name, args, budget_s=3.0)
