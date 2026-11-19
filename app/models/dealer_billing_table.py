from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, func

from app.models.base import metadata

# One billing profile per dealer. `customer_id` is a fake `cus_...` id today
# and a real Stripe customer id later — named generically so it survives a
# future payment-processor swap.
dealer_billing_table = Table(
    "dealer_billing",
    metadata,
    Column(
        "dealer_id",
        String(20),
        ForeignKey("dealer_users.dealer_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("customer_id", String(64), unique=True, nullable=True),
    Column(
        "default_payment_method_id",
        String(64),
        ForeignKey("payment_methods.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("credit_balance", Integer, nullable=False, default=0, server_default="0"),
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
