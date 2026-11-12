"""
Client for atoloan-backend's read-only loan application listings.
"""
from app.services.backend_client import BackendUnavailableError, backend_request

# Kept for existing callers/tests
ApplicationsUnavailableError = BackendUnavailableError


async def list_applications(dealer_id: str, limit: int = 50, offset: int = 0) -> dict:
    return await backend_request(
        "GET", f"/dealers/{dealer_id}/loan-applications", params={"limit": limit, "offset": offset}
    )


async def applications_summary(dealer_id: str) -> dict:
    return await backend_request("GET", f"/dealers/{dealer_id}/loan-applications/summary")


def _admin_filters(dealer_id: str | None, q: str | None) -> dict:
    return {k: v for k, v in (("dealer_id", dealer_id), ("q", q)) if v}


async def list_all_applications(dealer_id: str | None, limit: int, offset: int, q: str | None = None) -> dict:
    params = {"limit": limit, "offset": offset, **_admin_filters(dealer_id, q)}
    return await backend_request("GET", "/loan-applications", params=params)


async def all_applications_summary(dealer_id: str | None, q: str | None = None) -> dict:
    return await backend_request("GET", "/loan-applications/summary", params=_admin_filters(dealer_id, q) or None)
