"""
/admin/dealers access control and account-state enforcement
(inactive accounts, forced password change, audit log).
"""
import pytest
from sqlalchemy import select, update

from app.db import get_engine
from app.models.dealer_user_table import admin_audit_table, dealer_user_table


async def _set(dealer_id: str, **values) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(update(dealer_user_table).where(dealer_user_table.c.dealer_id == dealer_id).values(**values))


@pytest.mark.asyncio
async def test_non_admin_cannot_use_admin_routes(client, logged_in_dealer):
    assert (await client.get("/admin/dealers")).status_code == 403
    response = await client.post(f"/admin/dealers/{logged_in_dealer['dealer_id']}/reset-password")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_flag_is_read_from_db_each_request(client, logged_in_dealer):
    await _set(logged_in_dealer["dealer_id"], is_admin=True)
    assert (await client.get("/admin/dealers")).status_code == 200
    await _set(logged_in_dealer["dealer_id"], is_admin=False)
    assert (await client.get("/admin/dealers")).status_code == 403


@pytest.mark.asyncio
async def test_deactivated_dealer_is_signed_out_and_cannot_log_in(client, logged_in_dealer):
    await _set(logged_in_dealer["dealer_id"], is_active=False)
    assert (await client.get("/auth/me")).status_code == 401

    response = await client.post(
        "/auth/login", json={"email": logged_in_dealer["email"], "password": logged_in_dealer["password"]}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid email or password"


@pytest.mark.asyncio
async def test_reset_forces_password_change_and_is_audited(client, logged_in_dealer):
    await _set(logged_in_dealer["dealer_id"], is_admin=True)
    created = await client.post(
        "/admin/dealers",
        json={"email": "target-dealer@example.com", "name": "T", "dealership_name": "T Auto"},
    )
    assert created.status_code == 201
    target_id = created.json()["dealer_id"]
    # Admin never chooses the password — a one-time one comes back once
    assert len(created.json()["temporary_password"]) >= 16
    assert created.json()["must_change_password"] is True
    try:
        reset = await client.post(f"/admin/dealers/{target_id}/reset-password")
        temp = reset.json()["temporary_password"]

        # The dealer signs in with the temporary password: only /auth/* works until it's changed
        await client.post("/auth/logout")
        client.cookies.clear()
        login = await client.post("/auth/login", json={"email": "target-dealer@example.com", "password": temp})
        assert login.json()["must_change_password"] is True
        assert (await client.get("/banks/network")).status_code == 403

        changed = await client.post(
            "/auth/change-password", json={"current_password": temp, "new_password": "a-new-long-password"}
        )
        assert changed.status_code == 200
        assert (await client.get("/banks/network")).status_code == 200

        async with get_engine().connect() as conn:
            rows = (
                await conn.execute(
                    select(admin_audit_table.c.action, admin_audit_table.c.actor_dealer_id).where(
                        admin_audit_table.c.target_type == "dealer", admin_audit_table.c.target_id == target_id
                    )
                )
            ).all()
        assert {r.action for r in rows} == {"create_dealer", "reset_password"}
        assert {r.actor_dealer_id for r in rows} == {logged_in_dealer["dealer_id"]}
    finally:
        async with get_engine().begin() as conn:
            await conn.execute(admin_audit_table.delete().where(admin_audit_table.c.target_id == target_id))
            await conn.execute(dealer_user_table.delete().where(dealer_user_table.c.dealer_id == target_id))


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_self(client, logged_in_dealer):
    await _set(logged_in_dealer["dealer_id"], is_admin=True)
    response = await client.patch(f"/admin/dealers/{logged_in_dealer['dealer_id']}", json={"is_active": False})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_password_over_72_bytes_is_422_not_500(client):
    response = await client.post("/auth/login", json={"email": "a@example.com", "password": "x" * 100})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_can_grant_but_not_drop_own_admin(client, logged_in_dealer):
    await _set(logged_in_dealer["dealer_id"], is_admin=True)
    response = await client.patch(f"/admin/dealers/{logged_in_dealer['dealer_id']}", json={"is_admin": False})
    assert response.status_code == 422
