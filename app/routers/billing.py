import stripe
from fastapi import APIRouter, Depends, HTTPException

from .. import config
from ..deps import get_current_tenant
from ..repository import tenants as tenant_repo
from ..schemas import CheckoutRequest

router = APIRouter(prefix="/billing", tags=["billing"])

stripe.api_key = config.STRIPE_SECRET_KEY


@router.post("/checkout")
def create_checkout_session(
    body: CheckoutRequest,
    tenant: dict = Depends(get_current_tenant),
):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=500,
            detail="STRIPE_SECRET_KEY is not configured on the server",
        )
    if not config.STRIPE_PRO_PRICE_ID:
        raise HTTPException(
            status_code=500,
            detail="STRIPE_PRO_PRICE_ID is not configured on the server",
        )

    customer_id = tenant.get("stripe_customer_id")
    if not customer_id:
        customer = stripe.Customer.create(
            name=tenant["name"],
            metadata={"tenant_id": str(tenant["id"])},
        )
        customer_id = customer["id"]
        tenant_repo.set_tenant_stripe_customer_id(tenant["id"], customer_id)

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        client_reference_id=str(tenant["id"]),
        line_items=[{"price": config.STRIPE_PRO_PRICE_ID, "quantity": 1}],
        success_url=config.CHECKOUT_SUCCESS_URL,
        cancel_url=config.CHECKOUT_CANCEL_URL,
        metadata={"tenant_id": str(tenant["id"])},
    )

    return {"checkout_url": session["url"], "session_id": session["id"]}
