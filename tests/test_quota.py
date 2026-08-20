import uuid

import pytest

from app import meter_service


def _use_n_api_calls(tenant, n):
    """Bulk-seed n api_call usage events directly (bypassing meter_service)
    so quota-boundary tests aren't bottlenecked by n sequential DB
    round-trips through the full idempotency + quota check path. The
    boundary call itself, which is what each test actually asserts on,
    still goes through meter_service.record_api_call for a real check."""
    from app.database import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO usage_events (tenant_id, idempotency_key, type, quantity)
                VALUES (%s, %s, 'api_call', 1)
                """,
                [(tenant["id"], f"fill-{i}-{uuid.uuid4().hex[:8]}") for i in range(n)],
            )
        conn.commit()


def test_just_under_quota_succeeds(free_tenant):
    # free plan limit is 1000. Use 999, the 1000th should still succeed.
    _use_n_api_calls(free_tenant, 999)
    result = meter_service.record_api_call(free_tenant, f"boundary-{uuid.uuid4().hex}")
    assert result.was_new is True


def test_exactly_at_quota_succeeds(free_tenant):
    # The 1000th call lands exactly at the limit -- documented rule: the
    # boundary call itself is allowed (used + 1 <= limit).
    _use_n_api_calls(free_tenant, 999)
    boundary_call = meter_service.record_api_call(free_tenant, f"exact-{uuid.uuid4().hex}")
    assert boundary_call.was_new is True


def test_over_quota_raises_quota_exceeded(free_tenant):
    _use_n_api_calls(free_tenant, 1000)  # now exactly at the limit
    with pytest.raises(meter_service.QuotaExceeded) as exc_info:
        meter_service.record_api_call(free_tenant, f"over-{uuid.uuid4().hex}")
    assert exc_info.value.used == 1000
    assert exc_info.value.limit == 1000


def test_quota_exceeded_does_not_record_an_event(free_tenant):
    _use_n_api_calls(free_tenant, 1000)
    key = f"rejected-{uuid.uuid4().hex}"
    with pytest.raises(meter_service.QuotaExceeded):
        meter_service.record_api_call(free_tenant, key)

    from app.repository import usage_events as usage_repo

    assert usage_repo.find_by_idempotency_key(free_tenant["id"], key) is None


def test_ai_token_quota_enforced_independently_of_api_calls(free_tenant):
    # Using up the api_call quota should not affect the ai_tokens quota.
    _use_n_api_calls(free_tenant, 1000)
    # free plan ai_token_limit is 100000 -- well within reach.
    result = meter_service.record_ai_tokens(
        free_tenant,
        f"tokens-{uuid.uuid4().hex}",
        input_tokens=1000,
        cached_tokens=0,
        output_tokens=500,
        reasoning_tokens=0,
    )
    assert result.was_new is True


def test_ai_token_quota_over_limit_rejected(free_tenant):
    with pytest.raises(meter_service.QuotaExceeded):
        meter_service.record_ai_tokens(
            free_tenant,
            f"huge-{uuid.uuid4().hex}",
            input_tokens=200000,  # over the 100000 free-plan limit
            cached_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
        )


def test_pro_plan_has_higher_limits(pro_tenant):
    # 2000 api calls would blow the free plan's 1000 limit but is nowhere
    # near the pro plan's 50000.
    _use_n_api_calls(pro_tenant, 2000)
    result = meter_service.record_api_call(pro_tenant, f"pro-{uuid.uuid4().hex}")
    assert result.was_new is True


def test_past_due_subscription_blocks_usage_with_payment_required(free_tenant):
    from app.repository import subscriptions as sub_repo
    from app.repository import tenants as tenant_repo

    pro_plan = tenant_repo.get_plan_by_name("pro")
    sub_repo.upsert_subscription(
        tenant_id=free_tenant["id"],
        stripe_subscription_id=f"sub_test_{uuid.uuid4().hex}",
        status="past_due",
        plan_id=pro_plan["id"],
    )

    with pytest.raises(meter_service.PaymentRequired):
        meter_service.record_api_call(free_tenant, f"blocked-{uuid.uuid4().hex}")


def test_active_subscription_does_not_block_usage(free_tenant):
    from app.repository import subscriptions as sub_repo
    from app.repository import tenants as tenant_repo

    pro_plan = tenant_repo.get_plan_by_name("pro")
    sub_repo.upsert_subscription(
        tenant_id=free_tenant["id"],
        stripe_subscription_id=f"sub_test_{uuid.uuid4().hex}",
        status="active",
        plan_id=pro_plan["id"],
    )

    result = meter_service.record_api_call(free_tenant, f"allowed-{uuid.uuid4().hex}")
    assert result.was_new is True
