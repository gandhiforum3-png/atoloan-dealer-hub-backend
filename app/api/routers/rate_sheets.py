"""
Rate sheet upload: parse a bank's rate sheet PDF for review, then — on
dealer approval — persist it as a credit union record and add that bank to
the dealer's own network.
"""
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.dependencies import get_conn, get_current_user
from app.core.security import rate_sheet_parse_quota
from app.models.lender_submission_table import lender_submission_table
from app.models.auth import DealerUserOut
from app.services import bank_network_service
from app.services.bank_network_service import (
    BankNetworkUnavailableError,
    add_dealer_bank,
)
from app.services.rate_sheet_service import (
    RateSheetServiceUnavailableError,
    parse_rate_sheet,
    save_rate_sheet,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rate-sheets", tags=["rate-sheets"])

MAX_RATE_SHEET_BYTES = 20 * 1024 * 1024


@router.post("/upload")
async def upload_rate_sheet(
    file: UploadFile = File(...),
    current_user: DealerUserOut = Depends(get_current_user),
) -> dict:
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="only PDF rate sheets are supported")

    content = await file.read(MAX_RATE_SHEET_BYTES + 1)
    if len(content) > MAX_RATE_SHEET_BYTES:
        raise HTTPException(status_code=413, detail="rate sheet exceeds 20 MB")
    if not content:
        raise HTTPException(status_code=422, detail="uploaded file is empty")
    rate_sheet_parse_quota.take(current_user.dealer_id)

    try:
        return await parse_rate_sheet(file.filename, content, file.content_type)
    except RateSheetServiceUnavailableError as exc:
        raise HTTPException(
            status_code=502, detail="rate sheet parsing service is currently unavailable"
        ) from exc


@router.post("/confirm")
async def confirm_rate_sheet(
    request: Request,
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> dict:
    """
    Dealer-approved commit step: saves the previously-previewed rate_sheet
    as a credit union record on atoloan-backend, then adds that bank to
    the approving dealer's own network — additively, leaving the rest of
    their existing network selection untouched.

    Dealers can only submit *new* lenders, which atoloan-backend stores as
    pending — customers are never matched to them until an admin approves.
    An existing lender is never overwritten from here: atoloan-backend upserts
    by name, and any dealer can add any lender to their network, so allowing
    "update my own network's bank" would let any dealer rewrite any lender.
    """
    payload = await request.json()
    rate_sheet = payload.get("rate_sheet") if isinstance(payload, dict) else None
    if not isinstance(rate_sheet, dict):
        raise HTTPException(status_code=400, detail="rate_sheet is required")

    bank_name = (rate_sheet.get("credit_union_info") or {}).get("name")
    if not bank_name:
        raise HTTPException(status_code=400, detail="rate sheet is missing a credit union name")

    try:
        existing = {bank.name: bank.id for bank in await bank_network_service.list_banks()}
    except BankNetworkUnavailableError as exc:
        raise HTTPException(status_code=502, detail="rate sheet service is currently unavailable") from exc
    if bank_name in existing:
        raise HTTPException(
            status_code=409,
            detail="this lender already exists — rate changes for existing lenders are reviewed by atoloan, contact support",
        )

    try:
        update_result = await save_rate_sheet(rate_sheet)
    except RateSheetServiceUnavailableError as exc:
        raise HTTPException(
            status_code=502, detail="rate sheet service is currently unavailable"
        ) from exc

    bank_id = update_result.get("bank_id")
    if bank_id is None:
        logger.error("rate sheet save for %s returned no bank_id: %s", bank_name, update_result)
        raise HTTPException(status_code=502, detail="rate sheet was not saved — no bank_id returned")

    await add_dealer_bank(conn, current_user.dealer_id, bank_id, bank_name)
    # Remembered so admins reviewing the pending lender see who submitted it
    submission = pg_insert(lender_submission_table).values(bank_id=bank_id, dealer_id=current_user.dealer_id)
    await conn.execute(
        submission.on_conflict_do_update(
            index_elements=[lender_submission_table.c.bank_id],
            set_={"dealer_id": submission.excluded.dealer_id, "submitted_at": func.now()},
        )
    )

    return {
        "status": "success",
        "bank_id": bank_id,
        "bank_name": bank_name,
        "approval_status": "pending",
        "rate_policy_items_count": update_result.get("rate_policy_items_count"),
        "loan_program_items_count": update_result.get("loan_program_items_count"),
    }
