import uuid

import pytest
from sqlalchemy import insert

from app.db import get_engine
from app.models.dealer_user_table import dealer_user_table, next_dealer_id
from app.services.auth_service import hash_password


@pytest.fixture
async def dealer_user():
    email = f"{uuid.uuid4()}@example.com"
    password = "correct-horse-battery-staple"
    engine = get_engine()
    async with engine.begin() as conn:
        dealer_id = await next_dealer_id(conn)
        await conn.execute(
            insert(dealer_user_table).values(
                dealer_id=dealer_id,
                email=email,
                password_hash=hash_password(password),
                name="Test Dealer",
                dealership_name="Test Auto Group",
            )
        )
    yield {"dealer_id": dealer_id, "email": email, "password": password}
    async with engine.begin() as conn:
        await conn.execute(
            dealer_user_table.delete().where(dealer_user_table.c.email == email)
        )


@pytest.mark.asyncio
async def test_login_success_sets_cookie_and_returns_user(client, dealer_user):
    response = await client.post(
        "/auth/login",
        json={"email": dealer_user["email"], "password": dealer_user["password"]},
    )
    assert response.status_code == 200
    assert response.json()["email"] == dealer_user["email"]
    assert response.json()["dealer_id"] == dealer_user["dealer_id"]
    assert "dealerhub_session" in response.cookies


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client, dealer_user):
    response = await client.post(
        "/auth/login",
        json={"email": dealer_user["email"], "password": "wrong-password"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_without_cookie_returns_401(client):
    response = await client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_then_me_returns_same_user(client, dealer_user):
    login_response = await client.post(
        "/auth/login",
        json={"email": dealer_user["email"], "password": dealer_user["password"]},
    )
    assert login_response.status_code == 200

    me_response = await client.get("/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == dealer_user["email"]
