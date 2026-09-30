"""Save a running web endpoint's pages for the offline fallback tiers of the livestream.

Captures every view of every insight card, the Data page, and the answers to the prepared on-stage questions
(the evaluation cases marked `capture`). Styles and scripts are inlined, so the pages open from disk without
the app or a network connection, and every page carries a banner with its source and capture time, so a
recording is never mistaken for the live app.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .cards import CARDS, views
from .evaluation import load_cases

RATE_LIMIT_RETRIES = 6
RATE_LIMIT_WAIT_SECONDS = 11.0


@dataclass
class Snapshot:
    url: str
    out_dir: Path
    captured_at: str
    saved: list[tuple[str, str]] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def _name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def _self_contained(page: str, css: str, js: str, banner: str) -> str:
    page = page.replace('<link rel="stylesheet" href="/static/app.css">', f"<style>{css}</style>")
    page = page.replace('<script src="/static/app.js" defer></script>', f"<script>{js}</script>")
    return page.replace("<body>", f"<body>{banner}", 1)


def run(url: str, out_dir: Path, include_answers: bool = True, timeout: float = 90.0,
        client: httpx.Client | None = None) -> Snapshot:
    base = url.rstrip("/")
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    snap = Snapshot(url=base, out_dir=out_dir, captured_at=stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    banner = ('<div style="background:#7a1f1f;color:#fff;padding:0.6rem 1rem;font-weight:700">'
              f"Recorded copy of {html.escape(base)}, captured {stamp}. This is not the live app.</div>")
    pages: list[tuple[str, str, str, dict[str, str] | None]] = [
        ("home", "GET", "/", None), ("data", "GET", "/data", None)]
    for card in CARDS:
        for index, view in enumerate(views(card)):
            pages.append((f"q{card.number}-{_name(view.label)}", "GET", f"/card/{card.number}?v={index}", None))
    if include_answers:
        for case in (c for c in load_cases() if c.capture):
            pages.append((f"answer-{case.id}", "POST", "/ask", {"question": case.question}))
    with client or httpx.Client(base_url=base, timeout=timeout) as http:
        css = http.get("/static/app.css").text
        js = http.get("/static/app.js").text
        for name, method, path, form in pages:
            try:
                response = http.request(method, path, data=form)
                for _ in range(RATE_LIMIT_RETRIES):
                    if response.status_code != 429:
                        break
                    time.sleep(RATE_LIMIT_WAIT_SECONDS)  # the app limits requests per client per minute
                    response = http.request(method, path, data=form)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                snap.failed.append(f"{name}: {type(exc).__name__}")
                continue
            target = out_dir / f"{name}.html"
            target.write_text(_self_contained(response.text, css, js, banner), encoding="utf-8", newline="\n")
            snap.saved.append((name, target.name))
    links = "".join(f'<li><a href="{file}">{html.escape(name)}</a></li>' for name, file in snap.saved)
    listing = (f"<!doctype html><meta charset='utf-8'><title>Recorded pages</title>{banner}"
               f"<h1>Recorded pages from {html.escape(base)}</h1><ul>{links}</ul>")
    (out_dir / "index.html").write_text(listing, encoding="utf-8", newline="\n")
    return snap
