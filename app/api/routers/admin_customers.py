"""
Admin-only customer account management. Accounts live in atoloan-backend
(/customers, service token); this layer enforces admin rights and audits
every change with who did it and what changed.

The audit row is committed BEFORE the change is attempted ("pending") and
then marked done / unchanged / failed / unknown: a change can't happen without
a trace, even if the backend times out after applying it.

Accounts are addressed by numeric id — an email in a URL would end up in
access logs and in this service's request logs.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update

from app.core.dependencies import require_admin
from app.db import get_engine
from app.models.auth import DealerUserOut
from app.models.dealer_user_table import admin_audit_table
from app.services.backend_client import BackendNotFoundError, BackendUnavailableError, backend_request

router = APIRouter(prefix="/admin/customers", tags=["admin-customers"])


class CustomerUpdate(BaseModel):
    """Mirrors atoloan-backend's rules so a bad edit is a 422 here, not a
    502 from the backend call (any non-404 backend error reads as 'unavailable')."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    phone_number: str | None = Field(None, pattern=r"^\d{10}$")
    address: str | None = Field(None, min_length=1, max_length=255)
    city: str | None = Field(None, min_length=1, max_length=100)
    state: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    zipcode: str | None = Field(None, pattern=r"^\d{5}$")


class StatusIn(BaseModel):
    status: Literal["active", "disabled"]


def _path(customer_id: int, suffix: str = "") -> str:
    return f"/customers/{customer_id}{suffix}"


async def _backend(method: str, path: str, **kwargs) -> dict:
    try:
        return await backend_request(method, path, **kwargs)
    except BackendNotFoundError as exc:
        raise HTTPException(status_code=404, detail="customer not found") from exc
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=502, detail="customer service is currently unavailable") from exc


@router.get("")
async def list_customers(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin: DealerUserOut = Depends(require_admin),
) -> dict:
    params = {"limit": limit, "offset": offset, **({"q": q} if q else {})}
    return await _backend("GET", "/customers", params=params)


@router.get("/{customer_id}")
async def get_customer(customer_id: int, _admin: DealerUserOut = Depends(require_admin)) -> dict:
    return await _backend("GET", _path(customer_id))


async def _start_audit(actor_id: str, action: str, customer_id: int, requested: dict) -> int:
    async with get_engine().begin() as conn:
        return (
            await conn.execute(
                admin_audit_table.insert()
                .values(
                    actor_dealer_id=actor_id,
                    action=action,
                    target_type="customer",
                    target_id=str(customer_id),
                    details={"outcome": "pending", "requested": requested},
                )
                .returning(admin_audit_table.c.id)
            )
        ).scalar_one()


async def _finish_audit(audit_id: int, details: dict) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(update(admin_audit_table).where(admin_audit_table.c.id == audit_id).values(details=details))


async def _audited(admin: DealerUserOut, action: str, customer_id: int, requested: dict, method: str, path: str, **kwargs):
    """Audit first, then call the backend. Returns (audit_id, result)."""
    audit_id = await _start_audit(admin.dealer_id, action, customer_id, requested)
    try:
        result = await _backend(method, path, **kwargs)
    except HTTPException as exc:
        # 404: nothing changed. Anything else: the change may or may not have applied.
        outcome = "failed" if exc.status_code == 404 else "unknown"
        await _finish_audit(audit_id, {"outcome": outcome, "requested": requested})
        raise
    return audit_id, result


@router.patch("/{customer_id}")
async def update_customer(customer_id: int, changes: CustomerUpdate, admin: DealerUserOut = Depends(require_admin)) -> dict:
    requested = changes.model_dump(exclude_none=True)
    if not requested:
        raise HTTPException(status_code=422, detail="nothing to change")
    audit_id, result = await _audited(
        admin, "update_customer", customer_id, requested, "PATCH", _path(customer_id), json=requested
    )
    before, after = result["before"], result["after"]
    changed = {name: {"from": before.get(name), "to": after.get(name)} for name in after if before.get(name) != after.get(name)}
    await _finish_audit(audit_id, {
        "outcome": "done" if changed else "unchanged",
        "email": after["email"],
        "requested": requested,
        "changed": changed,
    })
    return after


@router.post("/{customer_id}/status")
async def set_customer_status(customer_id: int, payload: StatusIn, admin: DealerUserOut = Depends(require_admin)) -> dict:
    action = "disable_customer" if payload.status == "disabled" else "enable_customer"
    requested = {"status": payload.status}
    audit_id, result = await _audited(
        admin, action, customer_id, requested, "POST", _path(customer_id, "/status"), json=requested
    )
    await _finish_audit(audit_id, {
        "outcome": "done" if result["previous_status"] != payload.status else "unchanged",
        "email": result["email"],
        "requested": requested,
        "from": result["previous_status"],
        "to": payload.status,
    })
    return result


@router.post("/{customer_id}/close")
async def close_customer(customer_id: int, admin: DealerUserOut = Depends(require_admin)) -> dict:
    audit_id, result = await _audited(admin, "close_customer", customer_id, {}, "POST", _path(customer_id, "/close"))
    await _finish_audit(audit_id, {"outcome": "done", "email": result["email"], "requested": {}})
    return result
