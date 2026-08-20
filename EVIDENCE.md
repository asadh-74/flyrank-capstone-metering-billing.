# EVIDENCE

One proof per Definition-of-Done checkbox from the capstone brief's § 6.

## Verified independently on my own machine (Docker Desktop, Windows)

Full suite, run against my own local Docker containers:

    docker compose exec api pytest tests/ -v
    ======================== 27 passed, 2 warnings in 14.42s ========================

Forged webhook, live:

    curl.exe -i -X POST http://localhost:8000/webhooks/stripe -H "stripe-signature: t=123,v1=notarealsignature" -d '{"id":"evt_fake","type":"checkout.session.completed","data":{"object":{}}}'
    HTTP/1.1 400 Bad Request
    {"error":"Invalid webhook signature"}

Idempotency proof, live via /docs: same Idempotency-Key retried on
POST /generate returned "duplicate": true with the identical usage_event.id
(1000) both times — no new row created on retry.

Quota boundary proof, live via /docs: a tenant seeded at 999/1000 api_calls
— the 1000th call succeeded (201, exactly at the limit), the 1001st call
was rejected (429, "used 1000, limit 1000").

---

## METERING

### ☑ A billable action creates exactly one usage event, even under retries

`tests/test_idempotency.py::test_same_idempotency_key_records_exactly_one_event`

```
tests/test_idempotency.py::test_same_idempotency_key_records_exactly_one_event PASSED
```

Live proof — same `Idempotency-Key` sent twice, same `usage_event.id` (1000) both times:

```
$ curl -s -X POST http://127.0.0.1:8000/generate \
    -H "X-API-Key: demo_free_36dd8500e20e" \
    -H "Idempotency-Key: demo-key-1" \
    -d '{"type":"api_call"}'
{"duplicate":false,"usage_event":{"id":1000, ...}}

$ curl -s -X POST http://127.0.0.1:8000/generate \
    -H "X-API-Key: demo_free_36dd8500e20e" \
    -H "Idempotency-Key: demo-key-1" \
    -d '{"type":"api_call"}'
{"duplicate":true,"usage_event":{"id":1000, ...}}
```

### ☑ A test proves double-counting cannot happen

```
tests/test_idempotency.py::test_same_idempotency_key_records_exactly_one_event PASSED
tests/test_idempotency.py::test_different_idempotency_keys_record_separately PASSED
tests/test_idempotency.py::test_idempotency_holds_for_ai_token_events_too PASSED
tests/test_idempotency.py::test_retry_with_same_key_ignores_different_body PASSED
```

---

## QUOTAS

### ☑ Usage checked against plan; requests over limit rejected

### ☑ Responses carry correct status codes (429/402) with a clear message

Live proof — a tenant seeded at 999/1000 api_calls:

```
$ curl -i -X POST http://127.0.0.1:8000/generate \
    -H "X-API-Key: demo_boundary_f75366de3869" \
    -H "Idempotency-Key: boundary-call-1000" \
    -d '{"type":"api_call"}'
HTTP/1.1 201 Created
{"duplicate":false,"usage_event":{"id":1001, ...}}

$ curl -i -X POST http://127.0.0.1:8000/generate \
    -H "X-API-Key: demo_boundary_f75366de3869" \
    -H "Idempotency-Key: boundary-call-1001" \
    -d '{"type":"api_call"}'
HTTP/1.1 429 Too Many Requests
{"error":"api_call quota exceeded for this billing period. (used 1000, limit 1000)"}
```

Test proof — every boundary case, pinned:

```
tests/test_quota.py::test_just_under_quota_succeeds PASSED
tests/test_quota.py::test_exactly_at_quota_succeeds PASSED
tests/test_quota.py::test_over_quota_raises_quota_exceeded PASSED
tests/test_quota.py::test_quota_exceeded_does_not_record_an_event PASSED
tests/test_quota.py::test_ai_token_quota_enforced_independently_of_api_calls PASSED
tests/test_quota.py::test_ai_token_quota_over_limit_rejected PASSED
tests/test_quota.py::test_pro_plan_has_higher_limits PASSED
tests/test_quota.py::test_past_due_subscription_blocks_usage_with_payment_required PASSED
tests/test_quota.py::test_active_subscription_does_not_block_usage PASSED
```

---

## COST CALCULATION

### ☑ Monthly usage rolls up into a cost figure per tenant

Live `/usage` after one AI-tokens event (1000 input / 200 cached / 300 output / 100 reasoning):

```
$ curl -s http://127.0.0.1:8000/usage -H "X-API-Key: demo_pro_5caee6a61ab8"
{
    "plan": "pro",
    "api_calls": {"used": 0, "limit": 50000},
    "ai_tokens": {"used": 1400, "limit": 5000000},
    "cost_cents": {"plan_monthly": 2000, "ai_tokens": 105, "total": 2105}
}
```

### ☑ AI token pricing handles cached input, reasoning, and output correctly

### ☑ Pricing constants pinned in config, covered by tests

```
tests/test_pricing.py::test_pure_fresh_input_only PASSED
tests/test_pricing.py::test_cached_tokens_are_cheaper_than_fresh PASSED
tests/test_pricing.py::test_mixed_fresh_and_cached_input_priced_separately PASSED
tests/test_pricing.py::test_reasoning_tokens_billed_at_output_rate_not_free PASSED
tests/test_pricing.py::test_output_and_reasoning_tokens_combine_at_same_rate PASSED
tests/test_pricing.py::test_full_mix_of_all_four_categories PASSED
tests/test_pricing.py::test_zero_usage_costs_zero PASSED
tests/test_pricing.py::test_cached_tokens_cannot_exceed_input_tokens PASSED
tests/test_pricing.py::test_negative_tokens_rejected PASSED
tests/test_pricing.py::test_rounding_is_half_up_not_truncated PASSED
```

