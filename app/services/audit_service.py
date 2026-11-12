from sqlalchemy.ext.asyncio import AsyncConnection

from app.models.dealer_user_table import admin_audit_table


async def record_admin_action(
    conn: AsyncConnection,
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str | int,
    details: dict | None = None,
) -> None:
    """Append to admin_audit_log in the caller's transaction."""
    await conn.execute(
        admin_audit_table.insert().values(
            actor_dealer_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            details=details,
        )
    )
