"""Small, dependency-free statistics with fixed seeds, so results are reproducible."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

BOOTSTRAP_SEED = 20261014
BOOTSTRAP_RESAMPLES = 2000


def wilson(successes: int, trials: int, z: float = 1.959964) -> tuple[float, float, float]:
    """Share and 95% Wilson score interval, as percentages."""
    if trials <= 0:
        return 0.0, 0.0, 0.0
    p = successes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return 100 * p, 100 * max(0.0, centre - half), 100 * min(1.0, centre + half)


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile, q in [0, 100]."""
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def bootstrap_mean(values: Sequence[float], resamples: int = BOOTSTRAP_RESAMPLES,
                   seed: int = BOOTSTRAP_SEED) -> tuple[float, float, float]:
    """Mean and 95% percentile bootstrap interval."""
    if not values:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    stats = sorted(mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples))
    return mean(values), stats[int(0.025 * resamples)], stats[int(0.975 * resamples) - 1]


def bootstrap_difference(a: Sequence[float], b: Sequence[float], resamples: int = BOOTSTRAP_RESAMPLES,
                         seed: int = BOOTSTRAP_SEED) -> tuple[float, float, float]:
    """mean(a) - mean(b) with a 95% percentile bootstrap interval (independent resampling)."""
    if not a or not b:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    na, nb = len(a), len(b)
    stats = sorted(
        mean([a[rng.randrange(na)] for _ in range(na)]) - mean([b[rng.randrange(nb)] for _ in range(nb)])
        for _ in range(resamples)
    )
    return mean(a) - mean(b), stats[int(0.025 * resamples)], stats[int(0.975 * resamples) - 1]


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman rank correlation with average ranks for ties."""
    if len(x) != len(y) or len(x) < 3:
        return 0.0

    def ranks(values: Sequence[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    rx, ry = ranks(x), ranks(y)
    mx, my = mean(rx), mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0
