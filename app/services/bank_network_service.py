"""
Client for atoloan-backend's bank/credit-union data.

Dealer-hub-backend has no bank data of its own — atoloan-backend owns
that table, so we go through its API rather than reading its database
directly.
"""
import logging

import httpx
from sqlalchemy import delete, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import get_settings
from app.models.bank import BankOut
from app.models.bank_dealer_table import bank_dealer_table

logger = logging.getLogger(__name__)

settings = get_settings()


class BankNetworkUnavailableError(Exception):
    pass


class UnknownBankError(Exception):
    def __init__(self, bank_ids: list[int]):
        self.bank_ids = bank_ids
        super().__init__(f"unknown bank id(s): {bank_ids}")


async def list_banks() -> list[BankOut]:
    url = f"{settings.atoloan_backend_base_url.rstrip('/')}/credit-unions"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=settings.service_headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("atoloan-backend bank lookup failed")
        raise BankNetworkUnavailableError(str(exc)) from exc

    payload = response.json()
    return [BankOut(**bank) for bank in payload.get("credit_unions", [])]


async def get_dealer_bank_ids(conn: AsyncConnection, dealer_id: str) -> list[int]:
    """Bare bank_id list for a dealer's network — used by atoloan-backend's
    /findback to restrict bank search to banks this dealer actually works
    with. A dealer with no rows here (unknown dealer_id or none selected
    yet) just returns an empty list, same as any other dealer_id."""
    rows = (
        await conn.execute(
            select(bank_dealer_table.c.bank_id)
            .where(bank_dealer_table.c.dealer_id == dealer_id)
            .order_by(bank_dealer_table.c.bank_id)
        )
    ).all()
    return [row.bank_id for row in rows]


async def get_dealer_banks(conn: AsyncConnection, dealer_id: str) -> list[BankOut]:
    rows = (
        await conn.execute(
            select(bank_dealer_table.c.bank_id, bank_dealer_table.c.bank_name)
            .where(bank_dealer_table.c.dealer_id == dealer_id)
            .order_by(bank_dealer_table.c.bank_name)
        )
    ).all()
    return [BankOut(id=row.bank_id, name=row.bank_name) for row in rows]


async def save_dealer_banks(
    conn: AsyncConnection, dealer_id: str, bank_ids: list[int]
) -> list[BankOut]:
    """Replace the dealer's bank network with the given set of bank ids.

    Every id is validated against the live atoloan-backend bank list before
    anything is written, so a bogus id can't get silently stored.
    """
    available = {bank.id: bank.name for bank in await list_banks()}
    unknown = sorted({bank_id for bank_id in bank_ids if bank_id not in available})
    if unknown:
        raise UnknownBankError(unknown)

    unique_ids = sorted(set(bank_ids))

    await conn.execute(delete(bank_dealer_table).where(bank_dealer_table.c.dealer_id == dealer_id))
    if unique_ids:
        await conn.execute(
            insert(bank_dealer_table),
            [
                {"dealer_id": dealer_id, "bank_id": bank_id, "bank_name": available[bank_id]}
                for bank_id in unique_ids
            ],
        )

    return [BankOut(id=bank_id, name=available[bank_id]) for bank_id in unique_ids]


async def add_dealer_bank(conn: AsyncConnection, dealer_id: str, bank_id: int, bank_name: str) -> None:
    """
    Add a single bank to the dealer's network without touching the rest of
    their selection — unlike save_dealer_banks, which replaces the whole
    set. Used when a dealer approves a freshly-parsed rate sheet.
    """
    stmt = pg_insert(bank_dealer_table).values(
        dealer_id=dealer_id, bank_id=bank_id, bank_name=bank_name
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[bank_dealer_table.c.dealer_id, bank_dealer_table.c.bank_id],
        set_={"bank_name": bank_name},
    )
    await conn.execute(stmt)
