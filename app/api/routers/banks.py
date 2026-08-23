"""
Bank network endpoints: the lenders available through atoloan-backend, and
each dealer's own selected subset of those lenders.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.dependencies import get_conn, get_current_user
from app.models.auth import DealerUserOut
from app.models.bank import BankOut, DealerBankSelection
from app.services.bank_network_service import (
    BankNetworkUnavailableError,
    UnknownBankError,
    get_dealer_banks,
    list_banks,
    save_dealer_banks,
)

router = APIRouter(prefix="/banks", tags=["banks"])


@router.get("", response_model=list[BankOut])
async def get_banks(
    _current_user: DealerUserOut = Depends(get_current_user),
) -> list[BankOut]:
    try:
        return await list_banks()
    except BankNetworkUnavailableError as exc:
        raise HTTPException(status_code=502, detail="bank network is currently unavailable") from exc


@router.get("/network", response_model=list[BankOut])
async def get_my_bank_network(
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> list[BankOut]:
    return await get_dealer_banks(conn, current_user.dealer_id)


@router.post("/network", response_model=list[BankOut])
async def update_my_bank_network(
    payload: DealerBankSelection,
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> list[BankOut]:
    try:
        return await save_dealer_banks(conn, current_user.dealer_id, payload.bank_ids)
    except UnknownBankError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BankNetworkUnavailableError as exc:
        raise HTTPException(status_code=502, detail="bank network is currently unavailable") from exc
