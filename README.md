# Usage Metering & Billing Engine

FlyRank Internship — Backend Track Capstone. Meters billable usage exactly
once under retries, enforces plan quotas honestly, prices AI tokens using
real-world pricing rules, and keeps tenant plans in sync with Stripe through
signature-verified, deduplicated webhooks.

## What this is

Two plans (Free / Pro), two usage types (API calls / AI tokens), one
billable endpoint (`POST /generate`). Every hard part here is a correctness
puzzle — idempotency under retries, exact quota boundaries, and money math
that never touches a float — not an infrastructure one.

## Architecture

```
Client ──► POST /generate  (X-API-Key, Idempotency-Key header)
             │
             ▼
        MeterService.record(tenant, type, payload, idempotency_key)
             │
             ├─ subscription past_due/canceled/unpaid? ──► 402 Payment Required
             │
             ├─ duplicate idempotency_key? ──► return the ORIGINAL result
             │                                  (no new usage_event, no re-check)
             │
             ├─ over plan quota? ──► 429 Too Many Requests (used/limit in body)
             │
             └─ record usage_event (UNIQUE(tenant_id, idempotency_key)
                enforced at the DB level, not just in application code)
                     │
                     ▼
             pricing.calculate_token_cost_cents()  (ai_tokens only)


Client ──► GET /usage  ──► rollup(usage_events for current month)
                            → { api_calls, ai_tokens, cost_cents }


Client ──► POST /billing/checkout ──► Stripe Checkout Session (test mode)
                                        │
                                   customer pays with test card
                                        │
                                        ▼
Stripe ──signed webhook──► POST /webhooks/stripe
                            ├─ verify signature (forged → 400)
                            ├─ already processed this event id? → no-op, 200
                            ├─ apply side effect (upsert subscription,
                            │  flip tenant plan)
                            └─ mark event id processed (AFTER success, so a
                               crash mid-processing leaves it retryable)
```

Layers: `app/routers/*` (HTTP only) → `app/meter_service.py` (business
rules, framework-agnostic) → `app/repository/*` (the only code that touches
SQL). Swap Postgres for something else and only `repository/` changes.

## Setup

1. **Docker + Postgres, one command:**
   ```bash
   cp .env.example .env
   docker compose up --build
   ```
   The API will be live at `http://localhost:8000` once Postgres reports
   healthy. Schema is created automatically on startup (`app/schema.sql` —
   every statement is idempotent, safe to run every boot).

2. **Seed demo tenants** (one fresh Free tenant, one Free tenant sitting at
   999/1000 api_calls for the quota-boundary demo, one Pro tenant):
   ```bash
   docker compose exec api python -m scripts.seed
   ```
   This prints three `X-API-Key` values — use them in the calls below.

3. **Stripe test mode** (only needed for `/billing/checkout` and the
   webhook flow — `/generate` and `/usage` work without it):
   - Create a free account at [stripe.com](https://stripe.com), toggle
     **Test mode**.
   - Get your test **Secret key** from Developers → API keys.
   - Create a "Pro" product with a monthly recurring Price in test mode;
     copy its Price ID.
   - Install the [Stripe CLI](https://stripe.com/docs/stripe-cli), then:
     ```bash
     stripe listen --forward-to localhost:8000/webhooks/stripe
     ```
     This prints a `whsec_...` value — put it in `.env` as
     `STRIPE_WEBHOOK_SECRET`.
   - Put your secret key and Price ID in `.env` too, then restart
     `docker compose up`.

4. **Run the tests:**
   ```bash
   docker compose exec api pytest tests/ -v
   ```
   27 tests, all passing against a real Postgres instance — see
   `EVIDENCE.md` for the full transcript.

## API reference

| Method | Route | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | liveness check |
| POST | `/generate` | `X-API-Key` + `Idempotency-Key` header | the one billable action |
| GET | `/usage` | `X-API-Key` | current-month rollup: used/limit/cost per type |
| POST | `/billing/checkout` | `X-API-Key` | creates a Stripe Checkout session for the Pro plan |
| POST | `/webhooks/stripe` | Stripe signature | receives `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted` |

**Status codes:** `201` new usage event, `200` idempotent replay / reads,
`400` invalid input or bad webhook signature, `401` missing/invalid API
key, `402` subscription payment required, `429` quota exceeded.

## Example

```bash
# A billable API call. Idempotency-Key is required on every /generate call.
curl -i -X POST http://localhost:8000/generate \
  -H "X-API-Key: <your seeded key>" \
  -H "Idempotency-Key: unique-per-attempt" \
  -H "Content-Type: application/json" \
  -d '{"type": "api_call"}'

# The identical retry returns the SAME usage_event.id, "duplicate": true —
# it is not recorded twice.
curl -i -X POST http://localhost:8000/generate \
  -H "X-API-Key: <your seeded key>" \
  -H "Idempotency-Key: unique-per-attempt" \
  -H "Content-Type: application/json" \
  -d '{"type": "api_call"}'

# AI-token usage with the real pricing rules.
curl -i -X POST http://localhost:8000/generate \
  -H "X-API-Key: <your seeded key>" \
  -H "Idempotency-Key: token-call-1" \
  -H "Content-Type: application/json" \
  -d '{"type": "ai_tokens", "input_tokens": 1000, "cached_tokens": 200, "output_tokens": 300, "reasoning_tokens": 100}'

curl http://localhost:8000/usage -H "X-API-Key: <your seeded key>"
```

## Pricing rules (pinned in `app/config.py`, tested in `tests/test_pricing.py`)

- Fresh input tokens: **50¢ per 1,000**
- Cached input tokens (subset of input_tokens, billed separately): **25¢ per 1,000**
- Output tokens **and** reasoning tokens (reasoning is billed at the output
  rate, not free, not a separate category): **150¢ per 1,000**
- All math done in `Decimal`, rounded HALF_UP to the nearest cent. No float
  ever touches a money value.

## Limitations (honest, on purpose)

- **Stripe Checkout has not been run against a real Stripe test account**
  by me yet — see `BUILDLOG.md` and `EVIDENCE.md` for exactly what's
  verified (the webhook handler, fully, via hand-signed test requests) vs.
  what still needs a live `stripe listen` session before the demo.
- **No invoicing, proration, or overage billing** — explicitly out of core
  scope per the brief's § 7 "Realistic scope."
- **Webhook dedup has a narrow race window**: two *simultaneous* deliveries
  of the same event, both arriving before either finishes processing, could
  both apply side effects (both are idempotent upserts, so the end state is
  still correct — just slightly wasted work, not a correctness bug).
- **AI tokens are simulated** — this service meters numbers a client sends,
  it never calls an actual model. That's explicitly allowed by the brief.

## Project structure

```
app/
  config.py           pricing constants + env vars, all pinned in one place
  pricing.py           token cost math (Decimal, no floats)
  database.py            connection + schema init
  schema.sql               tenants / plans / subscriptions / usage_events
  meter_service.py           idempotency + quota orchestration (HTTP-agnostic)
  deps.py                       X-API-Key -> tenant lookup
  schemas.py                      Pydantic request bodies
  routers/
    usage.py                        POST /generate, GET /usage
    billing.py                       POST /billing/checkout
    webhooks.py                       POST /webhooks/stripe
  repository/
    tenants.py, usage_events.py, subscriptions.py, webhook_events.py
tests/
  test_pricing.py, test_idempotency.py, test_quota.py, test_webhooks.py
scripts/
  seed.py               demo tenants, one pre-loaded to the quota boundary
```
