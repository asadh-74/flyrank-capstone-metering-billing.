from ..database import get_connection


def get_tenant_by_api_key(api_key: str) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.*, p.name AS plan_name, p.api_call_limit,
                       p.ai_token_limit, p.monthly_price_cents
                FROM tenants t
                JOIN plans p ON p.id = t.plan_id
                WHERE t.api_key = %s
                """,
                (api_key,),
            )
            return cur.fetchone()


def get_tenant_by_id(tenant_id: int) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.*, p.name AS plan_name, p.api_call_limit,
                       p.ai_token_limit, p.monthly_price_cents
                FROM tenants t
                JOIN plans p ON p.id = t.plan_id
                WHERE t.id = %s
                """,
                (tenant_id,),
            )
            return cur.fetchone()


def create_tenant(name: str, api_key: str, plan_name: str = "free") -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM plans WHERE name = %s", (plan_name,))
            plan = cur.fetchone()
            cur.execute(
                """
                INSERT INTO tenants (name, api_key, plan_id)
                VALUES (%s, %s, %s)
                RETURNING *
                """,
                (name, api_key, plan["id"]),
            )
            row = cur.fetchone()
        conn.commit()
        return row


def get_plan_by_name(name: str) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM plans WHERE name = %s", (name,))
            return cur.fetchone()


def set_tenant_plan(tenant_id: int, plan_id: int) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tenants SET plan_id = %s WHERE id = %s",
                (plan_id, tenant_id),
            )
        conn.commit()


def set_tenant_stripe_customer_id(tenant_id: int, stripe_customer_id: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tenants SET stripe_customer_id = %s WHERE id = %s",
                (stripe_customer_id, tenant_id),
            )
        conn.commit()


def get_tenant_by_stripe_customer_id(stripe_customer_id: str) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tenants WHERE stripe_customer_id = %s",
                (stripe_customer_id,),
            )
            return cur.fetchone()
