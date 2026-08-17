# Atoloan Dealer Hub Backend

FastAPI backend for the Atoloan Dealer Hub. Scaffolded with the same stack as [atoloan-backend](../atoloan-backend): async SQLAlchemy + PostgreSQL, layered app structure, Docker Compose for local dev.

**Tech stack:** Python 3.12 · FastAPI · async SQLAlchemy 2.0 · asyncpg · PostgreSQL 16

## Project Structure

```
app/
├── main.py               FastAPI app, CORS, router registration, DB lifespan
├── db.py                 Async engine, connection, table creation
├── core/
│   ├── config.py          Pydantic settings (env vars / .env)
│   └── dependencies.py    Shared FastAPI dependencies (e.g. get_conn)
├── models/                SQLAlchemy table definitions (base.py holds shared metadata)
├── api/routers/           FastAPI routers (health.py is the only one so far)
├── services/              Business logic
└── integrations/          External API clients

tests/
├── conftest.py
├── unit/
└── integration/
```

## Local Development Setup

```bash
# 1. Create and activate a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy the env template and fill in local values
cp .env.example .env

# 4. Start Postgres (via Docker) or point PGHOST/PGPORT at an existing instance
docker compose up -d db

# 5. Run the server
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/hello` and `http://localhost:8000/db-check` to confirm the app and DB connection are working.

## Running Tests

```bash
pytest
```

## Running with Docker Compose

```bash
docker compose up --build
```

This starts both the Postgres database and the API container. The API reads config from `.env` (see `.env.example`), with `PGHOST`/`PGPORT` overridden to point at the `db` service.

## Adding a New Domain Module

1. Define tables in `app/models/<name>_table.py`, importing `metadata` from `app/models/base.py`.
2. Import the new table module in `app/db.py` so it registers before `create_tables()` runs.
3. Add business logic in `app/services/`.
4. Add a router in `app/api/routers/<name>.py` and register it in `app/main.py`.
