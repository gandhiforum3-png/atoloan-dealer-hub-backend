"""
POST /soft-pull — proxies to atoloan-backend's /findback, injecting the
authenticated dealer's own dealer_id so bank matching is scoped correctly.
"""
import pytest

from app.services.soft_pull_service import SoftPullUnavailableError


@pytest.mark.asyncio
async def test_submit_without_login_returns_401(client):
    response = await client.post("/soft-pull", json={"contactInfo": {}})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_submit_injects_authenticated_dealer_id(client, logged_in_dealer, monkeypatch):
    captured = {}

    async def fake_run_soft_pull(payload):
        captured.update(payload)
        return 200, {"prequal": {"score": 700}}

    monkeypatch.setattr("app.api.routers.soft_pull.run_soft_pull", fake_run_soft_pull)

    response = await client.post(
        "/soft-pull",
        json={"contactInfo": {"firstName": "John"}, "dealer_id": "someone-elses-id", "consent": True},
    )

    assert response.status_code == 200
    assert response.json() == {"prequal": {"score": 700}}
    assert captured["dealer_id"] == logged_in_dealer["dealer_id"]


@pytest.mark.asyncio
async def test_submit_forwards_validation_error(client, logged_in_dealer, monkeypatch):
    async def fake_run_soft_pull(payload):
        return 400, {"detail": "missing required fields: email"}

    monkeypatch.setattr("app.api.routers.soft_pull.run_soft_pull", fake_run_soft_pull)

    response = await client.post("/soft-pull", json={"consent": True})
    assert response.status_code == 400
    assert response.json()["detail"] == "missing required fields: email"


@pytest.mark.asyncio
async def test_submit_returns_502_when_service_unavailable(client, logged_in_dealer, monkeypatch):
    async def failing_run_soft_pull(payload):
        raise SoftPullUnavailableError("connection refused")

    monkeypatch.setattr("app.api.routers.soft_pull.run_soft_pull", failing_run_soft_pull)

    response = await client.post("/soft-pull", json={"consent": True})
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_submit_without_consent_never_reaches_backend(client, logged_in_dealer, monkeypatch):
    called = []

    async def fake_run_soft_pull(payload):
        called.append(payload)
        return 200, {}

    monkeypatch.setattr("app.api.routers.soft_pull.run_soft_pull", fake_run_soft_pull)

    response = await client.post("/soft-pull", json={"contactInfo": {"firstName": "John"}})
    assert response.status_code == 400
    assert called == []


@pytest.mark.asyncio
async def test_cross_origin_write_is_blocked(client, logged_in_dealer):
    """CSRF: a page on another origin (even a sibling subdomain) can't drive the session."""
    response = await client.post(
        "/soft-pull",
        content='{"consent": true}',
        headers={"Origin": "https://evil.atoloans.com", "Content-Type": "text/plain"},
    )
    assert response.status_code == 403
