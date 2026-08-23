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
