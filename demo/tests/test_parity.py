"""Cross-platform parity. Unit tests compare in-process web apps; the cloud test compares the deployed
AKS and ACA endpoints and runs only when AKS_WEB_URL and ACA_WEB_URL are set."""

from __future__ import annotations

import asyncio
import copy
import os
from typing import Any

import httpx
import pytest

from football_insights import parity
from football_insights.cards import CARDS
from football_insights.config import get_settings


def cards_payload(web: Any) -> dict[str, Any]:
    async def call() -> dict[str, Any]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web), base_url="http://web") as c:
            response = await c.get("/api/cards")
            assert response.status_code == 200
            payload: dict[str, Any] = response.json()
            return payload

    return asyncio.run(call())


@pytest.fixture
def web_app(monkeypatch, curated_store):  # type: ignore[no-untyped-def]
    get_settings.cache_clear()
    from football_insights.insights import app as insights_module
    from football_insights.web import app as web_module

    insights_module.state.set(curated_store)
    insights_app = insights_module.create_app()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=insights_app), base_url="http://insights")
    yield web_module.create_app(client=client)
    get_settings.cache_clear()


def test_identical_deployments_are_identical(web_app) -> None:  # type: ignore[no-untyped-def]
    payload = cards_payload(web_app)
    assert len(payload["cards"]) == len(CARDS) and len(payload["dataset_versions"]) == 1
    report = parity.compare({"https://aks.example": payload, "https://aca.example": copy.deepcopy(payload)})
    assert report.identical
    assert report.digests["https://aks.example"] == report.digests["https://aca.example"]


def test_one_changed_number_is_reported_with_its_path(web_app) -> None:  # type: ignore[no-untyped-def]
    payload = cards_payload(web_app)
    changed = copy.deepcopy(payload)
    fact = changed["cards"][2]["result"]["facts"][0]
    fact["value"] = (fact["value"] or 0) + 1
    report = parity.compare({"https://aks.example": payload, "https://aca.example": changed})
    assert not report.identical
    assert len(report.differences) == 1
    assert "/facts/0/value" in report.differences[0]


def test_a_missing_card_is_reported() -> None:
    result = {"tool": "t", "facts": []}
    report = parity.compare({"a": {"cards": [{"number": 1, "result": result}, {"number": 2, "result": result}]},
                             "b": {"cards": [{"number": 1, "result": result}]}})
    assert report.differences == ["card 2: only on a"]


def test_parity_needs_two_urls() -> None:
    with pytest.raises(ValueError):
        parity.run(["https://only-one.example"])


@pytest.mark.skipif(not (os.environ.get("AKS_WEB_URL") and os.environ.get("ACA_WEB_URL")),
                    reason="set AKS_WEB_URL and ACA_WEB_URL to compare the deployed platforms")
def test_deployed_platforms_return_identical_results() -> None:
    report = parity.run([os.environ["AKS_WEB_URL"], os.environ["ACA_WEB_URL"]])
    assert report.identical, report.differences
