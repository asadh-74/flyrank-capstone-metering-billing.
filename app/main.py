from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .database import init_db
from .routers import billing, usage, webhooks

app = FastAPI(
    title="Usage Metering & Billing Engine",
    description=(
        "Meters billable usage exactly once under retries, enforces plan "
        "quotas honestly, prices AI tokens correctly, and keeps tenant "
        "plans in sync with Stripe via verified, deduplicated webhooks."
    ),
    version="1.0.0",
)


@app.on_event("startup")
async def on_startup():
    init_db()
    print("Server running; schema initialized; connected to Postgres.")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": str(exc.errors())})


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(usage.router)
app.include_router(billing.router)
app.include_router(webhooks.router)
