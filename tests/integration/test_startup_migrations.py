"""Startup migrations must be no-ops once applied: an ALTER that takes an
ACCESS EXCLUSIVE lock on every boot would queue behind (and then block) any
open read of the audit log."""
import pytest
from sqlalchemy import select, text

from app.db import get_engine
from app.models.dealer_user_table import DEALER_USER_COLUMN_MIGRATIONS, admin_audit_table


@pytest.mark.asyncio
async def test_rerunning_migrations_does_not_lock_the_audit_log():
    engine = get_engine()
    async with engine.connect() as reader:
        await reader.begin()
        await reader.execute(select(admin_audit_table.c.id).limit(1))  # holds ACCESS SHARE, like a live request

        async with engine.connect() as migrator:
            await migrator.begin()
            await migrator.execute(text("SET LOCAL lock_timeout = '500ms'"))
            for stmt in DEALER_USER_COLUMN_MIGRATIONS:
                await migrator.execute(text(stmt))  # raises LockNotAvailable if it needs an exclusive lock
            await migrator.rollback()
        await reader.rollback()
