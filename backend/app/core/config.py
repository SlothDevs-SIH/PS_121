"""Application settings, read from environment variables prefixed with ``SMRITI_``.

Every setting is documented in docs/BACKEND_PLAN.md §7 (Configuration reference) and
listed with a safe development default in ``.env.example`` at the repository root.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SMRITI_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True
    git_sha: str = "unknown"

    # PostgreSQL 16 + PostGIS + pgvector + TimescaleDB (psycopg 3 driver)
    database_url: SecretStr = SecretStr("postgresql+psycopg://smriti:smriti@localhost:5432/smriti")
    required_pg_extensions: list[str] = Field(
        default_factory=lambda: ["postgis", "vector", "timescaledb", "pg_trgm"]
    )

    # Redis: Celery broker/result backend and (from B4) real-time streams
    redis_url: str = "redis://localhost:6379/0"

    # S3-compatible object storage (SeaweedFS in docker compose; any S3 API works)
    s3_endpoint_url: str = "http://localhost:8333"
    s3_access_key: SecretStr = SecretStr("smriti")
    s3_secret_key: SecretStr = SecretStr("smriti-secret")
    s3_region: str = "us-east-1"
    s3_bucket_raw: str = "smriti-raw"  # original uploaded files, keyed by sha256
    s3_bucket_pages: str = "smriti-pages"  # rendered page images for evidence display

    # Ingestion
    max_upload_mb: int = 50
    ocr_needs_review_below: float = 60.0  # mean OCR confidence (0..100) that triggers review

    # Auth: "dev" returns a fixed local user; "oidc" (Keycloak) is planned for phase B6
    auth_mode: Literal["dev", "oidc"] = "dev"

    # Per-dependency timeout used by /readyz checks
    readiness_timeout_s: float = 2.0

    @property
    def s3_buckets(self) -> list[str]:
        return [self.s3_bucket_raw, self.s3_bucket_pages]


@lru_cache
def get_settings() -> Settings:
    return Settings()
