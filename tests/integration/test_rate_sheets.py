import pytest

from app.services.rate_sheet_service import RateSheetServiceUnavailableError

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.mark.asyncio
async def test_upload_without_login_returns_401(client):
    response = await client.post(
        "/rate-sheets/upload",
        files={"file": ("rates.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_rejects_non_pdf(client, logged_in_dealer):
    response = await client.post(
        "/rate-sheets/upload",
        files={"file": ("rates.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_success_returns_parsed_preview(client, logged_in_dealer, monkeypatch):
    async def fake_parse_rate_sheet(filename, content, content_type):
        return {
            "filename": filename,
            "parse_error": None,
            "validation": {"is_valid": True},
            "rate_sheet": {"credit_union_info": {"name": "KeyPoint Credit Union"}},
        }

    monkeypatch.setattr("app.api.routers.rate_sheets.parse_rate_sheet", fake_parse_rate_sheet)

    response = await client.post(
        "/rate-sheets/upload",
        files={"file": ("rates.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "rates.pdf"
    assert body["rate_sheet"]["credit_union_info"]["name"] == "KeyPoint Credit Union"


@pytest.mark.asyncio
async def test_upload_returns_502_when_service_unavailable(client, logged_in_dealer, monkeypatch):
    async def failing_parse_rate_sheet(filename, content, content_type):
        raise RateSheetServiceUnavailableError("connection refused")

    monkeypatch.setattr("app.api.routers.rate_sheets.parse_rate_sheet", failing_parse_rate_sheet)

    response = await client.post(
        "/rate-sheets/upload",
        files={"file": ("rates.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert response.status_code == 502


SAMPLE_RATE_SHEET = {
    "credit_union_info": {"name": "KeyPoint Credit Union"},
    "loan_programs": [{"program_name": "New Auto"}],
}


@pytest.mark.asyncio
async def test_confirm_without_login_returns_401(client):
    response = await client.post("/rate-sheets/confirm", json={"rate_sheet": SAMPLE_RATE_SHEET})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_confirm_requires_rate_sheet(client, logged_in_dealer):
    response = await client.post("/rate-sheets/confirm", json={})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_confirm_requires_credit_union_name(client, logged_in_dealer):
    response = await client.post(
        "/rate-sheets/confirm", json={"rate_sheet": {"credit_union_info": {}}}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_confirm_saves_and_adds_to_dealer_network(client, logged_in_dealer, monkeypatch):
    async def fake_save_rate_sheet(rate_sheet):
        return {"bank_id": 42, "rate_policy_items_count": 3, "loan_program_items_count": 1}

    monkeypatch.setattr("app.api.routers.rate_sheets.save_rate_sheet", fake_save_rate_sheet)

    response = await client.post("/rate-sheets/confirm", json={"rate_sheet": SAMPLE_RATE_SHEET})
    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "bank_id": 42,
        "bank_name": "KeyPoint Credit Union",
        "rate_policy_items_count": 3,
        "loan_program_items_count": 1,
    }

    network = await client.get("/banks/network")
    assert network.json() == [{"id": 42, "name": "KeyPoint Credit Union"}]


@pytest.mark.asyncio
async def test_confirm_does_not_wipe_existing_network(client, logged_in_dealer, monkeypatch):
    from app.models.bank import BankOut

    async def fake_list_banks():
        return [BankOut(id=1, name="First City Credit Union"), BankOut(id=42, name="KeyPoint Credit Union")]

    monkeypatch.setattr("app.services.bank_network_service.list_banks", fake_list_banks)
    await client.post("/banks/network", json={"bank_ids": [1]})

    async def fake_save_rate_sheet(rate_sheet):
        return {"bank_id": 42, "rate_policy_items_count": 3, "loan_program_items_count": 1}

    monkeypatch.setattr("app.api.routers.rate_sheets.save_rate_sheet", fake_save_rate_sheet)
    await client.post("/rate-sheets/confirm", json={"rate_sheet": SAMPLE_RATE_SHEET})

    network = await client.get("/banks/network")
    assert {bank["id"] for bank in network.json()} == {1, 42}


@pytest.mark.asyncio
async def test_confirm_returns_502_when_service_unavailable(client, logged_in_dealer, monkeypatch):
    async def failing_save_rate_sheet(rate_sheet):
        raise RateSheetServiceUnavailableError("connection refused")

    monkeypatch.setattr("app.api.routers.rate_sheets.save_rate_sheet", failing_save_rate_sheet)

    response = await client.post("/rate-sheets/confirm", json={"rate_sheet": SAMPLE_RATE_SHEET})
    assert response.status_code == 502
