"""
Admin-only lender review and all-dealer application views. Lender and
application data live in atoloan-backend; this layer adds who-submitted-what
from our own tables, enforces admin rights, and audits every change.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.dependencies import get_conn, require_admin
from app.models.auth import DealerUserOut
from app.models.bank_dealer_table import bank_dealer_table
from app.models.dealer_user_table import dealer_user_table
from app.models.lender_submission_table import lender_submission_table
from app.services.applications_service import all_applications_summary, list_all_applications
from app.services.audit_service import record_admin_action
from app.services.backend_client import BackendNotFoundError, BackendUnavailableError, backend_request

router = APIRouter(prefix="/admin", tags=["admin"])


class ApprovalRequest(BaseModel):
    status: Literal["approved", "pending"]


def _unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail="lender service is currently unavailable")


async def _submissions(conn: AsyncConnection) -> dict[int, dict]:
    rows = (
        await conn.execute(
            select(
                lender_submission_table.c.bank_id,
                lender_submission_table.c.submitted_at,
                dealer_user_table.c.dealer_id,
                dealer_user_table.c.dealership_name,
            ).join(
                dealer_user_table,
                dealer_user_table.c.dealer_id == lender_submission_table.c.dealer_id,
                isouter=True,
            )
        )
    ).mappings().all()
    return {row["bank_id"]: dict(row) for row in rows}


async def _lenders(conn: AsyncConnection) -> list[dict]:
    try:
        payload = await backend_request("GET", "/credit-unions")
    except BackendUnavailableError as exc:
        raise _unavailable(exc) from exc

    submissions = await _submissions(conn)
    lenders = []
    for bank in payload.get("credit_unions", []):
        sub = submissions.get(bank["id"])
        lenders.append(
            {
                "id": bank["id"],
                "name": bank["name"],
                "approval_status": bank.get("approval_status", "approved"),
                "submitted_by": (
                    {"dealer_id": sub["dealer_id"], "dealership_name": sub["dealership_name"]}
                    if sub and sub["dealer_id"]
                    else None
                ),
                "submitted_at": sub["submitted_at"] if sub else None,
            }
        )
    # Work queue first: pending lenders, oldest submission first; then the rest by name
    lenders.sort(
        key=lambda l: (
            l["approval_status"] != "pending",
            (l["submitted_at"].timestamp() if l["submitted_at"] else 0) if l["approval_status"] == "pending" else 0,
            l["name"].lower(),
        )
    )
    return lenders


async def _lender_or_404(conn: AsyncConnection, bank_id: int) -> dict:
    lender = next((l for l in await _lenders(conn) if l["id"] == bank_id), None)
    if lender is None:
        raise HTTPException(status_code=404, detail="lender not found")
    return lender


@router.get("/lenders")
async def get_lenders(
    _admin: DealerUserOut = Depends(require_admin),
    conn: AsyncConnection = Depends(get_conn),
) -> list[dict]:
    return await _lenders(conn)


@router.get("/lenders/{bank_id}")
async def get_lender(
    bank_id: int,
    _admin: DealerUserOut = Depends(require_admin),
    conn: AsyncConnection = Depends(get_conn),
) -> dict:
    lender = await _lender_or_404(conn, bank_id)
    try:
        rate_sheet = await backend_request("GET", f"/credit-unions/{bank_id}/ratesheet")
    except BackendNotFoundError as exc:
        raise HTTPException(status_code=404, detail="lender not found") from exc
    except BackendUnavailableError as exc:
        raise _unavailable(exc) from exc
    return {**lender, "rate_sheet": rate_sheet}


@router.post("/lenders/{bank_id}/approval")
async def set_lender_approval(
    bank_id: int,
    payload: ApprovalRequest,
    admin: DealerUserOut = Depends(require_admin),
    conn: AsyncConnection = Depends(get_conn),
) -> dict:
    lender = await _lender_or_404(conn, bank_id)
    if lender["approval_status"] == payload.status:
        return lender
    try:
        await backend_request("POST", f"/credit-unions/{bank_id}/approval", json={"status": payload.status})
    except BackendNotFoundError as exc:
        raise HTTPException(status_code=404, detail="lender not found") from exc
    except BackendUnavailableError as exc:
        raise _unavailable(exc) from exc

    action = "approve_lender" if payload.status == "approved" else "unpublish_lender"
    await record_admin_action(conn, admin.dealer_id, action, "lender", bank_id, {"name": lender["name"]})
    return {**lender, "approval_status": payload.status}


@router.delete("/lenders/{bank_id}")
async def reject_lender(
    bank_id: int,
    admin: DealerUserOut = Depends(require_admin),
    conn: AsyncConnection = Depends(get_conn),
) -> dict:
    """Reject a pending submission: removes the lender and its rate sheet.
    Approved lenders must be unpublished first, so a live lender is never
    deleted in one click."""
    lender = await _lender_or_404(conn, bank_id)
    if lender["approval_status"] != "pending":
        raise HTTPException(status_code=409, detail="only pending lenders can be rejected — unpublish it first")
    try:
        await backend_request("DELETE", f"/credit-unions/{bank_id}")
    except BackendNotFoundError as exc:
        raise HTTPException(status_code=404, detail="lender not found") from exc
    except BackendUnavailableError as exc:
        raise _unavailable(exc) from exc

    await conn.execute(delete(bank_dealer_table).where(bank_dealer_table.c.bank_id == bank_id))
    await conn.execute(delete(lender_submission_table).where(lender_submission_table.c.bank_id == bank_id))
    await record_admin_action(
        conn,
        admin.dealer_id,
        "reject_lender",
        "lender",
        bank_id,
        {"name": lender["name"], "submitted_by": (lender["submitted_by"] or {}).get("dealer_id")},
    )
    return {"status": "rejected", "id": bank_id}


async def _dealer_names(conn: AsyncConnection) -> dict[str, str]:
    rows = (await conn.execute(select(dealer_user_table.c.dealer_id, dealer_user_table.c.dealership_name))).all()
    return {row.dealer_id: row.dealership_name for row in rows}


@router.get("/applications")
async def get_all_applications(
    dealer_id: str | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin: DealerUserOut = Depends(require_admin),
    conn: AsyncConnection = Depends(get_conn),
) -> dict:
    try:
        page = await list_all_applications(dealer_id, limit, offset, q)
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=502, detail="applications service is currently unavailable") from exc
    names = await _dealer_names(conn)
    for application in page.get("applications", []):
        # null dealer_id = the customer applied directly on the public site
        application["dealership_name"] = names.get(application.get("dealer_id"))
    return page


@router.get("/applications/summary")
async def get_all_applications_summary(
    dealer_id: str | None = None,
    q: str | None = Query(None, max_length=100),
    _admin: DealerUserOut = Depends(require_admin),
) -> dict:
    try:
        return await all_applications_summary(dealer_id, q)
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=502, detail="applications service is currently unavailable") from exc
