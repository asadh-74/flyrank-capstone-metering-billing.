from fastapi import APIRouter, Depends, Header, HTTPException

from ..deps import get_current_tenant
from ..meter_service import PaymentRequired, QuotaExceeded
from ..meter_service import record_ai_tokens, record_api_call
from ..repository import usage_events as usage_repo
from ..schemas import GenerateRequest

router = APIRouter(tags=["usage"])


def _serialize_event(event: dict) -> dict:
    return {
        "id": event["id"],
        "type": event["type"],
        "quantity": event["quantity"],
        "input_tokens": event["input_tokens"],
        "cached_tokens": event["cached_tokens"],
        "output_tokens": event["output_tokens"],
        "reasoning_tokens": event["reasoning_tokens"],
        "cost_cents": event["cost_cents"],
        "created_at": str(event["created_at"]),
    }


@router.post("/generate", status_code=201)
def generate(
    body: GenerateRequest,
    tenant: dict = Depends(get_current_tenant),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """The one dummy billable endpoint the capstone's realistic scope calls
    for. Every call must carry an Idempotency-Key header."""
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header required")

    try:
        if body.type == "api_call":
            result = record_api_call(tenant, idempotency_key)
        else:
            result = record_ai_tokens(
                tenant,
                idempotency_key,
                input_tokens=body.input_tokens,
                cached_tokens=body.cached_tokens,
                output_tokens=body.output_tokens,
                reasoning_tokens=body.reasoning_tokens,
            )
    except PaymentRequired as exc:
        raise HTTPException(status_code=402, detail=str(exc))
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=f"{exc} (used {exc.used}, limit {exc.limit})",
        )

    return {
        "duplicate": not result.was_new,
        "usage_event": _serialize_event(result.event),
    }


@router.get("/usage")
def get_usage(tenant: dict = Depends(get_current_tenant)):
    api_calls = usage_repo.sum_usage_this_month(tenant["id"], "api_call")
    ai_tokens = usage_repo.sum_usage_this_month(tenant["id"], "ai_tokens")

    token_cost_cents = ai_tokens["cost_cents"]
    plan_cost_cents = tenant["monthly_price_cents"]

    return {
        "plan": tenant["plan_name"],
        "api_calls": {
            "used": api_calls["used"],
            "limit": tenant["api_call_limit"],
        },
        "ai_tokens": {
            "used": ai_tokens["used"],
            "limit": tenant["ai_token_limit"],
        },
        "cost_cents": {
            "plan_monthly": plan_cost_cents,
            "ai_tokens": token_cost_cents,
            "total": plan_cost_cents + token_cost_cents,
        },
    }
