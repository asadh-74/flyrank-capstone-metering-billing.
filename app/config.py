"""
All configuration in one place. Nothing here is a secret except the two
Stripe values, and those come from the environment, never hardcoded.
"""
import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID", "")

CHECKOUT_SUCCESS_URL = os.environ.get(
    "CHECKOUT_SUCCESS_URL", "http://localhost:8000/billing/success"
)
CHECKOUT_CANCEL_URL = os.environ.get(
    "CHECKOUT_CANCEL_URL", "http://localhost:8000/billing/cancel"
)

PORT = int(os.environ.get("PORT", 8000))

# ---------------------------------------------------------------------------
# Pricing constants — pinned here and covered by tests/test_pricing.py.
# All prices are in integer CENTS per 1,000 tokens. Never floats.
#
# Modeled on FlyRank's chat-pricing.config.ts: cached input tokens are
# cheaper than fresh input tokens, and reasoning tokens are billed at the
# *output* rate, not as a separate category and not for free.
# ---------------------------------------------------------------------------
PRICE_PER_1K_INPUT_CENTS = 50        # fresh (non-cached) input tokens
PRICE_PER_1K_CACHED_INPUT_CENTS = 25  # cached input tokens — half price
PRICE_PER_1K_OUTPUT_CENTS = 150       # output tokens AND reasoning tokens
