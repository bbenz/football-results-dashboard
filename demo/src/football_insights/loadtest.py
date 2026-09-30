"""A bounded load test against deterministic endpoints only.

It never calls the model: the allowed paths render cached, deterministic
results. Rate and duration have hard caps, so a typo cannot turn a demo
measurement into a stress test.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field

import httpx

DETERMINISTIC_PATHS = ("/", "/data", "/healthz")
MAX_RPS = 50
MAX_SECONDS = 180


@dataclass
class LoadResult:
    url: str
    rps: int
    seconds: int
    sent: int = 0
    statuses: Counter[int] = field(default_factory=Counter)
    latencies_ms: list[float] = field(default_factory=list)
    errors: Counter[str] = field(default_factory=Counter)

    def summary(self) -> dict[str, object]:
        lat = sorted(self.latencies_ms)

        def pct(q: float) -> float:
            return round(lat[min(len(lat) - 1, int(q / 100 * len(lat)))], 1) if lat else 0.0

        return {"url": self.url, "target_rps": self.rps, "seconds": self.seconds, "sent": self.sent,
                "statuses": dict(self.statuses), "errors": dict(self.errors), "p50_ms": pct(50), "p95_ms": pct(95),
                "mean_ms": round(statistics.mean(lat), 1) if lat else 0.0}


async def _run(result: LoadResult, paths: tuple[str, ...]) -> None:
    interval = 1.0 / result.rps
    limits = httpx.Limits(max_connections=result.rps * 2)
    async with httpx.AsyncClient(base_url=result.url, timeout=10.0, limits=limits) as client:
        async def one(path: str) -> None:
            start = time.perf_counter()
            try:
                response = await client.get(path)
                result.statuses[response.status_code] += 1
                result.latencies_ms.append((time.perf_counter() - start) * 1000)
            except httpx.HTTPError as exc:
                result.errors[type(exc).__name__] += 1

        tasks = []
        deadline = time.perf_counter() + result.seconds
        i = 0
        while time.perf_counter() < deadline:
            tasks.append(asyncio.create_task(one(paths[i % len(paths)])))
            result.sent += 1
            i += 1
            await asyncio.sleep(interval)
        await asyncio.gather(*tasks)


def run(url: str, rps: int, seconds: int, paths: tuple[str, ...] = DETERMINISTIC_PATHS) -> LoadResult:
    if not 1 <= rps <= MAX_RPS:
        raise ValueError(f"rps must be between 1 and {MAX_RPS}")
    if not 1 <= seconds <= MAX_SECONDS:
        raise ValueError(f"seconds must be between 1 and {MAX_SECONDS}")
    bad = [p for p in paths if p not in DETERMINISTIC_PATHS]
    if bad:
        raise ValueError(f"only deterministic paths are allowed: {DETERMINISTIC_PATHS}; got {bad}")
    result = LoadResult(url=url.rstrip("/"), rps=rps, seconds=seconds)
    asyncio.run(_run(result, paths))
    return result
