"""
/admin/lenders review queue and /admin/applications. atoloan-backend is faked
at the backend_request seam; our own tables (submissions, audit, networks) are real.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update

from app.db import get_engine
from app.models.bank_dealer_table import bank_dealer_table
from app.models.dealer_user_table import admin_audit_table, dealer_user_table
from app.models.lender_submission_table import lender_submission_table


class FakeBackend:
    def __init__(self):
        self.banks = {
            901: {"id": 901, "name": "Zeta CU", "approval_status": "approved"},
            902: {"id": 902, "name": "Alpha CU", "approval_status": "pending"},
        }
        self.calls = []

    async def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json")))
        self.params = kwargs.get("params")
        if path == "/credit-unions":
            return {"credit_unions": list(self.banks.values())}
        if path.endswith("/ratesheet"):
            return {"credit_union_info": {"name": "Alpha CU"}, "loan_programs": []}
        if path.endswith("/approval"):
            bank_id = int(path.split("/")[2])
            self.banks[bank_id]["approval_status"] = kwargs["json"]["status"]
            return {}
        if method == "DELETE":
            self.banks.pop(int(path.split("/")[2]))
            return {}
        if path == "/loan-applications":
            return {"applications": [{"id": 1, "dealer_id": "DLR-NOPE"}, {"id": 2, "dealer_id": None}], "total": 2}
        raise AssertionError(path)


@pytest.fixture
async def admin(client, logged_in_dealer, monkeypatch):
    async with get_engine().begin() as conn:
        await conn.execute(
            update(dealer_user_table).where(dealer_user_table.c.dealer_id == logged_in_dealer["dealer_id"]).values(is_admin=True)
        )
        await conn.execute(
            lender_submission_table.insert().values(
                bank_id=902, dealer_id=logged_in_dealer["dealer_id"], submitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
            )
        )
        await conn.execute(bank_dealer_table.insert().values(dealer_id=logged_in_dealer["dealer_id"], bank_id=902, bank_name="Alpha CU"))
    fake = FakeBackend()
    for module in ("app.api.routers.admin", "app.services.applications_service"):
        monkeypatch.setattr(f"{module}.backend_request", fake)
    yield {**logged_in_dealer, "backend": fake}
    async with get_engine().begin() as conn:
        await conn.execute(lender_submission_table.delete().where(lender_submission_table.c.bank_id.in_([901, 902])))
        await conn.execute(admin_audit_table.delete().where(admin_audit_table.c.actor_dealer_id == logged_in_dealer["dealer_id"]))


@pytest.mark.asyncio
async def test_lender_routes_require_admin(client, logged_in_dealer):
    for method, path in [("get", "/admin/lenders"), ("get", "/admin/lenders/1"), ("delete", "/admin/lenders/1"), ("get", "/admin/applications")]:
        assert (await getattr(client, method)(path)).status_code == 403
    assert (await client.post("/admin/lenders/1/approval", json={"status": "approved"})).status_code == 403


@pytest.mark.asyncio
async def test_queue_lists_pending_first_with_submitter(client, admin):
    lenders = (await client.get("/admin/lenders")).json()
    assert [l["name"] for l in lenders] == ["Alpha CU", "Zeta CU"]
    assert lenders[0]["submitted_by"]["dealer_id"] == admin["dealer_id"]
    assert lenders[1]["submitted_by"] is None


@pytest.mark.asyncio
async def test_detail_includes_rate_sheet(client, admin):
    body = (await client.get("/admin/lenders/902")).json()
    assert body["rate_sheet"]["credit_union_info"]["name"] == "Alpha CU"
    assert (await client.get("/admin/lenders/999")).status_code == 404


@pytest.mark.asyncio
async def test_approve_is_forwarded_and_audited(client, admin):
    response = await client.post("/admin/lenders/902/approval", json={"status": "approved"})
    assert response.json()["approval_status"] == "approved"
    assert ("POST", "/credit-unions/902/approval", {"status": "approved"}) in admin["backend"].calls
    async with get_engine().connect() as conn:
        actions = (await conn.execute(select(admin_audit_table.c.action).where(admin_audit_table.c.target_id == "902"))).scalars().all()
    assert actions == ["approve_lender"]


@pytest.mark.asyncio
async def test_invalid_status_rejected(client, admin):
    assert (await client.post("/admin/lenders/902/approval", json={"status": "deleted"})).status_code == 422


@pytest.mark.asyncio
async def test_approved_lender_cannot_be_rejected_in_one_step(client, admin):
    assert (await client.delete("/admin/lenders/901")).status_code == 409
    assert not [c for c in admin["backend"].calls if c[0] == "DELETE"]


@pytest.mark.asyncio
async def test_reject_pending_removes_it_from_networks(client, admin):
    assert (await client.delete("/admin/lenders/902")).status_code == 200
    async with get_engine().connect() as conn:
        left = (await conn.execute(select(bank_dealer_table.c.bank_id).where(bank_dealer_table.c.bank_id == 902))).all()
    assert left == []


@pytest.mark.asyncio
async def test_all_applications_labels_dealer_or_direct(client, admin):
    body = (await client.get("/admin/applications")).json()
    assert body["total"] == 2
    assert [a["dealership_name"] for a in body["applications"]] == [None, None]


@pytest.mark.asyncio
async def test_customer_search_is_passed_to_backend(client, admin):
    await client.get("/admin/applications", params={"q": "jane@example.com", "limit": 10})
    assert admin["backend"].params == {"limit": 10, "offset": 0, "q": "jane@example.com"}


@pytest.mark.asyncio
async def test_customer_search_is_admin_only(client, logged_in_dealer):
    assert (await client.get("/admin/applications", params={"q": "jane"})).status_code == 403
