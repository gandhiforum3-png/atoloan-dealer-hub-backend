import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize("secret", ["", "dev-secret-change-me", "short"])
def test_weak_jwt_secret_refuses_to_start(secret):
    with pytest.raises(ValidationError):
        Settings(jwt_secret_key=secret)


def test_strong_jwt_secret_accepted():
    assert Settings(jwt_secret_key="x" * 32).jwt_secret_key == "x" * 32


def test_daily_quota_is_per_key_and_rolls_off(monkeypatch):
    from fastapi import HTTPException

    from app.core import security

    now = [1000.0]
    monkeypatch.setattr(security.time, "monotonic", lambda: now[0])
    quota = security.DailyQuota(2, "limit")
    quota.take("a")
    quota.take("a")
    with pytest.raises(HTTPException):
        quota.take("a")
    quota.take("b")  # other dealers unaffected
    now[0] += quota.WINDOW_SECONDS
    quota.take("a")  # old uses rolled off
