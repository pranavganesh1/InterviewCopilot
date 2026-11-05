from app.gateway.pricing import estimate_cost_usd


def test_known_model_cost():
    cost = estimate_cost_usd(
        "groq/openai/gpt-oss-120b", prompt_tokens=1_000_000, completion_tokens=1_000_000
    )
    assert cost > 0
    cost2 = estimate_cost_usd("groq/openai/gpt-oss-120b", 2_000_000, 0)
    assert cost2 != cost  # input/output prices differ


def test_unknown_model_prices_zero():
    assert estimate_cost_usd("mystery/model", 1000, 1000) == 0.0


def test_partial_model_name_match():
    # Model strings arrive with provider prefixes ("groq/openai/...").
    cost = estimate_cost_usd("something/unrelated-prefix/openai/gpt-oss-120b", 1_000_000, 0)
    assert cost > 0
