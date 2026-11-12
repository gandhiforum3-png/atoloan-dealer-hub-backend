"""
Server-to-server endpoints under /internal — no dealer login, but the
shared X-Service-Token is required.
"""
import pytest

from app.models.bank import BankOut

SERVICE_HEADERS = {"X-Service-Token": "test-service-token"}


def _fake_bank_list(monkeypatch):
    async def fake_list_banks():
        return [
            BankOut(id=1, name="KeyPoint Credit Union"),
            BankOut(id=3, name="First City Credit Union"),
            BankOut(id=4, name="American First Credit Union"),
        ]

    monkeypatch.setattr("app.services.bank_network_service.list_banks", fake_list_banks)


@pytest.mark.asyncio
async def test_bank_ids_does_not_require_login(client):
    response = await client.get("/internal/dealers/D-DOES-NOT-EXIST/bank-ids", headers=SERVICE_HEADERS)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_unknown_dealer_returns_empty_list(client):
    response = await client.get("/internal/dealers/D-DOES-NOT-EXIST/bank-ids", headers=SERVICE_HEADERS)
    assert response.json() == {"dealer_id": "D-DOES-NOT-EXIST", "bank_ids": []}


@pytest.mark.asyncio
async def test_returns_dealer_network_bank_ids(client, logged_in_dealer, monkeypatch):
    _fake_bank_list(monkeypatch)
    await client.post("/banks/network", json={"bank_ids": [1, 4]})

    response = await client.get(f"/internal/dealers/{logged_in_dealer['dealer_id']}/bank-ids", headers=SERVICE_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["dealer_id"] == logged_in_dealer["dealer_id"]
    assert sorted(body["bank_ids"]) == [1, 4]


@pytest.mark.asyncio
async def test_dealer_with_no_selection_returns_empty_list(client, logged_in_dealer):
    response = await client.get(f"/internal/dealers/{logged_in_dealer['dealer_id']}/bank-ids", headers=SERVICE_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"dealer_id": logged_in_dealer["dealer_id"], "bank_ids": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "wrong"}])
async def test_bank_ids_requires_service_token(client, headers):
    response = await client.get("/internal/dealers/D-DOES-NOT-EXIST/bank-ids", headers=headers)
    assert response.status_code == 401
