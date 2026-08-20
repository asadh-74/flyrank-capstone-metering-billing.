import os
import uuid

import pytest

os.environ.setdefault("DATABASE_URL", "postgres://postgres:devpass@localhost:5432/billing_test")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_dummy")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_dummy_secret")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_dummy")

from app.database import get_connection, init_db  # noqa: E402
from app.repository import tenants as tenant_repo  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _setup_schema():
    init_db()
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    """Wipe usage-affecting tables before every test so tests don't leak
    state into each other (e.g. one test's quota usage bleeding into the
    next test's boundary check)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE processed_webhook_events")
            cur.execute("TRUNCATE usage_events")
            cur.execute("TRUNCATE subscriptions")
            cur.execute("TRUNCATE tenants RESTART IDENTITY CASCADE")
        conn.commit()
    yield


@pytest.fixture
def free_tenant():
    api_key = f"test_{uuid.uuid4().hex}"
    tenant_repo.create_tenant("Test Tenant", api_key, "free")
    return tenant_repo.get_tenant_by_api_key(api_key)


@pytest.fixture
def pro_tenant():
    api_key = f"test_{uuid.uuid4().hex}"
    tenant_repo.create_tenant("Test Pro Tenant", api_key, "pro")
    return tenant_repo.get_tenant_by_api_key(api_key)
