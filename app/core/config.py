"""
Centralised application settings.

Secret loading priority (highest -> lowest):
  1. Environment variables  - set by the deployment platform
  2. .env file              - local development only; silently ignored
                              when absent (e.g. inside a container)
"""
from functools import lru_cache
from pathlib import Path

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

    # Auth
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24  # 24h
    auth_cookie_name: str = "dealerhub_session"
    # False for local http dev; must be True (requires HTTPS) in staging/prod
    auth_cookie_secure: bool = False

    # Base URL of the dealer-ui frontend, used to build the public
    # scan-landing link encoded in QR codes: {frontend_public_base_url}/d/{dealer_id}
    frontend_public_base_url: str = "http://localhost:5173"

    # Base URL of the atoloan-backend service, source of truth for bank/
    # credit-union data (GET {atoloan_backend_base_url}/credit-unions)
    atoloan_backend_base_url: str = "http://localhost:8001"

    model_config = SettingsConfigDict(
        # env_file is silently ignored when the file does not exist,
        # so this is safe inside containers where there is no .env file.
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
