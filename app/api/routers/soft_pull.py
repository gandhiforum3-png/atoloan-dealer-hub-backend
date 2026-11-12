"""
Dealer-facing soft-pull endpoint: runs a 700Credit pre-qualification and
bank match through atoloan-backend, scoped to the authenticated dealer's
own bank network.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.dependencies import get_current_user
from app.models.auth import DealerUserOut
from app.services.soft_pull_service import SoftPullUnavailableError, run_soft_pull

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/soft-pull", tags=["soft-pull"])


@router.post("")
async def submit_soft_pull(
    request: Request,
    current_user: DealerUserOut = Depends(get_current_user),
) -> dict:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid request body")

    # dealer_id always comes from the authenticated session, never from the
    # client payload — otherwise a dealer could pass another dealer_id and
    # search that dealer's bank network instead of their own.
    payload["dealer_id"] = current_user.dealer_id
    # FCRA: the dealer certifies the applicant's consent; atoloan-backend
    # refuses the pull without it and records when it was given.
    if payload.get("consent") is not True:
        raise HTTPException(status_code=400, detail="applicant consent is required")

    try:
        status_code, body = await run_soft_pull(payload)
    except SoftPullUnavailableError as exc:
        raise HTTPException(
            status_code=502, detail="soft pull service is currently unavailable"
        ) from exc

    if status_code >= 400:
        detail = body.get("detail") if isinstance(body, dict) else None
        raise HTTPException(status_code=status_code, detail=detail or "soft pull request failed")

    return body
