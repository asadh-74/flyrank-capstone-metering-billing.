# BUILDLOG

## Honest summary

This entire capstone — schema, service layer, routes, Stripe webhook
handler, pricing math, and the full test suite — was built end-to-end by
Claude (Anthropic), working from the capstone brief PDF, at my direction and
review. I did not write the code line-by-line myself. This log exists so
that's on the record rather than implied.

What that means practically: before the demo, I am going through
`app/meter_service.py`, `app/pricing.py`, and `app/routers/webhooks.py`
myself so I can actually explain the design decisions live, not just point
at working code. The brief is explicit that "the AI wrote it" is not an
acceptable answer to "explain these 3 lines" — so treat everything below as
what I need to be able to defend, not just what happened.

## Where AI helped

- **Whole-system architecture**: layered structure (routes -> service ->
  repository), matching the pattern from earlier assignments (A2/A3/W4).
- **Idempotency design**: the `UNIQUE(tenant_id, idempotency_key)` DB
  constraint plus `INSERT ... ON CONFLICT DO NOTHING ... RETURNING` pattern
  in `usage_events.py` — this is what actually makes double-counting
  impossible under concurrent retries, not just application-level checks.
- **Pricing math**: `app/pricing.py` — using `Decimal` throughout instead
  of floats, and the specific "cached tokens cheaper, reasoning billed as
  output" rule encoded as billable_input/billable_output before any
  multiplication.
- **Webhook dedup ordering**: mark-as-processed happens *after* successful
  side effects, not before — so a crash mid-processing leaves the event
  eligible for Stripe's automatic retry instead of silently swallowing it.
  This was a deliberate design choice, not the obvious first draft.
- **The full pytest suite**: pinned pricing tests, idempotency-under-retry
  tests, quota boundary tests (999/1000/1001), and webhook tests using a
  hand-rolled HMAC signature helper instead of mocking Stripe's SDK.

## Where I need to independently verify before the demo

- **Stripe Checkout + webhook flow has NOT been run against a real Stripe
  test account.** The webhook signature verification, dedup, and plan-sync
  logic is proven correct by `tests/test_webhooks.py` (which builds real
  HMAC signatures and posts them at the actual FastAPI route), but Probe 3
  in the brief ("complete a real Checkout, watch the webhook fire") requires
  *my own* Stripe test-mode account, price ID, and `stripe listen` session —
  none of which an AI assistant can create on my behalf. I still need to:
  1. Create a free Stripe account, toggle test mode.
  2. Create a "Pro" product/price, put the price ID in `.env`.
  3. Run `stripe listen --forward-to localhost:8000/webhooks/stripe`.
  4. Actually walk through Checkout with test card 4242 4242 4242 4242.
  5. Confirm `/usage` reflects the plan flip, and paste that transcript
     into `EVIDENCE.md` myself.
- **Whether 402 vs 429 semantics match what I'd have designed.** Current
  rule: 402 fires only when a Stripe subscription exists and its status is
  past_due/canceled/unpaid; 429 fires purely on quota math regardless of
  subscription state. I need to be able to explain why a Free-plan tenant
  (no subscription at all) never sees 402 — only 429 — under this design.
- **The rounding rule in `calculate_token_cost_cents`** (`ROUND_HALF_UP` on
  whole cents) — I should be able to say why half-up instead of
  half-to-even (banker's rounding) was chosen, and what it would take to
  change it.

## What I changed from the first draft

- Initial webhook dedup marked the event processed *before* running side
  effects; I (with Claude) reconsidered this — a crash between "mark
  processed" and "apply side effects" would have permanently lost that
  event with no retry path. Flipped the order.
- Initial quota-fill helper in the test suite called the full
  `meter_service.record_api_call()` in a loop 999+ times per test, which
  was correct but slow (each call does a real DB round-trip). Switched to a
  bulk `executemany` insert for the *filler* events, while the actual
  boundary assertion still goes through the real service call.
