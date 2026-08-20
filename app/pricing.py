"""
Cost calculation for AI-token usage.

The rule, straight from the capstone brief: token categories cannot simply
be added together.

  - cached input tokens are billed at the CACHED rate (cheaper)
  - the rest of input_tokens (i.e. input_tokens - cached_tokens) are billed
    at the full INPUT rate
  - output_tokens AND reasoning_tokens are both billed at the OUTPUT rate —
    reasoning tokens are not a separate free category, they're just output

Everything is computed with Decimal and returned as an int number of cents.
No floats touch a money value anywhere in this module.
"""
from decimal import ROUND_HALF_UP, Decimal

from .config import (
    PRICE_PER_1K_CACHED_INPUT_CENTS,
    PRICE_PER_1K_INPUT_CENTS,
    PRICE_PER_1K_OUTPUT_CENTS,
)

ONE_THOUSAND = Decimal(1000)


def calculate_token_cost_cents(
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
) -> int:
    """Return the cost, in whole cents, of one AI-usage event.

    Raises ValueError if cached_tokens exceeds input_tokens — cached tokens
    are a subset of input tokens, not an additional category, and a caller
    sending more cached than total input is sending a malformed request.
    """
    if any(v < 0 for v in (input_tokens, cached_tokens, output_tokens, reasoning_tokens)):
        raise ValueError("token counts must be non-negative")
    if cached_tokens > input_tokens:
        raise ValueError("cached_tokens cannot exceed input_tokens")

    billable_input = input_tokens - cached_tokens
    billable_output = output_tokens + reasoning_tokens

    input_cost = (Decimal(billable_input) * Decimal(PRICE_PER_1K_INPUT_CENTS)) / ONE_THOUSAND
    cached_cost = (Decimal(cached_tokens) * Decimal(PRICE_PER_1K_CACHED_INPUT_CENTS)) / ONE_THOUSAND
    output_cost = (Decimal(billable_output) * Decimal(PRICE_PER_1K_OUTPUT_CENTS)) / ONE_THOUSAND

    total = input_cost + cached_cost + output_cost
    # Round to the nearest whole cent. HALF_UP so small usage doesn't
    # silently round down to zero cost every time.
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
