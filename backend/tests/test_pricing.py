from app.gateway.pricing import estimate_cost_usd


def test_known_model_cost():
    # Gateway passes LiteLLM aliases — pricing table is keyed to those.
    cost = estimate_cost_usd(
        "structured-json", prompt_tokens=1_000_000, completion_tokens=1_000_000
    )
    assert cost > 0
    cost2 = estimate_cost_usd("structured-json-gemini", 1_000_000, 1_000_000)
    assert cost2 != cost  # Groq vs Gemini prices differ


def test_nim_model_cost():
    cost = estimate_cost_usd("structured-json-nim", 1_000_000, 1_000_000)
    assert cost > 0
    # NIM and Groq should not be the same price
    cost_groq = estimate_cost_usd("structured-json", 1_000_000, 1_000_000)
    assert cost != cost_groq


def test_unknown_model_prices_zero():
    assert estimate_cost_usd("mystery/model", 1000, 1000) == 0.0


def test_partial_alias_match():
    # Alias substrings must match correctly — longer aliases match first.
    cost_nim = estimate_cost_usd("structured-json-nim", 1_000_000, 0)
    cost_base = estimate_cost_usd("structured-json", 1_000_000, 0)
    assert cost_nim > 0
    assert cost_base > 0
    assert cost_nim != cost_base  # NIM ≠ Groq price
