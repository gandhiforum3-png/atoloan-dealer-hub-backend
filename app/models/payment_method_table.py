from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, func

from app.models.base import metadata

# A dealer's saved card — display metadata only (brand/last4/expiry). No PAN
# or CVC is ever stored here, stub or real.
payment_method_table = Table(
    "payment_methods",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "dealer_id",
        String(20),
        ForeignKey("dealer_users.dealer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("brand", String(20), nullable=False),
    Column("last4", String(4), nullable=False),
    Column("exp_month", Integer, nullable=False),
    Column("exp_year", Integer, nullable=False),
    Column("cardholder_name", String(200), nullable=False),
    Column("billing_zip", String(10), nullable=True),
    Column("is_default", Boolean, nullable=False, default=False, server_default="false"),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
