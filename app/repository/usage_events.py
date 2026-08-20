from ..database import get_connection


def find_by_idempotency_key(tenant_id: int, idempotency_key: str) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM usage_events
                WHERE tenant_id = %s AND idempotency_key = %s
                """,
                (tenant_id, idempotency_key),
            )
            return cur.fetchone()


def insert_usage_event(
    tenant_id: int,
    idempotency_key: str,
    event_type: str,
    quantity: int,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    cost_cents: int,
) -> tuple[dict, bool]:
    """Insert a usage event. Returns (row, was_newly_created).

    The UNIQUE(tenant_id, idempotency_key) constraint on the table is the
    real safety net here — even two concurrent requests carrying the same
    idempotency key can't both win the insert. ON CONFLICT DO NOTHING makes
    the loser of that race simply return "nothing happened", and we then
    fetch the winner's row and hand back the *same* result to both callers.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usage_events (
                    tenant_id, idempotency_key, type, quantity,
                    input_tokens, cached_tokens, output_tokens,
                    reasoning_tokens, cost_cents
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                RETURNING *
                """,
                (
                    tenant_id,
                    idempotency_key,
                    event_type,
                    quantity,
                    input_tokens,
                    cached_tokens,
                    output_tokens,
                    reasoning_tokens,
                    cost_cents,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    if row is not None:
        return row, True

    # Someone else (or an earlier attempt in this same request) already
    # inserted this key. Return their row instead of erroring.
    existing = find_by_idempotency_key(tenant_id, idempotency_key)
    return existing, False


def sum_usage_this_month(tenant_id: int, event_type: str) -> dict:
    """Returns quantity used (api_call: count of calls; ai_tokens: total
    billable tokens) plus total cost_cents, for the current calendar month."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            if event_type == "api_call":
                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(quantity), 0) AS used,
                        COALESCE(SUM(cost_cents), 0) AS cost_cents
                    FROM usage_events
                    WHERE tenant_id = %s
                      AND type = 'api_call'
                      AND date_trunc('month', created_at) = date_trunc('month', now())
                    """,
                    (tenant_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(input_tokens + output_tokens + reasoning_tokens), 0) AS used,
                        COALESCE(SUM(cost_cents), 0) AS cost_cents
                    FROM usage_events
                    WHERE tenant_id = %s
                      AND type = 'ai_tokens'
                      AND date_trunc('month', created_at) = date_trunc('month', now())
                    """,
                    (tenant_id,),
                )
            return cur.fetchone()
