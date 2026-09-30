"""Estimated cost per answer, from dated list prices. Always labeled as an estimate.

Prices: Azure Retail Prices API, product "Azure OpenAI GPT6", Global Standard,
short context, USD per 1M tokens, retrieved 2026-09-29. Your agreement may differ.
"""

from __future__ import annotations

PRICES_RETRIEVED = "2026-09-29"
# deployment model name -> (input, cached input, output) USD per 1M tokens
PRICES: dict[str, tuple[float, float, float]] = {
    "gpt-6-astra": (10.0, 1.0, 50.0),
    "gpt-6-sol": (2.0, 0.2, 10.0),
}


def estimate(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    price = PRICES.get(model)
    if price is None:
        return 0.0
    fresh = max(0, input_tokens - cached_tokens)
    return round((fresh * price[0] + cached_tokens * price[1] + output_tokens * price[2]) / 1_000_000, 6)
