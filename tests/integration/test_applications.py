import pytest

from app.services.applications_service import ApplicationsUnavailableError


@pytest.mark.asyncio
async def test_get_applications_without_login_returns_401(client):
    response = await client.get("/applications")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_applications_success(client, logged_in_dealer, monkeypatch):
    async def fake_list_applications(dealer_id):
        assert dealer_id == logged_in_dealer["dealer_id"]
        return [{"id": 1, "first_name": "Jane"}]

    monkeypatch.setattr("app.api.routers.applications.list_applications", fake_list_applications)

    response = await client.get("/applications")
    assert response.status_code == 200
    assert response.json() == [{"id": 1, "first_name": "Jane"}]


@pytest.mark.asyncio
async def test_get_applications_returns_502_when_unavailable(client, logged_in_dealer, monkeypatch):
    async def failing_list_applications(dealer_id):
        raise ApplicationsUnavailableError("connection refused")

    monkeypatch.setattr("app.api.routers.applications.list_applications", failing_list_applications)

    response = await client.get("/applications")
    assert response.status_code == 502
