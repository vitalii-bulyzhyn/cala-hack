from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import BACKEND_ROOT, MONOREPO_ROOT, ROOT_ENV_FILE, Settings


def test_root_env_path_is_derived_from_monorepo_layout() -> None:
    assert BACKEND_ROOT.name == "backend"
    assert MONOREPO_ROOT == BACKEND_ROOT.parent.parent
    assert ROOT_ENV_FILE == MONOREPO_ROOT / ".env"


def test_settings_parse_comma_separated_cors_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "BACKEND_CORS_ORIGINS",
        "http://localhost:3000, https://example.com/",
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://localhost:3000", "https://example.com"]


def test_settings_parse_json_cors_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "BACKEND_CORS_ORIGINS",
        '["http://localhost:3000", "https://example.com"]',
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://localhost:3000", "https://example.com"]


def test_log_level_is_normalized_and_api_prefix_is_fixed() -> None:
    settings = Settings(_env_file=None, log_level="debug")

    assert settings.api_prefix == "/api/v1"
    assert settings.log_level == "DEBUG"


def test_custom_api_prefix_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_prefix="/custom")


def test_canonical_root_cala_timeout_environment_name_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALA_TIMEOUT_SECONDS", "12.5")

    settings = Settings(_env_file=None)

    assert settings.cala_timeout_seconds == 12.5


def test_provider_secrets_are_optional() -> None:
    settings = Settings(_env_file=None)

    assert settings.openai_configured is False
    assert settings.cala_configured is False
    assert settings.fal_configured is False
    assert settings.offline_demo_enabled is True


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="verbose")


def test_backend_root_is_absolute() -> None:
    assert isinstance(BACKEND_ROOT, Path)
    assert BACKEND_ROOT.is_absolute()
