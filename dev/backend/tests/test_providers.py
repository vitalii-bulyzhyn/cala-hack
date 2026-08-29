from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.readiness import ReadinessChecker


def test_provider_status_is_safe_when_credentials_are_missing(
    client: TestClient,
    settings: Settings,
) -> None:
    response = client.get("/api/v1/providers/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "providers": {
            "openai": {
                "configured": False,
                "model": settings.openai_model,
                "base_url": None,
            },
            "cala": {
                "configured": False,
                "model": None,
                "base_url": "https://api.cala.ai",
            },
            "fal": {
                "configured": False,
                "model": settings.fal_image_model,
                "base_url": None,
            },
        }
    }
    assert "key" not in response.text.lower()


def test_provider_status_reports_configuration_without_exposing_secrets() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        openai_api_key="openai-secret",
        openai_model="gpt-test",
        cala_api_key="cala-secret",
        fal_key="fal-secret",
        fal_image_model="fal-ai/test-model",
    )

    async def passing_probe() -> None:
        return None

    checker = ReadinessChecker(
        settings,
        postgres_probe=passing_probe,
        redis_probe=passing_probe,
    )
    application = create_app(settings, checker)

    with TestClient(application) as test_client:
        response = test_client.get("/api/v1/providers/status")

    assert response.status_code == 200
    payload = response.json()["providers"]
    assert payload["openai"] == {
        "configured": True,
        "model": "gpt-test",
        "base_url": None,
    }
    assert payload["cala"]["configured"] is True
    assert payload["fal"] == {
        "configured": True,
        "model": "fal-ai/test-model",
        "base_url": None,
    }
    assert "openai-secret" not in response.text
    assert "cala-secret" not in response.text
    assert "fal-secret" not in response.text
