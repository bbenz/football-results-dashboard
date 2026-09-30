"""Replay snapshots: every card view and the prepared answers, saved as self-contained, clearly labeled pages."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from football_insights import snapshot
from football_insights.cards import CARDS, views
from football_insights.config import get_settings
from football_insights.evaluation import load_cases


def test_snapshot_saves_every_view_offline_and_labeled(monkeypatch, curated_store, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("WEB_RATE_LIMIT_PER_MINUTE", "1000")
    get_settings.cache_clear()
    from football_insights.insights import app as insights_module
    from football_insights.web import app as web_module

    insights_module.state.set(curated_store)
    insights = httpx.AsyncClient(transport=httpx.ASGITransport(app=insights_module.create_app()),
                                 base_url="http://insights")
    web = web_module.create_app(client=insights)
    with TestClient(web, base_url="http://web") as client:
        snap = snapshot.run("http://web", tmp_path, client=client)
    get_settings.cache_clear()

    expected = 2 + sum(len(views(card)) for card in CARDS) + sum(1 for case in load_cases() if case.capture)
    assert not snap.failed and len(snap.saved) == expected
    for page in tmp_path.glob("*.html"):
        text = page.read_text(encoding="utf-8")
        assert "This is not the live app." in text, page.name
        assert 'href="/static/' not in text and 'src="/static/' not in text, page.name
    assert (tmp_path / "index.html").is_file()
