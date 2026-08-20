from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, HTTPException, Request

from .. import config
from ..repository import subscriptions as sub_repo
from ..repository import tenants as tenant_repo
from ..repository import webhook_events as webhook_repo

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _unix_to_dt(ts) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _resolve_tenant_id(obj: dict) -> int | None:
    metadata = obj.get("metadata") or {}
    if metadata.get("tenant_id"):
        return int(metadata["tenant_id"])
    if obj.get("client_reference_id"):
        return int(obj["client_reference_id"])
    return None


@router.post("/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    # Payment truth lives at Stripe. We never trust a webhook body unless
    # its signature checks out against our webhook secret -- anyone who
    # can reach this URL can POST arbitrary JSON, so signature
    # verification is the entire security boundary here.
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, config.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_id = event["id"]
    event_type = event["type"]
    obj = event["data"]["object"]

    # A replayed event (Stripe redelivers on timeout, or someone reposts a
    # captured payload) is a no-op: we've already applied its side effects.
    if webhook_repo.has_processed(event_id):
        return {"received": True, "duplicate": True}

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(obj)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(obj)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(obj)
    # Any other event type: acknowledge and ignore. We only mark it
    # processed and move on -- no error, nothing to sync.

    webhook_repo.mark_processed(event_id, event_type)
    return {"received": True, "duplicate": False}


def _handle_checkout_completed(session: dict) -> None:
    tenant_id = _resolve_tenant_id(session)
    if tenant_id is None:
        return  # can't attribute this session to a tenant; nothing to do

    pro_plan = tenant_repo.get_plan_by_name("pro")
    sub_repo.upsert_subscription(
        tenant_id=tenant_id,
        stripe_subscription_id=session["subscription"],
        status="active",
        plan_id=pro_plan["id"],
    )
    tenant_repo.set_tenant_plan(tenant_id, pro_plan["id"])


def _handle_subscription_updated(subscription: dict) -> None:
    tenant = tenant_repo.get_tenant_by_stripe_customer_id(subscription["customer"])
    if tenant is None:
        return

    status = subscription["status"]
    pro_plan = tenant_repo.get_plan_by_name("pro")

    sub_repo.upsert_subscription(
        tenant_id=tenant["id"],
        stripe_subscription_id=subscription["id"],
        status=status,
        plan_id=pro_plan["id"],
        current_period_start=_unix_to_dt(subscription.get("current_period_start")),
        current_period_end=_unix_to_dt(subscription.get("current_period_end")),
    )

    if status == "active":
        tenant_repo.set_tenant_plan(tenant["id"], pro_plan["id"])
    # past_due / unpaid: leave the plan as-is; MeterService blocks usage
    # via the subscription status check, which is the more honest 402.


def _handle_subscription_deleted(subscription: dict) -> None:
    tenant = tenant_repo.get_tenant_by_stripe_customer_id(subscription["customer"])
    if tenant is None:
        return

    free_plan = tenant_repo.get_plan_by_name("free")
    sub_repo.set_subscription_status(subscription["id"], "canceled")
    tenant_repo.set_tenant_plan(tenant["id"], free_plan["id"])
