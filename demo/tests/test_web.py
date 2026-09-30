"""Web and insights APIs in-process: pages render, headers are set, limits hold,
nothing administrative is exposed, and the badge reports injected values only."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from football_insights.config import get_settings


@pytest.fixture
def apps(monkeypatch, curated_store):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("PLATFORM_NAME", "ACA")
    monkeypatch.setenv("PLATFORM_REGION", "testregion")
    monkeypatch.setenv("IMAGE_DIGEST", "sha256:0123456789abcdef0123")
    monkeypatch.setenv("ASK_RATE_LIMIT_PER_MINUTE", "2")
    monkeypatch.setenv("WEB_RATE_LIMIT_PER_MINUTE", "8")
    get_settings.cache_clear()
    from football_insights.insights import app as insights_module
    from football_insights.web import app as web_module

    insights_module.state.set(curated_store)
    insights_app = insights_module.create_app()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=insights_app), base_url="http://insights")
    web = web_module.create_app(client=client)
    yield web, insights_app
    get_settings.cache_clear()


def get(app, path: str, headers: dict[str, str] | None = None) -> httpx.Response:  # type: ignore[no-untyped-def]
    async def call() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://web") as c:
            return await c.get(path, headers=headers)

    return asyncio.run(call())


def test_home_page_renders_badge_and_card(apps) -> None:  # type: ignore[no-untyped-def]
    web, _ = apps
    response = get(web, "/")
    assert response.status_code == 200
    html = response.text
    assert "<strong>ACA</strong> · testregion" in html
    assert "image 0123456789ab" in html
    assert "AI narrative: off" in html
    assert "About this app" in html and "About this question" in html
    assert "Q3" in html
    assert "Mart Jürisoo" in html and "CC BY 4.0" in html


def test_badge_admits_when_insights_is_unreachable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("PLATFORM_NAME", "AKS")
    monkeypatch.setenv("AI_MODEL_DEPLOYMENT", "gpt-6-sol")
    get_settings.cache_clear()
    from football_insights.web import app as web_module

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("insights down", request=request)

    web = web_module.create_app(client=httpx.AsyncClient(transport=httpx.MockTransport(refuse),
                                                         base_url="http://insights"))
    html = get(web, "/").text
    get_settings.cache_clear()
    assert "<strong>AKS</strong>" in html
    assert "data unavailable" in html and "model unknown" in html and "AI narrative: unavailable" in html
    assert "gpt-6-sol" not in html
    assert get(web, "/readyz").status_code == 503


def test_security_headers(apps) -> None:  # type: ignore[no-untyped-def]
    web, _ = apps
    headers = get(web, "/").headers
    assert "default-src 'self'" in headers["content-security-policy"]
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["cache-control"] == "no-store"


def test_no_admin_or_docs_endpoints(apps) -> None:  # type: ignore[no-untyped-def]
    web, insights = apps
    for path in ("/docs", "/openapi.json", "/admin", "/reset", "/v1/tools"):
        assert get(web, path).status_code == 404
    assert get(insights, "/docs").status_code == 404


def test_rate_limit_per_client(apps) -> None:  # type: ignore[no-untyped-def]
    web, _ = apps
    codes = [get(web, "/data", {"x-forwarded-for": "203.0.113.9"}).status_code for _ in range(9)]
    assert codes[:8] == [200] * 8
    assert codes[8] == 429
    assert get(web, "/data", {"x-forwarded-for": "203.0.113.10"}).status_code == 200


def test_data_page_and_trace_validation(apps) -> None:  # type: ignore[no-untyped-def]
    web, _ = apps
    data = get(web, "/data")
    assert data.status_code == 200 and "Data quality report" in data.text
    assert get(web, "/trace/not-a-trace").status_code == 400
    assert get(web, "/trace/" + "0" * 32).status_code == 200


def test_an_older_web_shows_the_cards_it_knows_during_a_rollout(apps, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # During a v2 rollout, a v1 web revision can reach a v2 insights that returns a card it doesn't know.
    import dataclasses

    from football_insights.cards import CARDS
    from football_insights.insights import app as insights_module

    monkeypatch.setattr(insights_module, "CARDS", (*CARDS, dataclasses.replace(CARDS[0], number=99)))
    web, _ = apps
    html = get(web, "/", {"x-forwarded-for": "198.51.100.77"}).text
    assert "not ready" not in html
    assert html.count('<section class="card"') == len(CARDS)


def test_every_card_view_renders_without_the_model(apps) -> None:  # type: ignore[no-untyped-def]
    from football_insights.cards import CARDS, default_view, views

    web, _ = apps
    home = get(web, "/").text
    assert home.count('class="views"') == len(CARDS)
    request = 0
    for card in CARDS:
        choices = views(card)
        assert choices[default_view(card)].arguments == card.arguments
        for index, view in enumerate(choices):
            request += 1  # a different client each time, so the per-client page limit doesn't apply
            page = get(web, f"/card/{card.number}?v={index}", {"x-forwarded-for": f"198.51.100.{request}"})
            assert page.status_code == 200, (card.number, view.label)
            assert f"Q{card.number}" in page.text and "Tool call" in page.text
    lens = [v.label for card in CARDS for v in views(card) if "(development lens)" in v.label]
    assert len(lens) >= 7
    assert get(web, "/card/9?v=0", {"x-forwarded-for": "198.51.100.250"}).status_code == 404
    assert get(web, "/card/1?v=99", {"x-forwarded-for": "198.51.100.251"}).status_code == 404


def test_insights_readiness_and_tools(apps) -> None:  # type: ignore[no-untyped-def]
    _, insights = apps
    assert get(insights, "/readyz").json()["ready"] is True
    about = get(insights, "/v1/about").json()
    assert about["runtime"]["platform"] == "ACA"
    assert about["narrative_mode"] == "off"


def post(app, path: str, **kwargs) -> httpx.Response:  # type: ignore[no-untyped-def]
    async def call() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://web") as c:
            return await c.post(path, **kwargs)

    return asyncio.run(call())


def test_ask_without_a_model_says_so_and_keeps_evidence_honest(apps) -> None:  # type: ignore[no-untyped-def]
    web, _ = apps
    page = post(web, "/ask", data={"question": "Who is the best team of all time?"})
    assert page.status_code == 200
    assert "AI narrative unavailable" in page.text and "switched off" in page.text
    api = post(web, "/api/ask", json={"question": "Who is the best team of all time?"})
    assert api.status_code == 200 and api.json()["narrative_status"] == "unavailable"


def test_ask_rejects_bad_input_and_is_rate_limited(apps) -> None:  # type: ignore[no-untyped-def]
    web, _ = apps
    too_long = post(web, "/api/ask", json={"question": "x" * 400}, headers={"x-forwarded-for": "198.51.100.1"})
    assert too_long.status_code == 400 and "limited to" in too_long.json()["detail"]
    assert post(web, "/api/ask", content=b"not json", headers={"x-forwarded-for": "198.51.100.1"}).status_code == 400
    assert post(web, "/api/ask", content=b"not json", headers={"x-forwarded-for": "198.51.100.1"}).status_code == 429
    assert post(web, "/api/ask", content=b"not json", headers={"x-forwarded-for": "198.51.100.2"}).status_code == 400


def test_public_requests_cannot_choose_or_join_a_trace(apps) -> None:  # type: ignore[no-untyped-def]
    web, _ = apps
    chosen = "ab" * 16
    page = get(web, "/data", {"traceparent": f"00-{chosen}-{'cd' * 8}-01", "x-forwarded-for": "198.51.100.60"})
    assert page.status_code == 200 and chosen not in page.text


def test_request_bodies_are_bounded(apps) -> None:  # type: ignore[no-untyped-def]
    web, _ = apps
    big = post(web, "/api/ask", json={"question": "x" * 20_000}, headers={"x-forwarded-for": "198.51.100.61"})
    assert big.status_code == 413 and big.headers["x-frame-options"] == "DENY"

    async def chunks():  # type: ignore[no-untyped-def]
        for _ in range(40):
            yield b"x" * 1_000

    chunked = post(web, "/api/ask", content=chunks(), headers={"x-forwarded-for": "198.51.100.62"})
    assert chunked.status_code == 413
    nested = post(web, "/api/ask", content=b"[" * 5_000 + b"]" * 5_000,
                  headers={"content-type": "application/json", "x-forwarded-for": "198.51.100.63"})
    assert nested.status_code == 400


def test_public_api_cannot_pick_the_model_or_see_internal_errors(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    get_settings.cache_clear()
    from football_insights.web import app as web_module

    sent: list[dict[str, object]] = []

    def insights(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/ask":
            sent.append(json.loads(request.content))
            return httpx.Response(503, json={"detail": "curated store not loaded: blob https://internal.example"})
        return httpx.Response(503, json={"detail": "not ready"})

    web = web_module.create_app(client=httpx.AsyncClient(transport=httpx.MockTransport(insights),
                                                         base_url="http://insights"))
    response = post(web, "/api/ask", json={"question": "Who is best?", "deployment": "gpt-6-astra"})
    get_settings.cache_clear()
    assert sent == [{"question": "Who is best?"}]
    assert response.status_code == 503 and "internal.example" not in response.text


def test_services_listen_only_on_this_machine_unless_in_a_container() -> None:
    from conftest import REPO_ROOT

    assert get_settings().bind_host == "127.0.0.1"
    assert "BIND_HOST=0.0.0.0" in (REPO_ROOT / "demo" / "docker" / "Dockerfile").read_text(encoding="utf-8")


@pytest.mark.replay
def test_live_answer_renders_narrative_evidence_and_trace(apps, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from conftest import make_settings
    from fake_responses import FakeClient, answer, tool_calls
    from football_insights.agent.loop import InsightsAgent
    from football_insights.insights import app as insights_module

    ctx = insights_module.state.ctx
    facts = {f.id: f for f in insights_module.traced_tool(ctx, "dataset_facts", {})[0].facts}
    client = FakeClient([tool_calls(("dataset_facts", {})),
                         answer(f"The data holds {int(facts['scope.matches'].value)} matches.", ["scope.matches"])])
    settings = make_settings(foundry_project_endpoint="https://example.invalid/api/projects/p",
                             narrative_cache_dir=tmp_path)
    insights_module.state.agent = InsightsAgent(settings, lambda n, a: insights_module.traced_tool(ctx, n, a),
                                                client_factory=lambda: client)
    web, _ = apps
    page = post(web, "/ask", data={"question": "How many matches are in the data?"})
    html = page.text
    assert "AI narrative: live" in html and "Grounded: 1 numbers checked" in html
    assert f"The data holds {int(facts['scope.matches'].value)} matches." in html
    assert "dataset_facts()" in html and "scope.matches" in html
    assert "Trace ID for Application Insights" in html
