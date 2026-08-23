import pytest

from app.models.bank import BankOut
from app.services.bank_network_service import BankNetworkUnavailableError


@pytest.mark.asyncio
async def test_get_banks_without_login_returns_401(client):
    response = await client.get("/banks")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_banks_success(client, logged_in_dealer, monkeypatch):
    async def fake_list_banks():
        return [BankOut(id=1, name="KeyPoint Credit Union"), BankOut(id=3, name="First City Credit Union")]

    monkeypatch.setattr("app.api.routers.banks.list_banks", fake_list_banks)

    response = await client.get("/banks")
    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "name": "KeyPoint Credit Union"},
        {"id": 3, "name": "First City Credit Union"},
    ]


@pytest.mark.asyncio
async def test_get_banks_returns_502_when_bank_network_unavailable(client, logged_in_dealer, monkeypatch):
    async def failing_list_banks():
        raise BankNetworkUnavailableError("connection refused")

    monkeypatch.setattr("app.api.routers.banks.list_banks", failing_list_banks)

    response = await client.get("/banks")
    assert response.status_code == 502


def _fake_bank_list(monkeypatch):
    async def fake_list_banks():
        return [
            BankOut(id=1, name="KeyPoint Credit Union"),
            BankOut(id=3, name="First City Credit Union"),
            BankOut(id=4, name="American First Credit Union"),
        ]

    monkeypatch.setattr("app.services.bank_network_service.list_banks", fake_list_banks)


@pytest.mark.asyncio
async def test_get_network_without_login_returns_401(client):
    response = await client.get("/banks/network")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_network_defaults_to_empty(client, logged_in_dealer):
    response = await client.get("/banks/network")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_post_network_saves_selected_banks(client, logged_in_dealer, monkeypatch):
    _fake_bank_list(monkeypatch)

    response = await client.post("/banks/network", json={"bank_ids": [1, 3]})
    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "name": "KeyPoint Credit Union"},
        {"id": 3, "name": "First City Credit Union"},
    ]

    fetched = await client.get("/banks/network")
    assert fetched.status_code == 200
    assert {bank["id"] for bank in fetched.json()} == {1, 3}


@pytest.mark.asyncio
async def test_post_network_replaces_previous_selection(client, logged_in_dealer, monkeypatch):
    _fake_bank_list(monkeypatch)

    await client.post("/banks/network", json={"bank_ids": [1, 3]})
    second = await client.post("/banks/network", json={"bank_ids": [4]})

    assert second.status_code == 200
    assert second.json() == [{"id": 4, "name": "American First Credit Union"}]


@pytest.mark.asyncio
async def test_post_network_rejects_unknown_bank_id(client, logged_in_dealer, monkeypatch):
    _fake_bank_list(monkeypatch)

    response = await client.post("/banks/network", json={"bank_ids": [1, 999]})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_network_without_login_returns_401(client):
    response = await client.post("/banks/network", json={"bank_ids": [1]})
    assert response.status_code == 401
