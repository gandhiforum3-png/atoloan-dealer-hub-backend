"""
FastAPI application entry point.
Registers all routers and handles startup / shutdown lifecycle.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.db import create_tables, test_connection
from app.api.routers.admin import router as admin_router
from app.api.routers.admin_customers import router as admin_customers_router
from app.api.routers.applications import router as applications_router
from app.api.routers.auth import router as auth_router
from app.api.routers.banks import router as banks_router
from app.api.routers.dealer_admin import router as dealer_admin_router
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


_docs = settings.enable_docs
app = FastAPI(
    title="Dealer Hub Backend",
    lifespan=lifespan,
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def reject_cross_origin_writes(request: Request, call_next):
    """CSRF guard for the cookie session. Browsers always send Origin on
    cross-origin writes — including "simple" text/plain or form posts that skip
    the CORS preflight and that SameSite=Lax still allows from sibling
    subdomains. Non-browser clients send no Origin and are unaffected."""
    origin = request.headers.get("origin")
    if request.method in _UNSAFE_METHODS and origin is not None and origin not in settings.cors_origins_list:
        return JSONResponse({"detail": "cross-origin request blocked"}, status_code=403)
    return await call_next(request)


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(qr_codes_router)
app.include_router(public_router)
app.include_router(banks_router)
app.include_router(rate_sheets_router)
app.include_router(internal_router)
app.include_router(soft_pull_router)
app.include_router(applications_router)
app.include_router(dealer_admin_router)
app.include_router(admin_router)
app.include_router(admin_customers_router)
