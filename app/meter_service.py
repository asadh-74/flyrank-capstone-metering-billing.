"""
MeterService: the one place that decides whether a billable action is
allowed, records it exactly once, and prices it.

Kept deliberately separate from app/routers/usage.py — routes translate
HTTP <-> this service; this service knows nothing about FastAPI. Swap the
transport (HTTP -> gRPC -> CLI) and this file doesn't change.
"""
from dataclasses import dataclass

from .pricing import calculate_token_cost_cents
from .repository import subscriptions as sub_repo
from .repository import usage_events as usage_repo


class PaymentRequired(Exception):
    """Subscription is inactive (past_due / canceled / unpaid) -> 402."""


class QuotaExceeded(Exception):
    """Plan quota would be exceeded by this request -> 429."""

    def __init__(self, message: str, used: int, limit: int):
        super().__init__(message)
        self.used = used
        self.limit = limit


@dataclass
class MeterResult:
    event: dict
    was_new: bool  # False means this was a duplicate retry


def _subscription_blocks_usage(tenant: dict) -> bool:
    sub = sub_repo.get_active_subscription_for_tenant(tenant["id"])
    if sub is None:
        return False  # no Stripe subscription yet -> free plan, always fine
    return sub["status"] in ("past_due", "canceled", "unpaid")


def record_api_call(tenant: dict, idempotency_key: str) -> MeterResult:
    return _record(
        tenant=tenant,
        idempotency_key=idempotency_key,
        event_type="api_call",
        quantity=1,
        input_tokens=0,
        cached_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
        cost_cents=0,
        limit=tenant["api_call_limit"],
    )


def record_ai_tokens(
    tenant: dict,
    idempotency_key: str,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
) -> MeterResult:
    cost_cents = calculate_token_cost_cents(
        input_tokens, cached_tokens, output_tokens, reasoning_tokens
    )
    total_tokens = input_tokens + output_tokens + reasoning_tokens
    return _record(
        tenant=tenant,
        idempotency_key=idempotency_key,
        event_type="ai_tokens",
        quantity=total_tokens,
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cost_cents=cost_cents,
        limit=tenant["ai_token_limit"],
    )


def _record(
    tenant: dict,
    idempotency_key: str,
    event_type: str,
    quantity: int,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    cost_cents: int,
    limit: int,
) -> MeterResult:
    # 1. Payment/subscription health check first -- a tenant whose payment
    #    failed shouldn't be able to keep using the service at all,
    #    regardless of quota headroom.
    if _subscription_blocks_usage(tenant):
        raise PaymentRequired("Subscription payment is past due. Update billing to continue.")

    # 2. Idempotency check -- a retried request with the same key returns
    #    the ORIGINAL result. No new row, no new charge, no quota re-check.
    existing = usage_repo.find_by_idempotency_key(tenant["id"], idempotency_key)
    if existing is not None:
        return MeterResult(event=existing, was_new=False)

    # 3. Quota check -- only for genuinely new requests.
    current = usage_repo.sum_usage_this_month(tenant["id"], event_type)
    used = current["used"]
    request_amount = quantity if event_type == "api_call" else (input_tokens + output_tokens + reasoning_tokens)
    if used + request_amount > limit:
        raise QuotaExceeded(
            f"{event_type} quota exceeded for this billing period.",
            used=used,
            limit=limit,
        )

    # 4. Record exactly once. The DB's UNIQUE constraint is the final
    #    backstop against a race between two concurrent retries.
    row, was_new = usage_repo.insert_usage_event(
        tenant_id=tenant["id"],
        idempotency_key=idempotency_key,
        event_type=event_type,
        quantity=quantity,
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cost_cents=cost_cents,
    )
    return MeterResult(event=row, was_new=was_new)
