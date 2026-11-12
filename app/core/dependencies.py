"""
Shared FastAPI dependency injections.
"""
from typing import AsyncGenerator

import hmac

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import get_settings
from app.db import get_engine
from app.models.auth import DealerUserOut
from app.models.dealer_user_table import dealer_user_table
from app.services.auth_service import decode_access_token, password_version

settings = get_settings()

_ALLOWED_WHILE_PASSWORD_CHANGE_REQUIRED = {"/auth/me", "/auth/change-password", "/auth/logout"}


async def get_conn() -> AsyncGenerator[AsyncConnection, None]:
    """Yield a transactional async DB connection for use in route handlers."""
    async with get_engine().begin() as conn:
        yield conn


async def get_current_user(
    request: Request,
    conn: AsyncConnection = Depends(get_conn),
) -> DealerUserOut:
    """Resolve the signed-in dealer user from the session cookie."""
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")

    try:
        payload = decode_access_token(token)
        dealer_id = payload["sub"]
        token_pwv = payload["pwv"]
    except (jwt.InvalidTokenError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="invalid or expired session") from exc

    row = (
        await conn.execute(
            select(
                dealer_user_table.c.dealer_id,
                dealer_user_table.c.email,
                dealer_user_table.c.name,
                dealer_user_table.c.dealership_name,
                dealer_user_table.c.password_hash,
                dealer_user_table.c.is_admin,
                dealer_user_table.c.is_active,
                dealer_user_table.c.must_change_password,
            ).where(dealer_user_table.c.dealer_id == dealer_id)
        )
    ).mappings().first()

    # Unknown, deactivated, or token minted before the latest password change → revoked.
    if (
        row is None
        or not row["is_active"]
        or not hmac.compare_digest(password_version(row["password_hash"]), token_pwv)
    ):
        raise HTTPException(status_code=401, detail="invalid or expired session")

    # A temporary (admin-issued) password only unlocks changing it.
    if row["must_change_password"] and request.url.path not in _ALLOWED_WHILE_PASSWORD_CHANGE_REQUIRED:
        raise HTTPException(status_code=403, detail="password change required")

    return DealerUserOut(**{k: v for k, v in row.items() if k not in ("password_hash", "is_active")})


async def require_admin(current_user: DealerUserOut = Depends(get_current_user)) -> DealerUserOut:
    """Admin rights come from the database row on every request, never the token."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="admin access required")
    return current_user
