"""
Dealer-facing application status: the dealer's own submitted soft-pull
applications, scoped server-side to their own dealer_id.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user
from app.models.auth import DealerUserOut
from app.services.applications_service import ApplicationsUnavailableError, list_applications

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("")
async def get_my_applications(current_user: DealerUserOut = Depends(get_current_user)) -> list[dict]:
    try:
        return await list_applications(current_user.dealer_id)
    except ApplicationsUnavailableError as exc:
        raise HTTPException(
            status_code=502, detail="applications service is currently unavailable"
        ) from exc
