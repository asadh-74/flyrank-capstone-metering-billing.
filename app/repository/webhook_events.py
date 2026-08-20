from ..database import get_connection


def has_processed(event_id: str) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM processed_webhook_events WHERE event_id = %s",
                (event_id,),
            )
            return cur.fetchone() is not None


def mark_processed(event_id: str, event_type: str) -> None:
    """Called AFTER side effects succeed, not before. If processing crashes
    partway, the event stays unmarked and Stripe's automatic retry will
    hit it again -- safe, because every side effect below (subscription
    upsert, plan update) is itself idempotent under ON CONFLICT."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO processed_webhook_events (event_id, type)
                VALUES (%s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (event_id, event_type),
            )
        conn.commit()
