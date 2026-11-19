"""
Stub payment service for dealer billing.

Mimics Stripe's object shapes and call signatures (SetupIntent, PaymentMethod,
Subscription, charge/invoice) closely enough that a real `stripe` SDK
integration can be dropped in later by rewriting only this file. No network
calls are made — every "payment" is resolved synchronously against Postgres.
The one place this diverges from the real integration on purpose: card
declines are only simulated when a card is first added (confirm_payment_method);
once a card is saved, charging it here always succeeds, since this stub has
no notion of a card's balance changing over time.

Test card numbers honored by confirm_payment_method (Stripe's own published
test numbers, so the same numbers work once real Stripe is wired in):
  4242 4242 4242 4242   -> succeeds
  4000 0000 0000 0002   -> generic decline
  4000 0000 0000 9995   -> insufficient funds decline
Any other number that passes a Luhn check also succeeds, so manual testing
isn't limited to a single "good" number.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.billing_catalog import get_credit_pack, get_plan
from app.models.billing import CardInput
from app.models.dealer_billing_table import dealer_billing_table
from app.models.payment_method_table import payment_method_table
from app.models.payment_table import payment_table
from app.models.setup_intent_table import setup_intent_table
from app.models.subscription_table import subscription_table

logger = logging.getLogger(__name__)

ACTIVE_SUBSCRIPTION_STATUSES = ("active", "past_due")

_DECLINE_NUMBERS = {
    "4000000000000002": "card_declined",
    "4000000000009995": "insufficient_funds",
}


class BillingServiceUnavailableError(Exception):
    """Defined for interface parity with a real Stripe integration (network
    failure). Never raised by the stub."""


class CardDeclinedError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class SetupIntentNotFoundError(Exception):
    pass


class PaymentMethodNotFoundError(Exception):
    pass


class UnknownPlanError(Exception):
    pass


class UnknownCreditPackError(Exception):
    pass


class NoActiveSubscriptionError(Exception):
    pass


class PaymentMethodInUseError(Exception):
    pass


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def _luhn_checksum(number: str) -> bool:
    digits = [int(d) for d in number]
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _detect_brand(cleaned_number: str) -> str:
    if cleaned_number.startswith("4"):
        return "visa"
    if cleaned_number[:2] in {"51", "52", "53", "54", "55"}:
        return "mastercard"
    if cleaned_number[:2] in {"34", "37"}:
        return "amex"
    if cleaned_number.startswith("6"):
        return "discover"
    return "card"


def _validate_card(card: CardInput) -> str:
    """Returns the detected brand, or raises CardDeclinedError."""
    cleaned = card.card_number.replace(" ", "").replace("-", "")

    now = datetime.now(timezone.utc)
    if card.exp_year < now.year or (card.exp_year == now.year and card.exp_month < now.month):
        raise CardDeclinedError("expired_card")

    if len(card.cvc) not in (3, 4):
        raise CardDeclinedError("invalid_cvc")

    if cleaned in _DECLINE_NUMBERS:
        raise CardDeclinedError(_DECLINE_NUMBERS[cleaned])

    if not cleaned.isdigit() or not _luhn_checksum(cleaned):
        raise CardDeclinedError("card_declined")

    return _detect_brand(cleaned)


async def get_or_create_billing_profile(conn: AsyncConnection, dealer_id: str) -> dict:
    row = (
        await conn.execute(
            select(dealer_billing_table).where(dealer_billing_table.c.dealer_id == dealer_id)
        )
    ).mappings().first()
    if row is not None:
        return dict(row)

    await conn.execute(
        insert(dealer_billing_table).values(
            dealer_id=dealer_id, customer_id=_generate_id("cus"), credit_balance=0
        )
    )
    row = (
        await conn.execute(
            select(dealer_billing_table).where(dealer_billing_table.c.dealer_id == dealer_id)
        )
    ).mappings().first()
    return dict(row)


async def create_setup_intent(conn: AsyncConnection, dealer_id: str) -> dict:
    await get_or_create_billing_profile(conn, dealer_id)

    setup_intent_id = _generate_id("seti")
    client_secret = f"{setup_intent_id}_secret_{secrets.token_hex(8)}"
    await conn.execute(
        insert(setup_intent_table).values(
            id=setup_intent_id, dealer_id=dealer_id, status="requires_payment_method"
        )
    )
    return {"id": setup_intent_id, "client_secret": client_secret, "status": "requires_payment_method"}


async def confirm_payment_method(
    conn: AsyncConnection,
    dealer_id: str,
    setup_intent_id: str,
    card: CardInput,
    set_default: bool,
) -> dict:
    setup_intent = (
        await conn.execute(
            select(setup_intent_table).where(
                setup_intent_table.c.id == setup_intent_id,
                setup_intent_table.c.dealer_id == dealer_id,
            )
        )
    ).mappings().first()
    if setup_intent is None:
        raise SetupIntentNotFoundError(setup_intent_id)

    brand = _validate_card(card)
    cleaned = card.card_number.replace(" ", "").replace("-", "")
    last4 = cleaned[-4:]

    existing_count = (
        await conn.execute(
            select(payment_method_table.c.id).where(payment_method_table.c.dealer_id == dealer_id)
        )
    ).all()
    is_first_card = len(existing_count) == 0
    should_default = set_default or is_first_card

    payment_method_id = _generate_id("pm")
    await conn.execute(
        insert(payment_method_table).values(
            id=payment_method_id,
            dealer_id=dealer_id,
            brand=brand,
            last4=last4,
            exp_month=card.exp_month,
            exp_year=card.exp_year,
            cardholder_name=card.cardholder_name,
            billing_zip=card.billing_zip,
            is_default=should_default,
        )
    )

    if should_default:
        await conn.execute(
            update(payment_method_table)
            .where(
                payment_method_table.c.dealer_id == dealer_id,
                payment_method_table.c.id != payment_method_id,
            )
            .values(is_default=False)
        )
        await get_or_create_billing_profile(conn, dealer_id)
        await conn.execute(
            update(dealer_billing_table)
            .where(dealer_billing_table.c.dealer_id == dealer_id)
            .values(default_payment_method_id=payment_method_id)
        )

    await conn.execute(
        update(setup_intent_table)
        .where(setup_intent_table.c.id == setup_intent_id)
        .values(status="succeeded", payment_method_id=payment_method_id)
    )

    row = (
        await conn.execute(
            select(payment_method_table).where(payment_method_table.c.id == payment_method_id)
        )
    ).mappings().first()
    return dict(row)


async def list_payment_methods(conn: AsyncConnection, dealer_id: str) -> list[dict]:
    rows = (
        await conn.execute(
            select(payment_method_table)
            .where(payment_method_table.c.dealer_id == dealer_id)
            .order_by(payment_method_table.c.is_default.desc(), payment_method_table.c.created_at.asc())
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def set_default_payment_method(conn: AsyncConnection, dealer_id: str, payment_method_id: str) -> dict:
    row = (
        await conn.execute(
            select(payment_method_table).where(
                payment_method_table.c.id == payment_method_id,
                payment_method_table.c.dealer_id == dealer_id,
            )
        )
    ).mappings().first()
    if row is None:
        raise PaymentMethodNotFoundError(payment_method_id)

    await conn.execute(
        update(payment_method_table)
        .where(payment_method_table.c.dealer_id == dealer_id)
        .values(is_default=(payment_method_table.c.id == payment_method_id))
    )
    await get_or_create_billing_profile(conn, dealer_id)
    await conn.execute(
        update(dealer_billing_table)
        .where(dealer_billing_table.c.dealer_id == dealer_id)
        .values(default_payment_method_id=payment_method_id)
    )

    updated = (
        await conn.execute(
            select(payment_method_table).where(payment_method_table.c.id == payment_method_id)
        )
    ).mappings().first()
    return dict(updated)


async def remove_payment_method(conn: AsyncConnection, dealer_id: str, payment_method_id: str) -> None:
    row = (
        await conn.execute(
            select(payment_method_table).where(
                payment_method_table.c.id == payment_method_id,
                payment_method_table.c.dealer_id == dealer_id,
            )
        )
    ).mappings().first()
    if row is None:
        raise PaymentMethodNotFoundError(payment_method_id)

    in_use = (
        await conn.execute(
            select(subscription_table.c.id).where(
                subscription_table.c.dealer_id == dealer_id,
                subscription_table.c.payment_method_id == payment_method_id,
                subscription_table.c.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
            )
        )
    ).first()
    if in_use is not None:
        raise PaymentMethodInUseError(payment_method_id)

    await conn.execute(payment_method_table.delete().where(payment_method_table.c.id == payment_method_id))

    if row["is_default"]:
        await conn.execute(
            update(dealer_billing_table)
            .where(dealer_billing_table.c.dealer_id == dealer_id)
            .values(default_payment_method_id=None)
        )


def _subscription_to_dict(row: dict) -> dict:
    plan = get_plan(row["plan_id"])
    return {
        "id": row["id"],
        "plan_id": row["plan_id"],
        "plan_name": plan["name"] if plan else row["plan_id"],
        "billing_cycle": row["billing_cycle"],
        "status": row["status"],
        "current_period_start": row["current_period_start"],
        "current_period_end": row["current_period_end"],
        "cancel_at_period_end": row["cancel_at_period_end"],
        "canceled_at": row["canceled_at"],
    }


async def _get_active_subscription(conn: AsyncConnection, dealer_id: str) -> dict | None:
    row = (
        await conn.execute(
            select(subscription_table)
            .where(
                subscription_table.c.dealer_id == dealer_id,
                subscription_table.c.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
            )
            .order_by(subscription_table.c.created_at.desc())
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def create_subscription(
    conn: AsyncConnection,
    dealer_id: str,
    plan_id: str,
    billing_cycle: str,
    payment_method_id: str,
) -> dict:
    plan = get_plan(plan_id)
    if plan is None or plan.get("monthly_price_cents") is None:
        raise UnknownPlanError(plan_id)

    payment_method = (
        await conn.execute(
            select(payment_method_table).where(
                payment_method_table.c.id == payment_method_id,
                payment_method_table.c.dealer_id == dealer_id,
            )
        )
    ).mappings().first()
    if payment_method is None:
        raise PaymentMethodNotFoundError(payment_method_id)

    existing = await _get_active_subscription(conn, dealer_id)
    if existing is not None:
        await conn.execute(
            update(subscription_table)
            .where(subscription_table.c.id == existing["id"])
            .values(status="canceled", canceled_at=datetime.now(timezone.utc))
        )

    now = datetime.now(timezone.utc)
    period_end = now + (timedelta(days=365) if billing_cycle == "annual" else timedelta(days=30))

    subscription_id = _generate_id("sub")
    await conn.execute(
        insert(subscription_table).values(
            id=subscription_id,
            dealer_id=dealer_id,
            plan_id=plan_id,
            billing_cycle=billing_cycle,
            status="active",
            payment_method_id=payment_method_id,
            current_period_start=now,
            current_period_end=period_end,
            cancel_at_period_end=False,
        )
    )

    amount_cents = plan["annual_price_cents"] if billing_cycle == "annual" else plan["monthly_price_cents"]
    await conn.execute(
        insert(payment_table).values(
            id=_generate_id("in"),
            dealer_id=dealer_id,
            type="subscription",
            description=f"{plan['name']} — {billing_cycle} subscription",
            amount_cents=amount_cents,
            currency="usd",
            status="succeeded",
            payment_method_id=payment_method_id,
            subscription_id=subscription_id,
        )
    )

    row = (
        await conn.execute(select(subscription_table).where(subscription_table.c.id == subscription_id))
    ).mappings().first()
    return _subscription_to_dict(dict(row))


async def cancel_subscription(conn: AsyncConnection, dealer_id: str, cancel_immediately: bool) -> dict:
    existing = await _get_active_subscription(conn, dealer_id)
    if existing is None:
        raise NoActiveSubscriptionError(dealer_id)

    if cancel_immediately:
        values = {"status": "canceled", "canceled_at": datetime.now(timezone.utc)}
    else:
        values = {"cancel_at_period_end": True}

    await conn.execute(
        update(subscription_table).where(subscription_table.c.id == existing["id"]).values(**values)
    )

    row = (
        await conn.execute(select(subscription_table).where(subscription_table.c.id == existing["id"]))
    ).mappings().first()
    return _subscription_to_dict(dict(row))


async def charge_one_time(
    conn: AsyncConnection, dealer_id: str, credit_pack_id: str, payment_method_id: str
) -> dict:
    pack = get_credit_pack(credit_pack_id)
    if pack is None:
        raise UnknownCreditPackError(credit_pack_id)

    payment_method = (
        await conn.execute(
            select(payment_method_table).where(
                payment_method_table.c.id == payment_method_id,
                payment_method_table.c.dealer_id == dealer_id,
            )
        )
    ).mappings().first()
    if payment_method is None:
        raise PaymentMethodNotFoundError(payment_method_id)

    payment_id = _generate_id("pi")
    await conn.execute(
        insert(payment_table).values(
            id=payment_id,
            dealer_id=dealer_id,
            type="one_time",
            description=f"Soft-pull credits — {pack['name']}",
            amount_cents=pack["price_cents"],
            currency="usd",
            status="succeeded",
            payment_method_id=payment_method_id,
            credit_pack_id=credit_pack_id,
        )
    )

    await get_or_create_billing_profile(conn, dealer_id)
    await conn.execute(
        update(dealer_billing_table)
        .where(dealer_billing_table.c.dealer_id == dealer_id)
        .values(credit_balance=dealer_billing_table.c.credit_balance + pack["credits"])
    )

    row = (await conn.execute(select(payment_table).where(payment_table.c.id == payment_id))).mappings().first()
    return dict(row)


async def list_payment_history(conn: AsyncConnection, dealer_id: str, limit: int = 50) -> list[dict]:
    rows = (
        await conn.execute(
            select(payment_table)
            .where(payment_table.c.dealer_id == dealer_id)
            .order_by(payment_table.c.created_at.desc())
            .limit(limit)
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def get_current_plan_status(conn: AsyncConnection, dealer_id: str) -> dict:
    profile = await get_or_create_billing_profile(conn, dealer_id)
    subscription = await _get_active_subscription(conn, dealer_id)

    return {
        "billing_mode": "subscription" if subscription is not None else "pay_as_you_go",
        "subscription": _subscription_to_dict(subscription) if subscription is not None else None,
        "credit_balance": profile["credit_balance"],
    }
