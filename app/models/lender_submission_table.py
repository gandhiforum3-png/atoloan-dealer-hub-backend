from sqlalchemy import Column, DateTime, Integer, String, Table, func

from app.models.base import metadata

# Which dealer submitted a lender's rate sheet (bank data itself lives in
# atoloan-backend). Shown to admins reviewing pending lenders.
lender_submission_table = Table(
    "lender_submissions",
    metadata,
    Column("bank_id", Integer, primary_key=True),
    Column("dealer_id", String(20), nullable=False),
    Column("submitted_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
