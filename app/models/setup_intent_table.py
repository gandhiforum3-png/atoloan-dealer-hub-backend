from sqlalchemy import Column, DateTime, ForeignKey, String, Table, func

from app.models.base import metadata

# Tracks an in-progress "add a card" attempt. Persisted in Postgres (not an
# in-process dict) so it survives a dev-server --reload restart, and so it
# maps 1:1 onto Stripe's real SetupIntent object when that swap happens.
setup_intent_table = Table(
    "setup_intents",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "dealer_id",
        String(20),
        ForeignKey("dealer_users.dealer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("status", String(30), nullable=False, server_default="requires_payment_method"),
    Column(
        "payment_method_id",
        String(64),
        ForeignKey("payment_methods.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
