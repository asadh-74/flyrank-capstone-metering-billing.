import uuid

from app import meter_service
from app.repository import usage_events as usage_repo


def test_same_idempotency_key_records_exactly_one_event(free_tenant):
    key = f"idem-{uuid.uuid4().hex}"

    first = meter_service.record_api_call(free_tenant, key)
    second = meter_service.record_api_call(free_tenant, key)
    third = meter_service.record_api_call(free_tenant, key)

    assert first.was_new is True
    assert second.was_new is False
    assert third.was_new is False

    # Same underlying row every time.
    assert first.event["id"] == second.event["id"] == third.event["id"]

    usage = usage_repo.sum_usage_this_month(free_tenant["id"], "api_call")
    assert usage["used"] == 1  # NOT 3


def test_different_idempotency_keys_record_separately(free_tenant):
    key1 = f"idem-{uuid.uuid4().hex}"
    key2 = f"idem-{uuid.uuid4().hex}"

    meter_service.record_api_call(free_tenant, key1)
    meter_service.record_api_call(free_tenant, key2)

    usage = usage_repo.sum_usage_this_month(free_tenant["id"], "api_call")
    assert usage["used"] == 2


def test_idempotency_holds_for_ai_token_events_too(free_tenant):
    key = f"idem-{uuid.uuid4().hex}"

    first = meter_service.record_ai_tokens(
        free_tenant, key, input_tokens=1000, cached_tokens=0, output_tokens=500, reasoning_tokens=0
    )
    second = meter_service.record_ai_tokens(
        free_tenant, key, input_tokens=1000, cached_tokens=0, output_tokens=500, reasoning_tokens=0
    )

    assert first.was_new is True
    assert second.was_new is False
    assert first.event["id"] == second.event["id"]

    usage = usage_repo.sum_usage_this_month(free_tenant["id"], "ai_tokens")
    assert usage["used"] == 1500  # NOT 3000 -- one event's worth, not two


def test_retry_with_same_key_ignores_different_body(free_tenant):
    """A genuinely defensive property: if a client retries with the same
    idempotency key but (incorrectly) sends a different payload, we still
    return the ORIGINAL recorded result rather than double-processing or
    silently overwriting it. The idempotency key is authoritative."""
    key = f"idem-{uuid.uuid4().hex}"

    first = meter_service.record_ai_tokens(
        free_tenant, key, input_tokens=1000, cached_tokens=0, output_tokens=0, reasoning_tokens=0
    )
    # Same key, wildly different token counts on the "retry".
    second = meter_service.record_ai_tokens(
        free_tenant, key, input_tokens=999999, cached_tokens=0, output_tokens=999999, reasoning_tokens=0
    )

    assert second.was_new is False
    assert second.event["input_tokens"] == first.event["input_tokens"] == 1000
