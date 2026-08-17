"""
Shared FastAPI dependency injections.
"""
from typing import AsyncGenerator

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import get_settings
from app.db import get_engine
from app.models.auth import DealerUserOut
from app.models.dealer_user_table import dealer_user_table
from app.services.auth_service import decode_access_token

settings = get_settings()


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
    except (jwt.InvalidTokenError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="invalid or expired session") from exc

    row = (
        await conn.execute(
            select(
                dealer_user_table.c.dealer_id,
                dealer_user_table.c.email,
                dealer_user_table.c.name,
                dealer_user_table.c.dealership_name,
            ).where(dealer_user_table.c.dealer_id == dealer_id)
        )
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")

    return DealerUserOut(**row)
