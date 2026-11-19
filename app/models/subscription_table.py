from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, func

from app.models.base import metadata

# A dealer's subscription. Only one active/past_due row per dealer is
# enforced in app/services/billing_service.py (cancel-then-create), not at
# the DB level — same approach bank_network_service.save_dealer_banks takes
# for its own invariant.
subscription_table = Table(
    "subscriptions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "dealer_id",
        String(20),
        ForeignKey("dealer_users.dealer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("plan_id", String(50), nullable=False),
    Column("billing_cycle", String(10), nullable=False),
    Column("status", String(20), nullable=False),
    Column(
        "payment_method_id",
        String(64),
        ForeignKey("payment_methods.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("current_period_start", DateTime(timezone=True), nullable=False),
    Column("current_period_end", DateTime(timezone=True), nullable=False),
    Column("cancel_at_period_end", Boolean, nullable=False, default=False, server_default="false"),
    Column("canceled_at", DateTime(timezone=True), nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
)
