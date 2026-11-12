"""
Admin-only dealer management: list, onboard, edit, and reset the password of
dealerships from /admin/dealers.
"""
import secrets

from fastapi.concurrency import run_in_threadpool

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models.dealer_admin import CreateDealerRequest, UpdateDealerRequest
from app.models.dealer_user_table import dealer_user_table, next_dealer_id
from app.services.audit_service import record_admin_action
from app.services.auth_service import hash_password


class DuplicateEmailError(Exception):
    pass


async def _audit(conn: AsyncConnection, actor_id: str, action: str, target_id: str, details: dict | None = None) -> None:
    await record_admin_action(conn, actor_id, action, "dealer", target_id, details)


def _temporary_password() -> str:
    return secrets.token_urlsafe(12)


async def list_dealers(conn: AsyncConnection, q: str | None) -> list[dict]:
    stmt = select(dealer_user_table).order_by(dealer_user_table.c.created_at.desc())
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                dealer_user_table.c.dealership_name.ilike(pattern),
                dealer_user_table.c.name.ilike(pattern),
                dealer_user_table.c.email.ilike(pattern),
            )
        )
    rows = (await conn.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]


async def create_dealer(conn: AsyncConnection, payload: CreateDealerRequest, actor_id: str) -> dict:
    """Admins never pick passwords: a one-time password is generated, returned
    once, and must be replaced by the dealer at first sign-in."""
    dealer_id = await next_dealer_id(conn)
    temporary_password = _temporary_password()
    password_hash = await run_in_threadpool(hash_password, temporary_password)
    try:
        async with conn.begin_nested():
            await conn.execute(
                dealer_user_table.insert().values(
                    dealer_id=dealer_id,
                    email=payload.email.lower(),
                    password_hash=password_hash,
                    name=payload.name,
                    dealership_name=payload.dealership_name,
                    is_admin=payload.is_admin,
                    must_change_password=True,
                )
            )
    except IntegrityError as exc:
        raise DuplicateEmailError(payload.email) from exc
    await _audit(conn, actor_id, "create_dealer", dealer_id, {"email": payload.email.lower(), "is_admin": payload.is_admin})

    row = (
        await conn.execute(select(dealer_user_table).where(dealer_user_table.c.dealer_id == dealer_id))
    ).mappings().first()
    return {**dict(row), "temporary_password": temporary_password}


async def update_dealer(
    conn: AsyncConnection, dealer_id: str, payload: UpdateDealerRequest, actor_id: str
) -> dict | None:
    changes = payload.model_dump(exclude_unset=True)
    if "email" in changes:
        changes["email"] = changes["email"].lower()

    if changes:
        try:
            async with conn.begin_nested():
                result = await conn.execute(
                    update(dealer_user_table)
                    .where(dealer_user_table.c.dealer_id == dealer_id)
                    .values(**changes)
                )
        except IntegrityError as exc:
            raise DuplicateEmailError(changes.get("email", "")) from exc
        if result.rowcount == 0:
            return None
        await _audit(conn, actor_id, "update_dealer", dealer_id, changes)

    row = (
        await conn.execute(select(dealer_user_table).where(dealer_user_table.c.dealer_id == dealer_id))
    ).mappings().first()
    return dict(row) if row else None


async def reset_dealer_password(conn: AsyncConnection, dealer_id: str, actor_id: str) -> str | None:
    """New one-time password. Every existing session of that dealer is revoked
    (password version changes) and the dealer must replace it at sign-in."""
    temporary_password = _temporary_password()
    password_hash = await run_in_threadpool(hash_password, temporary_password)
    result = await conn.execute(
        update(dealer_user_table)
        .where(dealer_user_table.c.dealer_id == dealer_id)
        .values(password_hash=password_hash, must_change_password=True)
    )
    if result.rowcount == 0:
        return None
    await _audit(conn, actor_id, "reset_password", dealer_id)
    return temporary_password
