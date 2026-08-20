import hashlib
import hmac
import json
import time
import uuid

from fastapi.testclient import TestClient

from app.config import STRIPE_WEBHOOK_SECRET
from app.main import app
from app.repository import tenants as tenant_repo

client = TestClient(app)


def _sign(payload_bytes: bytes, secret: str, timestamp: int | None = None) -> str:
    timestamp = timestamp or int(time.time())
    signed_payload = f"{timestamp}.{payload_bytes.decode()}"
    signature = hmac.new(
        secret.encode(), signed_payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def _post_webhook(event: dict, secret: str = STRIPE_WEBHOOK_SECRET):
    payload = json.dumps(event).encode()
    sig = _sign(payload, secret)
    return client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": sig, "content-type": "application/json"},
    )


def _checkout_completed_event(tenant_id: int, subscription_id: str) -> dict:
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_{uuid.uuid4().hex}",
                "client_reference_id": str(tenant_id),
                "subscription": subscription_id,
                "customer": f"cus_{uuid.uuid4().hex}",
                "metadata": {"tenant_id": str(tenant_id)},
            }
        },
    }


def test_valid_webhook_flips_tenant_free_to_pro(free_tenant):
    assert free_tenant["plan_name"] == "free"

    sub_id = f"sub_{uuid.uuid4().hex}"
    event = _checkout_completed_event(free_tenant["id"], sub_id)

    resp = _post_webhook(event)
    assert resp.status_code == 200
    assert resp.json()["duplicate"] is False

    updated = tenant_repo.get_tenant_by_id(free_tenant["id"])
    assert updated["plan_name"] == "pro"


def test_forged_signature_rejected_with_400(free_tenant):
    sub_id = f"sub_{uuid.uuid4().hex}"
    event = _checkout_completed_event(free_tenant["id"], sub_id)

    resp = _post_webhook(event, secret="whsec_totally_wrong_secret")
    assert resp.status_code == 400

    # Nothing changed.
    updated = tenant_repo.get_tenant_by_id(free_tenant["id"])
    assert updated["plan_name"] == "free"


def test_replayed_event_processed_only_once(free_tenant):
    sub_id = f"sub_{uuid.uuid4().hex}"
    event = _checkout_completed_event(free_tenant["id"], sub_id)

    first = _post_webhook(event)
    assert first.json()["duplicate"] is False

    # Same event id, sent again -- Stripe does this on redelivery/timeout.
    second = _post_webhook(event)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True

    # Still just "pro" -- no double-application side effects to observe,
    # but the explicit duplicate flag proves the second delivery took the
    # dedup short-circuit rather than reprocessing.
    updated = tenant_repo.get_tenant_by_id(free_tenant["id"])
    assert updated["plan_name"] == "pro"


def test_subscription_deleted_reverts_tenant_to_free(pro_tenant):
    from app.repository import subscriptions as sub_repo

    customer_id = f"cus_{uuid.uuid4().hex}"
    tenant_repo.set_tenant_stripe_customer_id(pro_tenant["id"], customer_id)

    sub_id = f"sub_{uuid.uuid4().hex}"
    pro_plan = tenant_repo.get_plan_by_name("pro")
    sub_repo.upsert_subscription(
        tenant_id=pro_tenant["id"],
        stripe_subscription_id=sub_id,
        status="active",
        plan_id=pro_plan["id"],
    )

    event = {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": sub_id,
                "customer": customer_id,
                "status": "canceled",
            }
        },
    }
    resp = _post_webhook(event)
    assert resp.status_code == 200

    updated = tenant_repo.get_tenant_by_id(pro_tenant["id"])
    assert updated["plan_name"] == "free"
