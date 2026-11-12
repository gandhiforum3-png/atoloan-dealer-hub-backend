"""
/admin/customers: admin-only proxy to atoloan-backend's /customers, with every
change audit-logged before it is attempted. Accounts are addressed by numeric
id — emails never go in URLs. atoloan-backend is faked at the backend_request
seam; our own tables (dealer_users, admin_audit_log) are real.
"""
import pytest
from sqlalchemy import select, update

from app.db import get_engine
from app.models.dealer_user_table import admin_audit_table, dealer_user_table
from app.services.backend_client import BackendNotFoundError, BackendUnavailableError

JANE = "jane@example.com"
PROFILE = {"id": 7, "email": JANE, "first_name": "Jane", "last_name": "Doe", "phone_number": None,
           "address": None, "city": None, "state": None, "zipcode": None}


class FakeBackend:
    def __init__(self):
        self.calls = []
        self.fail = None
        self.status = "active"

    async def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("params"), kwargs.get("json")))
        if self.fail:
            raise self.fail
        if method == "GET" and path == "/customers":
            return {"customers": [{**PROFILE, "status": self.status}], "total": 1}
        if method == "GET":
            return {**PROFILE, "status": self.status, "applications": []}
        if method == "PATCH":
            return {"before": PROFILE, "after": {**PROFILE, **kwargs["json"]}}
        if path.endswith("/status"):
            previous, self.status = self.status, kwargs["json"]["status"]
            return {"id": 7, "email": JANE, "status": self.status, "previous_status": previous}
        if path.endswith("/close"):
            return {"id": 7, "email": JANE, "status": "closed"}
        raise AssertionError(path)


@pytest.fixture
def backend(monkeypatch):
    fake = FakeBackend()
    monkeypatch.setattr("app.api.routers.admin_customers.backend_request", fake)
    return fake


@pytest.fixture
async def admin(client, logged_in_dealer):
    async with get_engine().begin() as conn:
        await conn.execute(
            update(dealer_user_table).where(dealer_user_table.c.dealer_id == logged_in_dealer["dealer_id"]).values(is_admin=True)
        )
    yield logged_in_dealer
    async with get_engine().begin() as conn:
        await conn.execute(admin_audit_table.delete().where(admin_audit_table.c.actor_dealer_id == logged_in_dealer["dealer_id"]))


async def _audit(dealer_id):
    async with get_engine().connect() as conn:
        rows = await conn.execute(
            select(admin_audit_table.c.action, admin_audit_table.c.target_type, admin_audit_table.c.target_id, admin_audit_table.c.details)
            .where(admin_audit_table.c.actor_dealer_id == dealer_id)
            .order_by(admin_audit_table.c.id)
        )
        return [dict(r._mapping) for r in rows]


WRITES = [
    ("patch", "/admin/customers/7", {"phone_number": "4155550100"}),
    ("post", "/admin/customers/7/status", {"status": "disabled"}),
    ("post", "/admin/customers/7/close", None),
]


@pytest.mark.asyncio
async def test_non_admin_is_refused_everywhere(client, logged_in_dealer, backend):
    for method, path in [("get", "/admin/customers"), ("get", "/admin/customers/7")]:
        assert (await client.request(method.upper(), path)).status_code == 403
    for method, path, body in WRITES:
        assert (await client.request(method.upper(), path, json=body)).status_code == 403
    assert backend.calls == []


@pytest.mark.asyncio
async def test_search_params_passed_through(client, admin, backend):
    resp = await client.get("/admin/customers", params={"q": "jane", "limit": 10})
    assert resp.status_code == 200 and resp.json()["total"] == 1
    assert backend.calls == [("GET", "/customers", {"q": "jane", "limit": 10, "offset": 0}, None)]


@pytest.mark.asyncio
async def test_customer_urls_never_carry_emails(client, admin, backend):
    await client.get("/admin/customers/7")
    await client.post("/admin/customers/7/close")
    assert [call[1] for call in backend.calls] == ["/customers/7", "/customers/7/close"]
    assert (await client.get(f"/admin/customers/{JANE}")).status_code == 422


