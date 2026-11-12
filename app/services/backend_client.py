"""
Authenticated calls to atoloan-backend (sends the shared X-Service-Token).
"""
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class BackendUnavailableError(Exception):
    pass


class BackendNotFoundError(Exception):
    pass


async def backend_request(method: str, path: str, *, timeout: float = 15.0, **kwargs) -> dict:
    url = f"{settings.atoloan_backend_base_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, url, headers=settings.service_headers, **kwargs)
    except httpx.HTTPError as exc:
        logger.exception("atoloan-backend %s %s failed", method, path)
        raise BackendUnavailableError(str(exc)) from exc

    if response.status_code == 404:
        raise BackendNotFoundError(path)
    if response.status_code >= 400:
        logger.error("atoloan-backend %s %s returned %s", method, path, response.status_code)
        raise BackendUnavailableError(f"status {response.status_code}")
    return response.json()
