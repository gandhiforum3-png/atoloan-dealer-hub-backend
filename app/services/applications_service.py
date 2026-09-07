"""
Client for atoloan-backend's read-only loan application listing.
"""
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class ApplicationsUnavailableError(Exception):
    pass


async def list_applications(dealer_id: str) -> list[dict]:
    url = f"{settings.atoloan_backend_base_url.rstrip('/')}/dealers/{dealer_id}/loan-applications"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("atoloan-backend applications lookup failed")
        raise ApplicationsUnavailableError(str(exc)) from exc

    return response.json().get("applications", [])
