"""
Seed demo data: one Free-plan tenant sitting one call under its quota
(ready to demonstrate the 429 boundary), and one fresh Pro-plan tenant.

Run: python -m scripts.seed
"""
import uuid

from app.database import get_connection, init_db
from app.repository import tenants as tenant_repo


def seed():
    init_db()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM plans WHERE name = 'free'")
            free_plan = cur.fetchone()

    # Tenant 1: Free plan, fresh.
    api_key_1 = f"demo_free_{uuid.uuid4().hex[:12]}"
    tenant1 = tenant_repo.create_tenant("Acme Free Co", api_key_1, "free")
    print(f"Created FREE tenant: id={tenant1['id']}  api_key={api_key_1}")

    # Tenant 2: Free plan, seeded to 999/1000 api_calls so the very next
    # call sits exactly at the boundary and the one after triggers 429.
    api_key_2 = f"demo_boundary_{uuid.uuid4().hex[:12]}"
    tenant2 = tenant_repo.create_tenant("Boundary Test Co", api_key_2, "free")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO usage_events (tenant_id, idempotency_key, type, quantity)
                VALUES (%s, %s, 'api_call', 1)
                ON CONFLICT DO NOTHING
                """,
                [(tenant2["id"], f"seed-{i}-{uuid.uuid4().hex[:8]}") for i in range(999)],
            )
        conn.commit()
    print(
        f"Created BOUNDARY tenant: id={tenant2['id']}  api_key={api_key_2}  "
        f"(999/1000 api_calls used -- next call hits the boundary, the one after that gets 429)"
    )

    # Tenant 3: Pro plan, for testing token pricing / higher limits directly.
    api_key_3 = f"demo_pro_{uuid.uuid4().hex[:12]}"
    tenant3 = tenant_repo.create_tenant("Acme Pro Co", api_key_3, "pro")
    print(f"Created PRO tenant: id={tenant3['id']}  api_key={api_key_3}")


if __name__ == "__main__":
    seed()
