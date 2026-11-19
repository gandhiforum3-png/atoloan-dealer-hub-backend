from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, func

from app.models.base import metadata

# A single charge — backs both one-time credit-pack purchases and
# subscription "invoices". This is the table the billing history/invoice
# table on the dashboard reads from.
payment_table = Table(
    "payments",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "dealer_id",
        String(20),
        ForeignKey("dealer_users.dealer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("type", String(20), nullable=False),
    Column("description", String(255), nullable=False),
    Column("amount_cents", Integer, nullable=False),
    Column("currency", String(3), nullable=False, server_default="usd"),
    Column("status", String(20), nullable=False),
    Column(
        "payment_method_id",
        String(64),
        ForeignKey("payment_methods.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column(
        "subscription_id",
        String(64),
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("credit_pack_id", String(50), nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
