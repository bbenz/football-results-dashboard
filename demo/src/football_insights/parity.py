"""Cross-platform parity: the same images and curated data must give identical deterministic results.

Fetches /api/cards from each web endpoint and compares the canonical JSON of every card result.
Runtime values such as the platform, region, or trace IDs are not part of card results, so any
difference is a real difference in data, code, or configuration.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ParityReport:
    urls: list[str]
    digests: dict[str, dict[int, str]] = field(default_factory=dict)
    dataset_versions: dict[str, list[str]] = field(default_factory=dict)
    differences: list[str] = field(default_factory=list)

    @property
    def identical(self) -> bool:
        return not self.differences

    def as_dict(self) -> dict[str, Any]:
        return {"urls": self.urls, "identical": self.identical, "dataset_versions": self.dataset_versions,
                "card_digests": {url: {str(n): d for n, d in cards.items()} for url, cards in self.digests.items()},
                "differences": self.differences}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def first_difference(a: Any, b: Any, path: str = "") -> str:
    if type(a) is not type(b):
        return f"{path or '/'}: {type(a).__name__} vs {type(b).__name__}"
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                return f"{path}/{key}: present on one side only"
            if a[key] != b[key]:
                return first_difference(a[key], b[key], f"{path}/{key}")
    elif isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: {len(a)} vs {len(b)} items"
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            if x != y:
                return first_difference(x, y, f"{path}/{i}")
    return f"{path or '/'}: {a!r} vs {b!r}"


def fetch_cards(url: str, client: httpx.Client) -> dict[str, Any]:
    response = client.get(url.rstrip("/") + "/api/cards")
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


def compare(payloads: dict[str, dict[str, Any]]) -> ParityReport:
    urls = list(payloads)
    report = ParityReport(urls=urls)
    by_url: dict[str, dict[int, Any]] = {}
    for url, payload in payloads.items():
        cards = {int(item["number"]): item["result"] for item in payload["cards"]}
        by_url[url] = cards
        report.digests[url] = {n: hashlib.sha256(canonical(r).encode()).hexdigest()[:16] for n, r in cards.items()}
        report.dataset_versions[url] = payload.get("dataset_versions", [])
    reference, *others = urls
    for other in others:
        ref, cur = by_url[reference], by_url[other]
        for number in sorted(set(ref) | set(cur)):
            if number not in ref or number not in cur:
                report.differences.append(f"card {number}: only on {reference if number in ref else other}")
            elif ref[number] != cur[number]:
                detail = first_difference(ref[number], cur[number])
                report.differences.append(f"card {number}: {reference} vs {other}: {detail}")
    return report


def run(urls: list[str], timeout: float = 30.0) -> ParityReport:
    if len(urls) < 2:
        raise ValueError("parity needs at least two web URLs")
    with httpx.Client(timeout=timeout) as client:
        return compare({url: fetch_cards(url, client) for url in urls})
