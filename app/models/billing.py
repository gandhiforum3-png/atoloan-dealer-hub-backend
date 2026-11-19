"""
Request/response schemas for the billing API.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PlanOut(BaseModel):
    id: str
    name: str
    description: str
    monthly_price_cents: int | None
    annual_price_cents: int | None
    features: list[str]


class CreditPackOut(BaseModel):
    id: str
    name: str
    credits: int
    price_cents: int
    per_unit_cents: int


class CardInput(BaseModel):
    cardholder_name: str
    card_number: str
    exp_month: int
    exp_year: int
    cvc: str
    billing_zip: str | None = None


class SetupIntentOut(BaseModel):
    id: str
    client_secret: str
    status: str


class ConfirmPaymentMethodRequest(BaseModel):
    setup_intent_id: str
    card: CardInput
    set_default: bool = False


class PaymentMethodOut(BaseModel):
    id: str
    brand: str
    last4: str
    exp_month: int
    exp_year: int
    cardholder_name: str
    is_default: bool
    created_at: datetime


class SubscribeRequest(BaseModel):
    plan_id: str
    billing_cycle: Literal["monthly", "annual"]
    payment_method_id: str


class SubscriptionOut(BaseModel):
    id: str
    plan_id: str
    plan_name: str
    billing_cycle: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    canceled_at: datetime | None


class CancelSubscriptionRequest(BaseModel):
    cancel_immediately: bool = False


class OneTimeChargeRequest(BaseModel):
    credit_pack_id: str
    payment_method_id: str


class PaymentOut(BaseModel):
    id: str
    type: str
    description: str
    amount_cents: int
    currency: str
    status: str
    created_at: datetime


class CurrentPlanOut(BaseModel):
    billing_mode: Literal["subscription", "pay_as_you_go"]
    subscription: SubscriptionOut | None
    credit_balance: int
