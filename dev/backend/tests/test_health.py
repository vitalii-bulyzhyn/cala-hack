from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.readiness import ReadinessChecker


def test_liveness_does_not_depend_on_external_services(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_structured_success(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["postgres"]["status"] == "ok"
    assert payload["checks"]["redis"]["status"] == "ok"


def test_readiness_returns_503_and_all_checks_when_one_dependency_fails(
    settings: Settings,
) -> None:
    async def passing_probe() -> None:
        return None

    async def failing_probe() -> None:
        raise ConnectionError("intentionally unavailable")

    checker = ReadinessChecker(
        settings,
        postgres_probe=failing_probe,
        redis_probe=passing_probe,
    )
    application = create_app(settings, checker)

    with TestClient(application) as test_client:
        response = test_client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["postgres"]["status"] == "error"
    assert response.json()["checks"]["redis"]["status"] == "ok"


def test_readiness_remains_ready_when_optional_redis_is_unavailable(
    settings: Settings,
) -> None:
    async def passing_probe() -> None:
        return None

    async def failing_probe() -> None:
        raise ConnectionError("intentionally unavailable")

    checker = ReadinessChecker(
        settings,
        postgres_probe=passing_probe,
        redis_probe=failing_probe,
    )
    application = create_app(settings, checker)

    with TestClient(application) as test_client:
        response = test_client.get("/api/v1/health/ready")

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "ready"
    assert payload["checks"]["postgres"] == {
        "status": "ok",
        "required": True,
        "latency_ms": payload["checks"]["postgres"]["latency_ms"],
    }
    assert payload["checks"]["redis"] == {
        "status": "error",
        "required": False,
        "latency_ms": payload["checks"]["redis"]["latency_ms"],
    }


def test_cors_preflight_allows_configured_frontend(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health/live",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["x-request-id"].startswith("req_")
