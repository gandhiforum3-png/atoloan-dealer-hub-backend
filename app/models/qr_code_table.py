from sqlalchemy import Column, DateTime, ForeignKey, String, Table, func

from app.models.base import metadata

# One active QR record per dealer. Regenerating rotates `token`, which
# invalidates previously printed codes without changing the dealer_id
# encoded in the URL.
qr_code_table = Table(
    "qr_codes",
    metadata,
    Column(
        "dealer_id",
        String(20),
        ForeignKey("dealer_users.dealer_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("label", String(200), nullable=False, server_default="Showroom QR"),
    Column("token", String(32), nullable=False, unique=True),
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
