from sqlalchemy import Column, DateTime, Sequence, String, Table, func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models.base import metadata

# Backs the DLR-###### dealer_id short codes assigned at onboarding.
dealer_id_seq = Sequence("dealer_id_seq", start=1, metadata=metadata)

dealer_user_table = Table(
    "dealer_users",
    metadata,
    Column("dealer_id", String(20), primary_key=True),
    Column("email", String(320), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("name", String(200), nullable=False),
    Column("dealership_name", String(200), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column("last_login_at", DateTime(timezone=True), nullable=True),
)


async def next_dealer_id(conn: AsyncConnection) -> str:
    """Mint the next DLR-###### short code for a newly onboarded dealer."""
    seq_value = await conn.scalar(select(dealer_id_seq.next_value()))
    return f"DLR-{seq_value:06d}"