@pytest.mark.asyncio
async def test_edit_is_audited_with_before_and_after(client, admin, backend):
    resp = await client.patch("/admin/customers/7", json={"phone_number": "4155550100", "city": None})
    assert resp.status_code == 200 and resp.json()["phone_number"] == "4155550100"
    assert backend.calls[0][3] == {"phone_number": "4155550100"}  # unset/None fields aren't forwarded
    assert await _audit(admin["dealer_id"]) == [{
        "action": "update_customer", "target_type": "customer", "target_id": "7",
        "details": {
            "outcome": "done",
            "email": JANE,
            "requested": {"phone_number": "4155550100"},
            "changed": {"phone_number": {"from": None, "to": "4155550100"}},
        },
    }]


@pytest.mark.asyncio
async def test_empty_edit_is_refused_before_audit(client, admin, backend):
    assert (await client.patch("/admin/customers/7", json={"city": None})).status_code == 422
    assert backend.calls == [] and await _audit(admin["dealer_id"]) == []


@pytest.mark.asyncio
async def test_edit_that_changes_nothing_is_recorded_as_unchanged(client, admin, backend):
    await client.patch("/admin/customers/7", json={"first_name": "Jane"})
    (row,) = await _audit(admin["dealer_id"])
    assert row["details"]["outcome"] == "unchanged" and row["details"]["changed"] == {}


@pytest.mark.asyncio
async def test_invalid_edit_is_422_without_calling_backend(client, admin, backend):
    resp = await client.patch("/admin/customers/7", json={"phone_number": "555", "state": "California"})
    assert resp.status_code == 422
    assert backend.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("current,status,action,outcome", [
    ("active", "disabled", "disable_customer", "done"),
    ("disabled", "active", "enable_customer", "done"),
    ("disabled", "disabled", "disable_customer", "unchanged"),
])
async def test_status_change_is_audited_with_from_and_to(client, admin, backend, current, status, action, outcome):
    backend.status = current
    resp = await client.post("/admin/customers/7/status", json={"status": status})
    assert resp.status_code == 200
    (row,) = await _audit(admin["dealer_id"])
    assert row["action"] == action
    assert row["details"] == {"outcome": outcome, "email": JANE, "requested": {"status": status}, "from": current, "to": status}


@pytest.mark.asyncio
async def test_close_is_audited(client, admin, backend):
    assert (await client.post("/admin/customers/7/close")).json()["status"] == "closed"
    audit = await _audit(admin["dealer_id"])
    assert [(row["action"], row["target_id"], row["details"]["email"]) for row in audit] == [("close_customer", "7", JANE)]


@pytest.mark.asyncio
async def test_failed_or_unknown_outcomes_are_still_audited(client, admin, backend):
    backend.fail = BackendNotFoundError("/customers/8")
    assert (await client.post("/admin/customers/8/close")).status_code == 404
    backend.fail = BackendUnavailableError("timeout")  # may or may not have been applied
    assert (await client.post("/admin/customers/9/status", json={"status": "disabled"})).status_code == 502
    backend.fail = BackendUnavailableError("down")
    assert (await client.get("/admin/customers")).status_code == 502  # reads aren't audited

    audit = await _audit(admin["dealer_id"])
    assert [(row["action"], row["target_id"], row["details"]["outcome"]) for row in audit] == [
        ("close_customer", "8", "failed"),
        ("disable_customer", "9", "unknown"),
    ]


@pytest.mark.asyncio
async def test_no_change_without_an_audit_row(client, admin, backend, monkeypatch):
    async def audit_down(*args, **kwargs):
        raise RuntimeError("audit database unavailable")

    monkeypatch.setattr("app.api.routers.admin_customers._start_audit", audit_down)
    with pytest.raises(RuntimeError):
        await client.post("/admin/customers/7/close")
    assert backend.calls == []
