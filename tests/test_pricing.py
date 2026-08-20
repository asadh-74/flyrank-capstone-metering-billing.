import pytest

from app.pricing import calculate_token_cost_cents


def test_pure_fresh_input_only():
    # 2000 fresh input tokens, no cache, no output.
    # 2000/1000 * 50c = 100c
    cost = calculate_token_cost_cents(
        input_tokens=2000, cached_tokens=0, output_tokens=0, reasoning_tokens=0
    )
    assert cost == 100


def test_cached_tokens_are_cheaper_than_fresh():
    # Same total input tokens, but this time all cached.
    # 2000/1000 * 25c = 50c -- half the cost of the all-fresh case above.
    cost = calculate_token_cost_cents(
        input_tokens=2000, cached_tokens=2000, output_tokens=0, reasoning_tokens=0
    )
    assert cost == 50


def test_mixed_fresh_and_cached_input_priced_separately():
    # 1000 fresh + 1000 cached: NOT the same as 2000 at either flat rate.
    # fresh: 1000/1000 * 50c = 50c
    # cached: 1000/1000 * 25c = 25c
    # total = 75c
    cost = calculate_token_cost_cents(
        input_tokens=2000, cached_tokens=1000, output_tokens=0, reasoning_tokens=0
    )
    assert cost == 75


def test_reasoning_tokens_billed_at_output_rate_not_free():
    # Reasoning tokens are NOT a separate free category -- they cost the
    # same as output tokens.
    only_output = calculate_token_cost_cents(
        input_tokens=0, cached_tokens=0, output_tokens=1000, reasoning_tokens=0
    )
    only_reasoning = calculate_token_cost_cents(
        input_tokens=0, cached_tokens=0, output_tokens=0, reasoning_tokens=1000
    )
    assert only_output == only_reasoning == 150  # 1000/1000 * 150c


def test_output_and_reasoning_tokens_combine_at_same_rate():
    # 600 output + 400 reasoning = 1000 total output-rate tokens.
    cost = calculate_token_cost_cents(
        input_tokens=0, cached_tokens=0, output_tokens=600, reasoning_tokens=400
    )
    assert cost == 150


def test_full_mix_of_all_four_categories():
    # 800 fresh input + 200 cached input + 300 output + 100 reasoning.
    # fresh:     800/1000 * 50  = 40.0
    # cached:    200/1000 * 25  = 5.0
    # output:    400/1000 * 150 = 60.0   (300 output + 100 reasoning)
    # total = 105 cents
    cost = calculate_token_cost_cents(
        input_tokens=1000, cached_tokens=200, output_tokens=300, reasoning_tokens=100
    )
    assert cost == 105


def test_zero_usage_costs_zero():
    cost = calculate_token_cost_cents(0, 0, 0, 0)
    assert cost == 0


def test_cached_tokens_cannot_exceed_input_tokens():
    with pytest.raises(ValueError):
        calculate_token_cost_cents(
            input_tokens=100, cached_tokens=200, output_tokens=0, reasoning_tokens=0
        )


def test_negative_tokens_rejected():
    with pytest.raises(ValueError):
        calculate_token_cost_cents(
            input_tokens=-1, cached_tokens=0, output_tokens=0, reasoning_tokens=0
        )


def test_rounding_is_half_up_not_truncated():
    # 15 input tokens at 50c/1000 = 0.75c -> should round to 1 cent, not 0.
    cost = calculate_token_cost_cents(
        input_tokens=15, cached_tokens=0, output_tokens=0, reasoning_tokens=0
    )
    assert cost == 1
