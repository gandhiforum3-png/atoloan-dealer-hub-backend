"""
Server-to-server endpoints for other atoloan services. Callers must send the
shared X-Service-Token; no dealer login.
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.dependencies import get_conn
from app.core.security import require_service_token
from app.services.bank_network_service import get_dealer_bank_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_service_token)])


@router.get("/dealers/{dealer_id}/bank-ids")
async def list_dealer_bank_ids(
    dealer_id: str,
    conn: AsyncConnection = Depends(get_conn),
) -> dict:
    """
    Used by atoloan-backend's /findback to restrict bank search to the
    dealer's mapped network when a dealer_id is supplied. An unknown
    dealer_id (or a known dealer with no banks selected yet) just returns
    an empty list rather than a 404 — the caller treats both the same way.
    """
    bank_ids = await get_dealer_bank_ids(conn, dealer_id)
    return {"dealer_id": dealer_id, "bank_ids": bank_ids}
