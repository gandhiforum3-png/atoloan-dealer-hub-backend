"""
Unauthenticated endpoints reachable by scanning a dealer's QR code.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.dependencies import get_conn
from app.models.dealer_user_table import dealer_user_table
from app.models.qr_code import PublicDealerOut
from app.models.qr_code_table import qr_code_table

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/dealers/{dealer_id}", response_model=PublicDealerOut)
async def get_public_dealer_info(
    dealer_id: str,
    code: str,
    conn: AsyncConnection = Depends(get_conn),
) -> PublicDealerOut:
    """Resolve the QR scan target: dealer_id + the token printed on the code.

    A mismatched or stale `code` (from a since-regenerated QR code) is
    rejected so old printed/shared codes stop working.
    """
    row = (
        await conn.execute(
            select(
                dealer_user_table.c.dealer_id,
                dealer_user_table.c.dealership_name,
            )
            .select_from(dealer_user_table.join(qr_code_table))
            .where(
                dealer_user_table.c.dealer_id == dealer_id,
                qr_code_table.c.token == code,
                dealer_user_table.c.is_active.is_(True),  # deactivated dealer → their printed codes stop working
            )
        )
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="QR code not found or no longer active")

    return PublicDealerOut(**row)
