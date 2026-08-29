from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.readiness import ReadinessChecker


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        cors_origins=["http://localhost:3000"],
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        redis_url="redis://localhost:6379/15",
        openai_api_key=None,
        cala_api_key=None,
        fal_key=None,
        media_storage_path=tmp_path / "generated-media",
    )


@pytest.fixture
def healthy_checker(settings: Settings) -> ReadinessChecker:
    async def passing_probe() -> None:
        return None

    return ReadinessChecker(
        settings,
        postgres_probe=passing_probe,
        redis_probe=passing_probe,
    )


@pytest.fixture
def client(settings: Settings, healthy_checker: ReadinessChecker) -> Iterator[TestClient]:
    application = create_app(settings, healthy_checker)
    with TestClient(application) as test_client:
        yield test_client
