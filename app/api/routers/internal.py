"""
Server-to-server endpoints for other atoloan services — not reachable by
end users, no bank/rate data of its own to protect (mirrors the trust
model atoloan-backend already uses for its own unauthenticated
/credit-unions endpoint).
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.dependencies import get_conn
from app.services.bank_network_service import get_dealer_bank_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


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
