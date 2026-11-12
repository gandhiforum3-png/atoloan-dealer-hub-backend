"""
Dealer-facing application status: the dealer's own submitted soft-pull
applications, scoped server-side to their own dealer_id.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_current_user
from app.models.auth import DealerUserOut
from app.services.applications_service import (
    ApplicationsUnavailableError,
    applications_summary,
    list_applications,
)

router = APIRouter(prefix="/applications", tags=["applications"])

_UNAVAILABLE = "applications service is currently unavailable"


@router.get("")
async def get_my_applications(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: DealerUserOut = Depends(get_current_user),
) -> dict:
    try:
        return await list_applications(current_user.dealer_id, limit, offset)
    except ApplicationsUnavailableError as exc:
        raise HTTPException(status_code=502, detail=_UNAVAILABLE) from exc


@router.get("/summary")
async def get_my_summary(current_user: DealerUserOut = Depends(get_current_user)) -> dict:
    try:
        return await applications_summary(current_user.dealer_id)
    except ApplicationsUnavailableError as exc:
        raise HTTPException(status_code=502, detail=_UNAVAILABLE) from exc
