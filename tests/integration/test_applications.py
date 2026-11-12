import pytest

from app.services.applications_service import ApplicationsUnavailableError


@pytest.mark.asyncio
async def test_get_applications_without_login_returns_401(client):
    response = await client.get("/applications")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_applications_success(client, logged_in_dealer, monkeypatch):
    async def fake_list_applications(dealer_id, limit, offset):
        assert dealer_id == logged_in_dealer["dealer_id"]
        assert (limit, offset) == (10, 20)
        return {"applications": [{"id": 1, "first_name": "Jane"}], "total": 21}

    monkeypatch.setattr("app.api.routers.applications.list_applications", fake_list_applications)

    response = await client.get("/applications?limit=10&offset=20")
    assert response.status_code == 200
    assert response.json() == {"applications": [{"id": 1, "first_name": "Jane"}], "total": 21}


@pytest.mark.asyncio
async def test_get_applications_returns_502_when_unavailable(client, logged_in_dealer, monkeypatch):
    async def failing_list_applications(dealer_id, limit, offset):
        raise ApplicationsUnavailableError("connection refused")

    monkeypatch.setattr("app.api.routers.applications.list_applications", failing_list_applications)

    response = await client.get("/applications")
    assert response.status_code == 502
