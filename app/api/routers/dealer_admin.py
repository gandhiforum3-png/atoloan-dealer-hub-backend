"""
Admin-only endpoints for managing dealerships as they're onboarded.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.dependencies import get_conn, require_admin
from app.models.auth import DealerUserOut
from app.models.dealer_admin import (
    CreateDealerRequest,
    CreatedDealerOut,
    DealerAdminOut,
    ResetPasswordOut,
    UpdateDealerRequest,
)
from app.services.dealer_admin_service import (
    DuplicateEmailError,
    create_dealer,
    list_dealers,
    reset_dealer_password,
    update_dealer,
)

router = APIRouter(prefix="/admin/dealers", tags=["dealer-admin"])


@router.get("", response_model=list[DealerAdminOut])
async def get_dealers(
    q: str | None = None,
    _admin: DealerUserOut = Depends(require_admin),
    conn: AsyncConnection = Depends(get_conn),
) -> list[dict]:
    return await list_dealers(conn, q)


@router.post("", response_model=CreatedDealerOut, status_code=201)
async def post_dealer(
    payload: CreateDealerRequest,
    admin: DealerUserOut = Depends(require_admin),
    conn: AsyncConnection = Depends(get_conn),
) -> dict:
    try:
        return await create_dealer(conn, payload, actor_id=admin.dealer_id)
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=409, detail="a dealer with this email already exists") from exc


@router.patch("/{dealer_id}", response_model=DealerAdminOut)
async def patch_dealer(
    dealer_id: str,
    payload: UpdateDealerRequest,
    admin: DealerUserOut = Depends(require_admin),
    conn: AsyncConnection = Depends(get_conn),
) -> dict:
    # Guards against an admin locking everyone (including themselves) out
    if dealer_id == admin.dealer_id and payload.is_active is False:
        raise HTTPException(status_code=422, detail="you cannot deactivate your own account")
    if dealer_id == admin.dealer_id and payload.is_admin is False:
        raise HTTPException(status_code=422, detail="you cannot remove your own admin access")
    try:
        row = await update_dealer(conn, dealer_id, payload, actor_id=admin.dealer_id)
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=409, detail="a dealer with this email already exists") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="dealer not found")
    return row


@router.post("/{dealer_id}/reset-password", response_model=ResetPasswordOut)
async def post_reset_password(
    dealer_id: str,
    admin: DealerUserOut = Depends(require_admin),
    conn: AsyncConnection = Depends(get_conn),
) -> dict:
    temporary_password = await reset_dealer_password(conn, dealer_id, actor_id=admin.dealer_id)
    if temporary_password is None:
        raise HTTPException(status_code=404, detail="dealer not found")
    return {"temporary_password": temporary_password}
