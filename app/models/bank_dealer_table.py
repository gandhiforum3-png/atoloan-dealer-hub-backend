from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, func

from app.models.base import metadata

# A dealer's selected bank/credit-union network. Bank data itself lives in
# atoloan-backend, not here — we store id + a name snapshot so the network
# can be listed without a live call to atoloan-backend on every read.
bank_dealer_table = Table(
    "bank_dealer",
    metadata,
    Column(
        "dealer_id",
        String(20),
        ForeignKey("dealer_users.dealer_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("bank_id", Integer, primary_key=True),
    Column("bank_name", String(200), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
