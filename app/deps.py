from fastapi import Header, HTTPException

from .repository import tenants as tenant_repo


def get_current_tenant(x_api_key: str | None = Header(default=None)) -> dict:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    tenant = tenant_repo.get_tenant_by_api_key(x_api_key)
    if tenant is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return tenant
