"""
Dealer sign-in endpoints: login, current-session lookup, logout.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import get_settings
from app.core.dependencies import get_conn, get_current_user
from app.core.security import login_throttle
from app.models.auth import ChangePasswordRequest, DealerUserOut, LoginRequest
from app.models.dealer_user_table import dealer_user_table
from app.services.auth_service import create_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

# Checked when the email doesn't exist, so unknown and known emails take the
# same bcrypt time and response timing doesn't reveal which accounts exist.
_DUMMY_PASSWORD_HASH = hash_password("timing-equaliser-not-a-real-password")


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
    request: Request,
    response: Response,
    conn: AsyncConnection = Depends(get_conn),
) -> DealerUserOut:
    email = payload.email.lower()
    client_ip = request.client.host if request.client else "unknown"
    login_throttle.check(email, client_ip)

    row = (
        await conn.execute(
            select(
                dealer_user_table.c.dealer_id,
                dealer_user_table.c.email,
                dealer_user_table.c.password_hash,
                dealer_user_table.c.name,
                dealer_user_table.c.dealership_name,
                dealer_user_table.c.is_admin,
                dealer_user_table.c.is_active,
                dealer_user_table.c.must_change_password,
            ).where(dealer_user_table.c.email == email)
        )
    ).mappings().first()

    # bcrypt is CPU-bound (~250ms): off the event loop so logins can't stall the API
    password_ok = await run_in_threadpool(
        verify_password, payload.password, row["password_hash"] if row else _DUMMY_PASSWORD_HASH
    )
    # Deactivated accounts get the same answer as a wrong password
    if row is None or not password_ok or not row["is_active"]:
        login_throttle.record_failure(email, client_ip)
        logger.info("failed login attempt from %s", client_ip)
        raise HTTPException(status_code=401, detail="invalid email or password")
    login_throttle.reset(email, client_ip)

    await conn.execute(
        update(dealer_user_table)
        .where(dealer_user_table.c.dealer_id == row["dealer_id"])
        .values(last_login_at=func.now())
    )

    token = create_access_token(row["dealer_id"], row["password_hash"])
    _set_session_cookie(response, token)

    return DealerUserOut(**{k: v for k, v in row.items() if k not in ("password_hash", "is_active")})


@router.post("/change-password", response_model=DealerUserOut)
async def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> DealerUserOut:
    current_hash = await conn.scalar(
        select(dealer_user_table.c.password_hash).where(dealer_user_table.c.dealer_id == current_user.dealer_id)
    )
    if not await run_in_threadpool(verify_password, payload.current_password, current_hash):
        raise HTTPException(status_code=401, detail="current password is incorrect")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=422, detail="new password must differ from the current one")

    new_hash = await run_in_threadpool(hash_password, payload.new_password)
    await conn.execute(
        update(dealer_user_table)
        .where(dealer_user_table.c.dealer_id == current_user.dealer_id)
        .values(password_hash=new_hash, must_change_password=False)
    )
    # The old session is now revoked (password version changed) — issue a fresh one
    _set_session_cookie(response, create_access_token(current_user.dealer_id, new_hash))
    return current_user.model_copy(update={"must_change_password": False})


@router.get("/me", response_model=DealerUserOut)
async def me(current_user: DealerUserOut = Depends(get_current_user)) -> DealerUserOut:
    return current_user


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    return {"status": "logged out"}
