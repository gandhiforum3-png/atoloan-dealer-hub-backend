import pytest


@pytest.mark.asyncio
async def test_generate_qr_code_returns_url_with_dealer_id_and_image(client, logged_in_dealer):
    response = await client.post("/qr-codes", json={"label": "Showroom Entrance"})
    assert response.status_code == 200
    body = response.json()

    assert body["label"] == "Showroom Entrance"
    assert body["dealer_id"] == logged_in_dealer["dealer_id"]
    assert f"/d/{logged_in_dealer['dealer_id']}?code={body['token']}" in body["url"]
    assert body["image_data_url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_generate_without_login_returns_401(client):
    response = await client.post("/qr-codes", json={"label": "Showroom Entrance"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_regenerate_rotates_token_and_invalidates_old_code(client, logged_in_dealer):
    first = (await client.post("/qr-codes")).json()
    second = (await client.post("/qr-codes")).json()

    assert first["token"] != second["token"]

    old_scan = await client.get(
        f"/public/dealers/{logged_in_dealer['dealer_id']}", params={"code": first["token"]}
    )
    assert old_scan.status_code == 404

    new_scan = await client.get(
        f"/public/dealers/{logged_in_dealer['dealer_id']}", params={"code": second["token"]}
    )
    assert new_scan.status_code == 200
    assert new_scan.json() == {
        "dealer_id": logged_in_dealer["dealer_id"],
        "dealership_name": "Test Auto Group",
    }


@pytest.mark.asyncio
async def test_update_label_keeps_same_token(client, logged_in_dealer):
    generated = (await client.post("/qr-codes")).json()

    updated = await client.patch("/qr-codes/me", json={"label": "Front Desk"})
    assert updated.status_code == 200
    assert updated.json()["label"] == "Front Desk"
    assert updated.json()["token"] == generated["token"]


@pytest.mark.asyncio
async def test_scan_unknown_dealer_returns_404(client):
    response = await client.get("/public/dealers/DLR-999999", params={"code": "bogus"})
    assert response.status_code == 404


async def test_scan_of_deactivated_dealer_returns_404(client, logged_in_dealer):
    from sqlalchemy import update

    from app.db import get_engine
    from app.models.dealer_user_table import dealer_user_table

    token = (await client.post("/qr-codes", json={"label": "Front desk"})).json()["token"]
    url, params = f"/public/dealers/{logged_in_dealer['dealer_id']}", {"code": token}
    assert (await client.get(url, params=params)).status_code == 200

    async with get_engine().begin() as conn:
        await conn.execute(
            update(dealer_user_table)
            .where(dealer_user_table.c.dealer_id == logged_in_dealer["dealer_id"])
            .values(is_active=False)
        )
    assert (await client.get(url, params=params)).status_code == 404
