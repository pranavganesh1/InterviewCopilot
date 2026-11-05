"""Estimated LLM cost table (M11).

Prices are PUBLIC LIST-PRICE ESTIMATES in USD per 1M tokens — free-tier usage
costs $0 today; these figures show what the same volume would cost at scale.
Edit this table when prices change. Matched by substring, most specific first.
"""

# (substr, input_usd_per_1m, output_usd_per_1m) — prices checked 2026-11-05.
_PRICES: list[tuple[str, float, float]] = [
    ("gpt-oss-120b", 0.15, 0.75),  # Groq list price
    ("gpt-oss-20b", 0.05, 0.40),
    ("gemini-flash", 0.30, 2.50),  # Gemini flash-class (AI Studio tier)
    ("llama-3.3", 0.60, 0.60),  # fallback if model returns
]


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimated USD cost for one call, or 0.0 for unknown models."""
    for substr, in_price, out_price in _PRICES:
        if substr in (model or ""):
            cost = (prompt_tokens / 1_000_000) * in_price
            cost += (completion_tokens / 1_000_000) * out_price
            return round(cost, 6)
    return 0.0
