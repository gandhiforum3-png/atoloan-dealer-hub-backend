from sqlalchemy import Boolean, Column, DateTime, Integer, Sequence, String, Table, false, func, select, true
from sqlalchemy.dialects.postgresql import JSONB
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
    Column("is_admin", Boolean, nullable=False, server_default=false()),
    Column("is_active", Boolean, nullable=False, server_default=true()),
    # Set when an admin creates the account or resets its password: the
    # dealer can do nothing but change it before using the portal.
    Column("must_change_password", Boolean, nullable=False, server_default=false()),
)

# Append-only record of admin actions (dealer accounts, lender approvals).
admin_audit_table = Table(
    "admin_audit_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("actor_dealer_id", String(20), nullable=False),
    Column("action", String(50), nullable=False),
    Column("target_type", String(20), nullable=False),  # "dealer" | "lender" | "customer"
    Column("target_id", String(320), nullable=False),  # customer targets are emails
    Column("details", JSONB),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# create_all() doesn't add columns to existing tables — these do, idempotently.
DEALER_USER_COLUMN_MIGRATIONS = [
    "ALTER TABLE dealer_users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE dealer_users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true",
    "ALTER TABLE dealer_users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT false",
    # Widen target_id once. Guarded: ALTER COLUMN TYPE takes an ACCESS EXCLUSIVE
    # lock even when nothing changes, so running it on every boot would block reads.
    """
    DO $$
    BEGIN
        IF (SELECT character_maximum_length FROM information_schema.columns
            WHERE table_name = 'admin_audit_log' AND column_name = 'target_id') < 320 THEN
            ALTER TABLE admin_audit_log ALTER COLUMN target_id TYPE VARCHAR(320);
        END IF;
    END $$
    """,
]


async def next_dealer_id(conn: AsyncConnection) -> str:
    """Mint the next DLR-###### short code for a newly onboarded dealer."""
    seq_value = await conn.scalar(select(dealer_id_seq.next_value()))
    return f"DLR-{seq_value:06d}"
