"""
Centralised application settings.

Secret loading priority (highest -> lowest):
  1. Environment variables  - set by the deployment platform
  2. .env file              - local development only; silently ignored
                              when absent (e.g. inside a container)
"""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    # Database
    database_url: str = ""
    pghost: str = "localhost"
    pgport: int = 5432
    pguser: str = ""
    pgpassword: str = ""
    pgdatabase: str = "dealerhub"

    # CORS allowed origins (comma-separated)
    cors_origins: str = "http://localhost:5173,http://localhost:5174"

    # Auth — JWT_SECRET_KEY has no default: the app refuses to start without
    # a real one (generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`)
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 12  # 12h
    auth_cookie_name: str = "dealerhub_session"
    # Secure by default; set AUTH_COOKIE_SECURE=false only for local http dev
    auth_cookie_secure: bool = True

    # Shared secret sent as X-Service-Token on calls to atoloan-backend and
    # required on this service's /internal routes. Must match atoloan-backend's.
    service_token: str = ""

    # Swagger UI / OpenAPI schema — on for local dev only
    enable_docs: bool = False

    # Base URL of the dealer-ui frontend, used to build the public
    # scan-landing link encoded in QR codes: {frontend_public_base_url}/d/{dealer_id}
    frontend_public_base_url: str = "http://localhost:5173"

    # Base URL of the atoloan-backend service, source of truth for bank/
    # credit-union data (GET {atoloan_backend_base_url}/credit-unions)
    atoloan_backend_base_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(
        # env_file is silently ignored when the file does not exist,
        # so this is safe inside containers where there is no .env file.
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def _strong_jwt_secret(cls, value: str) -> str:
        if len(value) < 32 or value == "dev-secret-change-me":
            raise ValueError("JWT_SECRET_KEY must be set to a random value of at least 32 characters")
        return value

    @property
    def service_headers(self) -> dict[str, str]:
        return {"X-Service-Token": self.service_token}

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
