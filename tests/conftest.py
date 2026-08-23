import uuid

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import insert

from app.db import get_engine
from app.main import app
from app.models.dealer_user_table import dealer_user_table, next_dealer_id
from app.services.auth_service import hash_password


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def logged_in_dealer(client):
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

    login_response = await client.post("/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200

    yield {"dealer_id": dealer_id}

    async with engine.begin() as conn:
        await conn.execute(
            dealer_user_table.delete().where(dealer_user_table.c.dealer_id == dealer_id)
        )