`test_full_mix_of_all_four_categories` is the one that matches the live
`/usage` call above exactly: 1000 input tokens (200 of them cached), 300
output, 100 reasoning → 105 cents, both in the pinned test and in the real
running server.

---

## STRIPE INTEGRATION

### ☑ Subscription checkout works end-to-end in Stripe test mode

**Not yet independently verified against a real Stripe account** — see
`BUILDLOG.md` for why, and the exact steps I still need to run
(`stripe listen`, a real Checkout with test card 4242 4242 4242 4242) before
this box is genuinely done. The code path (`app/routers/billing.py`) is
written and the webhook handler that would receive the resulting event is
fully tested below — only the live end-to-end Stripe round-trip is
outstanding.

### ☑ Webhooks verify signatures, ignore duplicate events, update tenant plan/status

Live proof — forged signature rejected:

```
$ curl -i -X POST http://127.0.0.1:8000/webhooks/stripe \
    -H "stripe-signature: t=123,v1=notarealsignature" \
    -d '{"id":"evt_fake","type":"checkout.session.completed","data":{"object":{}}}'
HTTP/1.1 400 Bad Request
{"error":"Invalid webhook signature"}
```

Test proof — valid signature flips plan, forged signature rejected, replay ignored, deletion reverts plan:

```
tests/test_webhooks.py::test_valid_webhook_flips_tenant_free_to_pro PASSED
tests/test_webhooks.py::test_forged_signature_rejected_with_400 PASSED
tests/test_webhooks.py::test_replayed_event_processed_only_once PASSED
tests/test_webhooks.py::test_subscription_deleted_reverts_tenant_to_free PASSED
```

`test_replayed_event_processed_only_once` posts the identical event twice;
the second response is `{"duplicate": true}` and the plan is unaffected by
the redelivery — that's the deduplication proof for Probe 4's second half.

---

## DATA MODEL, TESTS & DOCUMENTATION

### ☑ Schema includes tenants, plans, subscriptions, usage events; tenants isolated

See `app/schema.sql`. Every query in `app/repository/*.py` filters by
`tenant_id` — there is no query anywhere in the codebase that reads across
tenants.

### ☑ Tests cover: duplicate prevention, quota boundaries, cost calc, invalid/duplicate webhooks

Full suite, run against a real Postgres 16 instance:

```
$ pytest tests/ -v
tests/test_idempotency.py::test_same_idempotency_key_records_exactly_one_event PASSED
tests/test_idempotency.py::test_different_idempotency_keys_record_separately PASSED
tests/test_idempotency.py::test_idempotency_holds_for_ai_token_events_too PASSED
tests/test_idempotency.py::test_retry_with_same_key_ignores_different_body PASSED
tests/test_pricing.py::test_pure_fresh_input_only PASSED
tests/test_pricing.py::test_cached_tokens_are_cheaper_than_fresh PASSED
tests/test_pricing.py::test_mixed_fresh_and_cached_input_priced_separately PASSED
tests/test_pricing.py::test_reasoning_tokens_billed_at_output_rate_not_free PASSED
tests/test_pricing.py::test_output_and_reasoning_tokens_combine_at_same_rate PASSED
tests/test_pricing.py::test_full_mix_of_all_four_categories PASSED
tests/test_pricing.py::test_zero_usage_costs_zero PASSED
tests/test_pricing.py::test_cached_tokens_cannot_exceed_input_tokens PASSED
tests/test_pricing.py::test_negative_tokens_rejected PASSED
tests/test_pricing.py::test_rounding_is_half_up_not_truncated PASSED
tests/test_quota.py::test_just_under_quota_succeeds PASSED
tests/test_quota.py::test_exactly_at_quota_succeeds PASSED
tests/test_quota.py::test_over_quota_raises_quota_exceeded PASSED
tests/test_quota.py::test_quota_exceeded_does_not_record_an_event PASSED
tests/test_quota.py::test_ai_token_quota_enforced_independently_of_api_calls PASSED
tests/test_quota.py::test_ai_token_quota_over_limit_rejected PASSED
tests/test_quota.py::test_pro_plan_has_higher_limits PASSED
tests/test_quota.py::test_past_due_subscription_blocks_usage_with_payment_required PASSED
tests/test_quota.py::test_active_subscription_does_not_block_usage PASSED
tests/test_webhooks.py::test_valid_webhook_flips_tenant_free_to_pro PASSED
tests/test_webhooks.py::test_forged_signature_rejected_with_400 PASSED
tests/test_webhooks.py::test_replayed_event_processed_only_once PASSED
tests/test_webhooks.py::test_subscription_deleted_reverts_tenant_to_free PASSED

======================== 27 passed in 3.31s ========================
```

### ☐ README + architecture diagram + setup instructions

See `README.md`. Diagram included as ASCII (matches § 5 of the brief).

### ☐ Submission-pack files present

`README.md`, `capstone.yaml`, `EVIDENCE.md` (this file), `BUILDLOG.md`,
`.env.example` — all present at repo root.
