import pytest

CARD_SUCCESS = "4242 4242 4242 4242"
CARD_DECLINE = "4000 0000 0000 0002"


def _card_payload(card_number=CARD_SUCCESS, **overrides):
    payload = {
        "cardholder_name": "Marina Albrecht",
        "card_number": card_number,
        "exp_month": 12,
        "exp_year": 2035,
        "cvc": "123",
        "billing_zip": "94103",
    }
    payload.update(overrides)
    return payload


async def _add_card(client, card_number=CARD_SUCCESS, set_default=True):
    setup = await client.post("/billing/setup-intents")
    assert setup.status_code == 200
    response = await client.post(
        "/billing/payment-methods",
        json={
            "setup_intent_id": setup.json()["id"],
            "card": _card_payload(card_number),
            "set_default": set_default,
        },
    )
    return response


@pytest.mark.asyncio
async def test_get_plans_returns_catalog(client):
    response = await client.get("/billing/plans")
    assert response.status_code == 200
    plan_ids = {plan["id"] for plan in response.json()}
    assert {"solo-lot", "multi-lot", "dealer-group"} == plan_ids


@pytest.mark.asyncio
async def test_get_credit_packs_returns_catalog(client):
    response = await client.get("/billing/credit-packs")
    assert response.status_code == 200
    pack_ids = {pack["id"] for pack in response.json()}
    assert {"pack-10", "pack-50", "pack-100"} == pack_ids


@pytest.mark.asyncio
async def test_get_plan_without_login_returns_401(client):
    response = await client.get("/billing/plan")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_plan_defaults_to_pay_as_you_go(client, logged_in_dealer):
    response = await client.get("/billing/plan")
    assert response.status_code == 200
    assert response.json() == {
        "billing_mode": "pay_as_you_go",
        "subscription": None,
        "credit_balance": 0,
    }


@pytest.mark.asyncio
async def test_create_setup_intent_requires_login(client):
    response = await client.post("/billing/setup-intents")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_add_payment_method_success(client, logged_in_dealer):
    response = await _add_card(client)
    assert response.status_code == 200
    body = response.json()
    assert body["brand"] == "visa"
    assert body["last4"] == "4242"
    assert body["is_default"] is True


@pytest.mark.asyncio
async def test_add_payment_method_declined_returns_402(client, logged_in_dealer):
    response = await _add_card(client, card_number=CARD_DECLINE)
    assert response.status_code == 402


@pytest.mark.asyncio
async def test_add_payment_method_unknown_setup_intent_returns_404(client, logged_in_dealer):
    response = await client.post(
        "/billing/payment-methods",
        json={"setup_intent_id": "seti_doesnotexist", "card": _card_payload(), "set_default": True},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_payment_methods_empty_by_default(client, logged_in_dealer):
    response = await client.get("/billing/payment-methods")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_set_default_payment_method_not_found_returns_404(client, logged_in_dealer):
    response = await client.post("/billing/payment-methods/pm_doesnotexist/default")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_remove_payment_method_not_found_returns_404(client, logged_in_dealer):
    response = await client.delete("/billing/payment-methods/pm_doesnotexist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_remove_payment_method_in_use_returns_409(client, logged_in_dealer):
    card = (await _add_card(client)).json()

    subscribe = await client.post(
        "/billing/subscriptions",
        json={"plan_id": "solo-lot", "billing_cycle": "monthly", "payment_method_id": card["id"]},
    )
    assert subscribe.status_code == 200

    response = await client.delete(f"/billing/payment-methods/{card['id']}")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_subscribe_success_returns_subscription(client, logged_in_dealer):
    card = (await _add_card(client)).json()

    response = await client.post(
        "/billing/subscriptions",
        json={"plan_id": "multi-lot", "billing_cycle": "monthly", "payment_method_id": card["id"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan_id"] == "multi-lot"
    assert body["status"] == "active"
    assert body["billing_cycle"] == "monthly"


@pytest.mark.asyncio
async def test_subscribe_unknown_plan_returns_422(client, logged_in_dealer):
    card = (await _add_card(client)).json()

    response = await client.post(
        "/billing/subscriptions",
        json={"plan_id": "not-a-real-plan", "billing_cycle": "monthly", "payment_method_id": card["id"]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_subscribe_unknown_payment_method_returns_404(client, logged_in_dealer):
    response = await client.post(
        "/billing/subscriptions",
        json={"plan_id": "solo-lot", "billing_cycle": "monthly", "payment_method_id": "pm_doesnotexist"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_subscription_without_active_subscription_returns_404(client, logged_in_dealer):
    response = await client.post("/billing/subscriptions/cancel", json={})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_subscribe_then_cancel_immediately_updates_status(client, logged_in_dealer):
    card = (await _add_card(client)).json()
    await client.post(
        "/billing/subscriptions",
        json={"plan_id": "solo-lot", "billing_cycle": "monthly", "payment_method_id": card["id"]},
    )

    response = await client.post("/billing/subscriptions/cancel", json={"cancel_immediately": True})
    assert response.status_code == 200
    assert response.json()["status"] == "canceled"

    current = await client.get("/billing/plan")
    assert current.json()["billing_mode"] == "pay_as_you_go"


@pytest.mark.asyncio
async def test_charge_one_time_success_increments_credit_balance(client, logged_in_dealer):
    card = (await _add_card(client)).json()

    response = await client.post(
        "/billing/charges", json={"credit_pack_id": "pack-10", "payment_method_id": card["id"]}
    )
    assert response.status_code == 200
    assert response.json()["amount_cents"] == 4500

    current = await client.get("/billing/plan")
    assert current.json()["credit_balance"] == 10


@pytest.mark.asyncio
async def test_charge_one_time_unknown_pack_returns_422(client, logged_in_dealer):
    card = (await _add_card(client)).json()

    response = await client.post(
        "/billing/charges", json={"credit_pack_id": "not-a-real-pack", "payment_method_id": card["id"]}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_history_returns_payments_most_recent_first(client, logged_in_dealer):
    card = (await _add_card(client)).json()
    await client.post(
        "/billing/subscriptions",
        json={"plan_id": "solo-lot", "billing_cycle": "monthly", "payment_method_id": card["id"]},
    )
    await client.post(
        "/billing/charges", json={"credit_pack_id": "pack-10", "payment_method_id": card["id"]}
    )

    response = await client.get("/billing/history")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["type"] == "one_time"
    assert body[1]["type"] == "subscription"
