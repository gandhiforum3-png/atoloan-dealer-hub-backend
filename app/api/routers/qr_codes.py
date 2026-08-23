"""
Dealer-facing QR code management: generate, relabel, and fetch the
current showroom QR code. One active code per dealer.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.dependencies import get_conn, get_current_user
from app.models.auth import DealerUserOut
from app.models.qr_code import QRCodeLabelUpdate, QRCodeOut
from app.models.qr_code_table import qr_code_table
from app.services.qr_code_service import build_scan_url, generate_token, render_qr_png_data_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qr-codes", tags=["qr-codes"])

DEFAULT_LABEL = "Showroom QR"


def _to_out(row) -> QRCodeOut:
    url = build_scan_url(row["dealer_id"], row["token"])
    return QRCodeOut(
        dealer_id=row["dealer_id"],
        label=row["label"],
        token=row["token"],
        url=url,
        image_data_url=render_qr_png_data_url(url),
        updated_at=row["updated_at"],
    )


@router.get("/me", response_model=QRCodeOut)
async def get_my_qr_code(
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> QRCodeOut:
    row = (
        await conn.execute(
            select(qr_code_table).where(qr_code_table.c.dealer_id == current_user.dealer_id)
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="no QR code generated yet")
    return _to_out(row)


@router.post("", response_model=QRCodeOut)
async def generate_qr_code(
    payload: QRCodeLabelUpdate | None = None,
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> QRCodeOut:
    """Create the dealer's QR code, or rotate its token if one already exists.

    Rotating the token changes the encoded URL, so any previously
    printed/shared copies of the old code stop resolving.
    """
    label = (payload.label.strip() if payload and payload.label.strip() else None) or DEFAULT_LABEL
    token = generate_token()

    stmt = pg_insert(qr_code_table).values(
        dealer_id=current_user.dealer_id,
        label=label,
        token=token,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[qr_code_table.c.dealer_id],
        set_={"label": label, "token": token, "updated_at": func.now()},
    ).returning(qr_code_table)

    row = (await conn.execute(stmt)).mappings().first()
    return _to_out(row)


@router.patch("/me", response_model=QRCodeOut)
async def update_qr_code_label(
    payload: QRCodeLabelUpdate,
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> QRCodeOut:
    """Rename the existing QR code without rotating its token/URL."""
    label = payload.label.strip() or DEFAULT_LABEL

    row = (
        await conn.execute(
            qr_code_table.update()
            .where(qr_code_table.c.dealer_id == current_user.dealer_id)
            .values(label=label)
            .returning(qr_code_table)
        )
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="no QR code generated yet")
    return _to_out(row)
