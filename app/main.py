"""
FastAPI application entry point.
Registers all routers and handles startup / shutdown lifecycle.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db import create_tables, test_connection
from app.api.routers.applications import router as applications_router
from app.api.routers.auth import router as auth_router
from app.api.routers.banks import router as banks_router
from app.api.routers.health import router as health_router
from app.api.routers.internal import router as internal_router
from app.api.routers.public import router as public_router
from app.api.routers.qr_codes import router as qr_codes_router
from app.api.routers.rate_sheets import router as rate_sheets_router
from app.api.routers.soft_pull import router as soft_pull_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await create_tables()
        await test_connection()
        logger.info("Database connection successful")
    except Exception:
        logger.exception("Database connection failed on startup")
    yield


app = FastAPI(title="Dealer Hub Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(qr_codes_router)
app.include_router(public_router)
app.include_router(banks_router)
app.include_router(rate_sheets_router)
app.include_router(internal_router)
app.include_router(soft_pull_router)
app.include_router(applications_router)
