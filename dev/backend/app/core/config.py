import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    AliasChoices,
    BeforeValidator,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MONOREPO_ROOT = (
    BACKEND_ROOT.parent.parent
    if BACKEND_ROOT.name == "backend" and BACKEND_ROOT.parent.name == "dev"
    else BACKEND_ROOT
)
ROOT_ENV_FILE = MONOREPO_ROOT / ".env"


def _parse_cors_origins(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(origin).strip().rstrip("/") for origin in value if str(origin).strip()]
    if not isinstance(value, str):
        raise TypeError("CORS_ORIGINS must be a JSON array or comma-separated string")

    raw_value = value.strip()
    if not raw_value:
        return []
    if raw_value.startswith("["):
        parsed = json.loads(raw_value)
        if not isinstance(parsed, list):
            raise ValueError("CORS_ORIGINS JSON must contain an array")
        return [str(origin).strip().rstrip("/") for origin in parsed if str(origin).strip()]
    return [origin.strip().rstrip("/") for origin in raw_value.split(",") if origin.strip()]


CorsOrigins = Annotated[list[str], NoDecode, BeforeValidator(_parse_cors_origins)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Travel Journal API"
    app_env: str = "local"
    log_level: str = "INFO"
    api_prefix: Literal["/api/v1"] = "/api/v1"
    cors_origins: CorsOrigins = Field(
        default_factory=lambda: ["http://localhost:3000"],
        validation_alias=AliasChoices("BACKEND_CORS_ORIGINS", "CORS_ORIGINS"),
    )

    database_url: str = (
        "postgresql+asyncpg://travel_journal:travel_journal@localhost:5432/travel_journal"
    )
    redis_url: str = "redis://localhost:6379/0"
    redis_connect_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    redis_operation_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    generation_queue_key: str = "travel-journal:generation:queued"
    generation_max_attempts: int = Field(default=3, ge=1, le=10)
    generation_retry_base_seconds: float = Field(default=5.0, gt=0, le=300)
    worker_name: str = "generation-worker"
    worker_poll_seconds: int = Field(default=2, ge=1, le=30)
    worker_heartbeat_key: str = "travel-journal:generation:worker:heartbeat"
    worker_heartbeat_seconds: int = Field(default=5, ge=1, le=60)
    worker_heartbeat_ttl_seconds: int = Field(default=15, ge=2, le=300)
    worker_reconcile_seconds: int = Field(default=5, ge=1, le=60)
    worker_lease_seconds: int = Field(default=60, ge=10, le=3600)

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6-terra"
    openai_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    provider_context_max_chars: int = Field(default=30_000, ge=1_000, le=100_000)

    cala_api_key: SecretStr | None = None
    cala_base_url: str = "https://api.cala.ai"
    cala_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=300,
        validation_alias=AliasChoices("CALA_TIMEOUT_SECONDS", "CALA_TIMEOUT"),
    )

    fal_key: SecretStr | None = None
    fal_image_model: str = "fal-ai/flux/schnell"
    fal_start_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    fal_result_timeout_seconds: float = Field(default=180.0, gt=0, le=1800)

    media_storage_path: Path = MONOREPO_ROOT / ".data" / "generated-media"
    media_url_path: str = "/media"
    media_download_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    media_max_bytes: int = Field(default=15_000_000, ge=1_000_000, le=100_000_000)

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError("LOG_LEVEL must be CRITICAL, ERROR, WARNING, INFO, or DEBUG")
        return normalized

    @field_validator("cala_base_url")
    @classmethod
    def normalize_cala_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("CALA_BASE_URL must be an HTTP(S) URL")
        return normalized

    @field_validator("openai_model", "fal_image_model")
    @classmethod
    def normalize_model_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("provider model IDs cannot be blank")
        return normalized

    @field_validator("media_url_path")
    @classmethod
    def normalize_media_url_path(cls, value: str) -> str:
        normalized = "/" + value.strip().strip("/")
        if normalized == "/":
            raise ValueError("MEDIA_URL_PATH cannot be the application root")
        return normalized

    @field_validator("generation_queue_key", "worker_name", "worker_heartbeat_key")
    @classmethod
    def reject_blank_worker_settings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("worker and queue identifiers cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_worker_heartbeat(self) -> "Settings":
        if self.worker_heartbeat_ttl_seconds <= self.worker_heartbeat_seconds:
            raise ValueError(
                "WORKER_HEARTBEAT_TTL_SECONDS must be greater than WORKER_HEARTBEAT_SECONDS"
            )
        if self.worker_lease_seconds <= self.worker_heartbeat_seconds * 2:
            raise ValueError(
                "WORKER_LEASE_SECONDS must be greater than twice WORKER_HEARTBEAT_SECONDS"
            )
        return self

    @staticmethod
    def _secret_is_configured(secret: SecretStr | None) -> bool:
        return bool(secret and secret.get_secret_value().strip())

    @property
    def openai_configured(self) -> bool:
        return self._secret_is_configured(self.openai_api_key)

    @property
    def cala_configured(self) -> bool:
        return self._secret_is_configured(self.cala_api_key)

    @property
    def fal_configured(self) -> bool:
        return self._secret_is_configured(self.fal_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
