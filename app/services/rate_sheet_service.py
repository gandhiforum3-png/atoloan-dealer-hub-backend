"""
Client for atoloan-backend's rate sheet PDF-parsing pipeline.

Dealer-hub-backend has no PDF/OCR/LLM parsing of its own — atoloan-backend
already owns that pipeline (pdfplumber/camelot + LLM extraction), so we
forward the upload to it rather than duplicating those dependencies here.
This only parses and previews; nothing is persisted to the bank database.
"""
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class RateSheetServiceUnavailableError(Exception):
    pass


async def parse_rate_sheet(filename: str, content: bytes, content_type: str | None) -> dict:
    url = f"{settings.atoloan_backend_base_url.rstrip('/')}/ratesheetuploader"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                files={"file": (filename, content, content_type or "application/pdf")},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("atoloan-backend rate sheet upload failed")
        raise RateSheetServiceUnavailableError(str(exc)) from exc

    payload = response.json()
    files = payload.get("files") or []
    if not files:
        return {"filename": filename, "parse_error": "no file was processed", "rate_sheet": None}

    result = files[0]
    return {
        "filename": result.get("filename", filename),
        "parse_error": result.get("parse_error"),
        "validation": result.get("validation"),
        "rate_sheet": result.get("rate_sheet"),
    }


async def save_rate_sheet(rate_sheet: dict) -> dict:
    """
    Persist a dealer-approved rate sheet as a credit union record.

    atoloan-backend's /update upserts by credit union name — approving a
    rate sheet for a bank that already exists there updates its rates in
    place rather than creating a duplicate.
    """
    url = f"{settings.atoloan_backend_base_url.rstrip('/')}/update"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=rate_sheet)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("atoloan-backend rate sheet save failed")
        raise RateSheetServiceUnavailableError(str(exc)) from exc

    return response.json()
