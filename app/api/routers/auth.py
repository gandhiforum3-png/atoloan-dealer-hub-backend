"""
Dealer sign-in endpoints: login, current-session lookup, logout.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import get_settings
from app.core.dependencies import get_conn, get_current_user
from app.models.auth import DealerUserOut, LoginRequest
from app.models.dealer_user_table import dealer_user_table
from app.services.auth_service import create_access_token, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=settings.jwt_expires_minutes * 60,
        path="/",
    )


@router.post("/login", response_model=DealerUserOut)
async def login(
    payload: LoginRequest,
    response: Response,
    conn: AsyncConnection = Depends(get_conn),
) -> DealerUserOut:
    row = (
        await conn.execute(
            select(
                dealer_user_table.c.dealer_id,
                dealer_user_table.c.email,
                dealer_user_table.c.password_hash,
                dealer_user_table.c.name,
                dealer_user_table.c.dealership_name,
            ).where(dealer_user_table.c.email == payload.email.lower())
        )
    ).mappings().first()

    if row is None or not verify_password(payload.password, row["password_hash"]):
        logger.info("failed login attempt for %s", payload.email)
        raise HTTPException(status_code=401, detail="invalid email or password")

    await conn.execute(
        update(dealer_user_table)
        .where(dealer_user_table.c.dealer_id == row["dealer_id"])
        .values(last_login_at=func.now())
    )

    token = create_access_token(row["dealer_id"])
    _set_session_cookie(response, token)

    return DealerUserOut(
        dealer_id=row["dealer_id"],
        email=row["email"],
        name=row["name"],
        dealership_name=row["dealership_name"],
    )


@router.get("/me", response_model=DealerUserOut)
async def me(current_user: DealerUserOut = Depends(get_current_user)) -> DealerUserOut:
    return current_user


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    return {"status": "logged out"}
