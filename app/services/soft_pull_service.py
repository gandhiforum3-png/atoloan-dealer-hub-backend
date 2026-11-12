"""
Client for atoloan-backend's /findback — runs a 700Credit soft-pull
pre-qualification and (best-effort) finds the best matching bank offer.
"""
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class SoftPullUnavailableError(Exception):
    pass


async def run_soft_pull(payload: dict) -> tuple[int, dict]:
    url = f"{settings.atoloan_backend_base_url.rstrip('/')}/findback"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=settings.service_headers)
    except httpx.HTTPError as exc:
        logger.exception("atoloan-backend soft pull request failed")
        raise SoftPullUnavailableError(str(exc)) from exc

    try:
        body = response.json()
    except ValueError:
        body = {}

    return response.status_code, body
