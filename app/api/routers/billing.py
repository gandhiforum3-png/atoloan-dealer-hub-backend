"""
Dealer billing: subscription plans, pay-as-you-go credit packs, saved cards,
and payment history. Backed by a stub payment service (see
app/services/billing_service.py) — no real charges happen.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.billing_catalog import CREDIT_PACKS, PLANS
from app.core.dependencies import get_conn, get_current_user
from app.models.auth import DealerUserOut
from app.models.billing import (
    CancelSubscriptionRequest,
    ConfirmPaymentMethodRequest,
    CreditPackOut,
    CurrentPlanOut,
    OneTimeChargeRequest,
    PaymentMethodOut,
    PaymentOut,
    PlanOut,
    SetupIntentOut,
    SubscribeRequest,
    SubscriptionOut,
)
from app.services import billing_service

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans")
async def get_plans() -> list[PlanOut]:
    return [PlanOut(**plan) for plan in PLANS]


@router.get("/credit-packs")
async def get_credit_packs() -> list[CreditPackOut]:
    return [CreditPackOut(**pack) for pack in CREDIT_PACKS]


@router.get("/plan")
async def get_current_plan(
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> CurrentPlanOut:
    status = await billing_service.get_current_plan_status(conn, current_user.dealer_id)
    return CurrentPlanOut(**status)


@router.post("/setup-intents")
async def create_setup_intent(
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> SetupIntentOut:
    result = await billing_service.create_setup_intent(conn, current_user.dealer_id)
    return SetupIntentOut(**result)


@router.post("/payment-methods")
async def add_payment_method(
    payload: ConfirmPaymentMethodRequest,
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> PaymentMethodOut:
    try:
        result = await billing_service.confirm_payment_method(
            conn,
            current_user.dealer_id,
            payload.setup_intent_id,
            payload.card,
            payload.set_default,
        )
    except billing_service.SetupIntentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="setup intent not found") from exc
    except billing_service.CardDeclinedError as exc:
        raise HTTPException(status_code=402, detail=f"card declined: {exc.reason}") from exc
    return PaymentMethodOut(**result)


@router.get("/payment-methods")
async def list_payment_methods(
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> list[PaymentMethodOut]:
    rows = await billing_service.list_payment_methods(conn, current_user.dealer_id)
    return [PaymentMethodOut(**row) for row in rows]


@router.post("/payment-methods/{payment_method_id}/default")
async def set_default_payment_method(
    payment_method_id: str,
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> PaymentMethodOut:
    try:
        result = await billing_service.set_default_payment_method(
            conn, current_user.dealer_id, payment_method_id
        )
    except billing_service.PaymentMethodNotFoundError as exc:
        raise HTTPException(status_code=404, detail="payment method not found") from exc
    return PaymentMethodOut(**result)


@router.delete("/payment-methods/{payment_method_id}", status_code=204)
async def remove_payment_method(
    payment_method_id: str,
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> None:
    try:
        await billing_service.remove_payment_method(conn, current_user.dealer_id, payment_method_id)
    except billing_service.PaymentMethodNotFoundError as exc:
        raise HTTPException(status_code=404, detail="payment method not found") from exc
    except billing_service.PaymentMethodInUseError as exc:
        raise HTTPException(
            status_code=409, detail="this card is backing an active subscription — set a different default first"
        ) from exc


@router.post("/subscriptions")
async def subscribe(
    payload: SubscribeRequest,
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> SubscriptionOut:
    try:
        result = await billing_service.create_subscription(
            conn,
            current_user.dealer_id,
            payload.plan_id,
            payload.billing_cycle,
            payload.payment_method_id,
        )
    except billing_service.UnknownPlanError as exc:
        raise HTTPException(status_code=422, detail="unknown plan") from exc
    except billing_service.PaymentMethodNotFoundError as exc:
        raise HTTPException(status_code=404, detail="payment method not found") from exc
    except billing_service.CardDeclinedError as exc:
        raise HTTPException(status_code=402, detail=f"card declined: {exc.reason}") from exc
    return SubscriptionOut(**result)


@router.post("/subscriptions/cancel")
async def cancel_subscription(
    payload: CancelSubscriptionRequest,
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> SubscriptionOut:
    try:
        result = await billing_service.cancel_subscription(
            conn, current_user.dealer_id, payload.cancel_immediately
        )
    except billing_service.NoActiveSubscriptionError as exc:
        raise HTTPException(status_code=404, detail="no active subscription") from exc
    return SubscriptionOut(**result)


@router.post("/charges")
async def charge_one_time(
    payload: OneTimeChargeRequest,
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> PaymentOut:
    try:
        result = await billing_service.charge_one_time(
            conn, current_user.dealer_id, payload.credit_pack_id, payload.payment_method_id
        )
    except billing_service.UnknownCreditPackError as exc:
        raise HTTPException(status_code=422, detail="unknown credit pack") from exc
    except billing_service.PaymentMethodNotFoundError as exc:
        raise HTTPException(status_code=404, detail="payment method not found") from exc
    except billing_service.CardDeclinedError as exc:
        raise HTTPException(status_code=402, detail=f"card declined: {exc.reason}") from exc
    return PaymentOut(**result)


@router.get("/history")
async def get_history(
    limit: int = 50,
    current_user: DealerUserOut = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
) -> list[PaymentOut]:
    rows = await billing_service.list_payment_history(conn, current_user.dealer_id, limit)
    return [PaymentOut(**row) for row in rows]
