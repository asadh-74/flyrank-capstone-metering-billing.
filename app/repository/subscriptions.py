from ..database import get_connection


def upsert_subscription(
    tenant_id: int,
    stripe_subscription_id: str,
    status: str,
    plan_id: int,
    current_period_start=None,
    current_period_end=None,
) -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO subscriptions (
                    tenant_id, stripe_subscription_id, status, plan_id,
                    current_period_start, current_period_end
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (stripe_subscription_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    plan_id = EXCLUDED.plan_id,
                    current_period_start = EXCLUDED.current_period_start,
                    current_period_end = EXCLUDED.current_period_end,
                    updated_at = now()
                RETURNING *
                """,
                (
                    tenant_id,
                    stripe_subscription_id,
                    status,
                    plan_id,
                    current_period_start,
                    current_period_end,
                ),
            )
            row = cur.fetchone()
        conn.commit()
        return row


def get_subscription_by_stripe_id(stripe_subscription_id: str) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM subscriptions WHERE stripe_subscription_id = %s",
                (stripe_subscription_id,),
            )
            return cur.fetchone()


def get_active_subscription_for_tenant(tenant_id: int) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM subscriptions
                WHERE tenant_id = %s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (tenant_id,),
            )
            return cur.fetchone()


def set_subscription_status(stripe_subscription_id: str, status: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE subscriptions SET status = %s, updated_at = now()
                WHERE stripe_subscription_id = %s
                """,
                (status, stripe_subscription_id),
            )
        conn.commit()
