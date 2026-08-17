"""
Shared SQLAlchemy metadata that all table definitions register against.

Import new table modules in app/db.py so they register with `metadata`
before `create_tables()` runs.
"""
from sqlalchemy import MetaData

metadata = MetaData()
