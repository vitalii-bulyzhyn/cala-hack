from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, call
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.dependencies import get_itinerary_service
from app.core.errors import ItineraryNotFoundError
from app.db.models import Itinerary, MediaAsset, Stop
from app.domain.itineraries import (
    ItineraryStatus,
    MediaRole,
    MediaStatus,
    PublicItineraryStatus,
)
from app.main import create_app
from app.services.itineraries import AcceptedItinerary
from app.services.readiness import ReadinessChecker


@contextmanager
def itinerary_client(
    settings: Settings,
    healthy_checker: ReadinessChecker,
    service: object,
) -> Iterator[TestClient]:
    application = create_app(settings, healthy_checker)

    def override_service() -> object:
        return service

    application.dependency_overrides[get_itinerary_service] = override_service
    with TestClient(application) as test_client:
        yield test_client


def itinerary_resource(
    status: ItineraryStatus,
    *,
    stops: list[Stop] | None = None,
    media_assets: list[MediaAsset] | None = None,
    complete_result: bool = False,
) -> Itinerary:
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    return Itinerary(
        id=uuid4(),
        city="Barcelona",
        tags=["art", "food"],
        destination="Barcelona, Spain" if complete_result else None,
        planned_date=date(2026, 9, 5) if complete_result else None,
        destination_timezone="Europe/Madrid" if complete_result else None,
        request_fingerprint="f" * 64,
        status=status,
        title="A day in Barcelona" if complete_result else None,
        summary="A compact one-day route." if complete_result else None,
        state_version=1,
        status_changed_at=now,
        completed_at=(now if status in {ItineraryStatus.READY, ItineraryStatus.FAILED} else None),
        created_at=now,
        updated_at=now,
        stops=stops or [],
        media_assets=media_assets or [],
    )


def test_create_itinerary_returns_city_tags_202_and_replay_headers(
    settings: Settings,
    healthy_checker: ReadinessChecker,
) -> None:
    itinerary_id = UUID("a6983f02-f1ad-4cfb-b799-abccb1216e9a")
    service = SimpleNamespace(
        create=AsyncMock(
            side_effect=[
                AcceptedItinerary(
                    id=itinerary_id,
                    status=PublicItineraryStatus.PENDING,
                    replayed=False,
                ),
                AcceptedItinerary(
                    id=itinerary_id,
                    status=PublicItineraryStatus.DONE,
                    replayed=True,
                ),
            ]
        )
    )

    with itinerary_client(settings, healthy_checker, service) as client:
        first = client.post(
            "/api/v1/itineraries",
            json={"city": "  Barcelona  ", "tags": [" Art ", "local   food", "ART"]},
            headers={"Idempotency-Key": "request-1"},
        )
        replay = client.post(
            "/api/v1/itineraries",
            json={"city": "Barcelona", "tags": ["Art", "local food"]},
            headers={"Idempotency-Key": "request-1"},
        )

    expected_status_url = f"/api/v1/itineraries/{itinerary_id}"
    assert first.status_code == 202
    assert first.json() == {
        "id": str(itinerary_id),
        "status": "pending",
        "status_url": expected_status_url,
    }
    assert first.headers["location"] == expected_status_url
    assert "retry-after" not in first.headers
    assert first.headers["cache-control"] == "no-store"
    assert "idempotency-replayed" not in first.headers
    assert first.headers["x-request-id"].startswith("req_")

    assert replay.status_code == 202
    assert replay.json() == {
        "id": str(itinerary_id),
        "status": "done",
        "status_url": expected_status_url,
    }
    assert replay.headers["idempotency-replayed"] == "true"
    assert replay.headers["location"] == expected_status_url
    assert "retry-after" not in replay.headers
    assert service.create.await_args_list == [
        call("Barcelona", ["Art", "local food"], "request-1"),
        call("Barcelona", ["Art", "local food"], "request-1"),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"request": "Visit Barcelona"},
        {"city": "Barcelona"},
        {"tags": ["art"]},
        {"city": "", "tags": []},
        {"city": "   ", "tags": []},
        {"city": "12345", "tags": []},
        {"city": "Visit\nBarcelona", "tags": []},
        {"city": "a" * 161, "tags": []},
        {"city": "Paris", "tags": "art"},
        {"city": "Paris", "tags": ["1234"]},
        {"city": "Paris", "tags": [f"tag-{index}" for index in range(21)]},
        {"city": "Paris", "tags": [], "days": 2},
    ],
)
def test_create_itinerary_rejects_invalid_or_legacy_payloads_before_service_call(
    settings: Settings,
    healthy_checker: ReadinessChecker,
    payload: dict[str, object],
) -> None:
    service = SimpleNamespace(create=AsyncMock())

    with itinerary_client(settings, healthy_checker, service) as client:
        response = client.post("/api/v1/itineraries", json=payload)

    assert response.status_code == 422
    service.create.assert_not_awaited()


def test_create_itinerary_rejects_invalid_idempotency_key_before_service_call(
    settings: Settings,
    healthy_checker: ReadinessChecker,
) -> None:
    service = SimpleNamespace(create=AsyncMock())

    with itinerary_client(settings, healthy_checker, service) as client:
        response = client.post(
            "/api/v1/itineraries",
            json={"city": "Barcelona", "tags": ["art"]},
            headers={"Idempotency-Key": "contains spaces"},
        )

    assert response.status_code == 422
    service.create.assert_not_awaited()


@pytest.mark.parametrize(
    "internal_status",
    [
        ItineraryStatus.LEARNING_PREFERENCES,
        ItineraryStatus.QUEUED,
        ItineraryStatus.RESEARCHING,
        ItineraryStatus.PLANNING,
        ItineraryStatus.ILLUSTRATING,
    ],
)
def test_get_itinerary_projects_internal_work_to_pending(
    settings: Settings,
    healthy_checker: ReadinessChecker,
    internal_status: ItineraryStatus,
) -> None:
    itinerary = itinerary_resource(internal_status)
    service = SimpleNamespace(get=AsyncMock(return_value=itinerary))

    with itinerary_client(settings, healthy_checker, service) as client:
        response = client.get(f"/api/v1/itineraries/{itinerary.id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(itinerary.id),
        "city": "Barcelona",
        "tags": ["art", "food"],
        "status": "pending",
        "stage": internal_status.value,
        "result": None,
        "error": None,
        "created_at": "2026-08-29T12:00:00Z",
        "updated_at": "2026-08-29T12:00:00Z",
        "completed_at": None,
    }
    assert response.headers["cache-control"] == "no-store"
    if internal_status == ItineraryStatus.LEARNING_PREFERENCES:
        assert "retry-after" not in response.headers
    else:
        assert response.headers["retry-after"] == str(settings.worker_poll_seconds)


def test_get_itinerary_serializes_complete_journal_result(
    settings: Settings,
    healthy_checker: ReadinessChecker,
) -> None:
    itinerary_id = uuid4()
    stop_id = uuid4()
    asset_id = uuid4()
    stop = Stop(
        id=stop_id,
        itinerary_id=itinerary_id,
        position=1,
        start_time=time(9, 30),
        end_time=time(11, 0),
        name="Sagrada Família",
        category="landmark",
        description="A landmark stop.",
        reason_to_visit="Begin the day with architecture.",
        address="Carrer de Mallorca, Barcelona",
        latitude=Decimal("41.403600"),
        longitude=Decimal("2.174400"),
        evidence=[],
        links=[
            {
                "kind": "official",
                "label": "Official website",
                "url": "https://sagradafamilia.org/",
            },
            {
                "kind": "map",
                "label": "Open in maps",
                "url": "https://maps.example/sagrada-familia",
            },
        ],
    )
    hero = MediaAsset(
        id=asset_id,
        itinerary_id=itinerary_id,
        role=MediaRole.HERO,
        status=MediaStatus.READY,
        attempt_count=1,
        url=f"/media/{itinerary_id}/journal.jpg",
        storage_key=f"{itinerary_id}/journal.jpg",
        content_type="image/jpeg",
        width=1536,
        height=1024,
        alt_text="Hand-drawn Barcelona travel journal.",
    )
    itinerary = itinerary_resource(
        ItineraryStatus.READY,
        stops=[stop],
        media_assets=[hero],
        complete_result=True,
    )
    itinerary.id = itinerary_id
    service = SimpleNamespace(get=AsyncMock(return_value=itinerary))

    with itinerary_client(settings, healthy_checker, service) as client:
        response = client.get(f"/api/v1/itineraries/{itinerary_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "done"
    assert payload["stage"] is None
    assert payload["error"] is None
    assert payload["result"] == {
        "destination": "Barcelona, Spain",
        "planned_date": "2026-09-05",
        "destination_timezone": "Europe/Madrid",
        "title": "A day in Barcelona",
        "summary": "A compact one-day route.",
        "journal_image": {
            "id": str(asset_id),
            "url": f"http://testserver/media/{itinerary_id}/journal.jpg",
            "content_type": "image/jpeg",
            "width": 1536,
            "height": 1024,
            "alt_text": "Hand-drawn Barcelona travel journal.",
        },
        "places": [
            {
                "id": str(stop_id),
                "position": 1,
                "start_time": "09:30",
                "end_time": "11:00",
                "name": "Sagrada Família",
                "category": "landmark",
                "description": "A landmark stop.",
                "reason_to_visit": "Begin the day with architecture.",
                "location": {
                    "address": "Carrer de Mallorca, Barcelona",
                    "latitude": 41.4036,
                    "longitude": 2.1744,
                },
                "links": [
                    {
                        "kind": "official",
                        "label": "Official website",
                        "url": "https://sagradafamilia.org/",
                    },
                    {
                        "kind": "map",
                        "label": "Open in maps",
                        "url": "https://maps.example/sagrada-familia",
                    },
                ],
            }
        ],
    }
    assert "retry-after" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    service.get.assert_awaited_once_with(itinerary_id)


@pytest.mark.parametrize("internal_status", [ItineraryStatus.FAILED, ItineraryStatus.PARTIAL])
def test_get_itinerary_projects_terminal_failures_safely(
    settings: Settings,
    healthy_checker: ReadinessChecker,
    internal_status: ItineraryStatus,
) -> None:
    itinerary = itinerary_resource(internal_status)
    itinerary.completed_at = itinerary.created_at
    itinerary.error_code = "IMAGE_GENERATION_FAILED"
    itinerary.error_message = "The journal image could not be generated."
    itinerary.error_retryable = True
    itinerary.error_request_id = "job_safe"
    service = SimpleNamespace(get=AsyncMock(return_value=itinerary))

    with itinerary_client(settings, healthy_checker, service) as client:
        response = client.get(f"/api/v1/itineraries/{itinerary.id}")

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "fail"
    assert payload["stage"] is None
    assert payload["result"] is None
    assert payload["error"] == {
        "code": "IMAGE_GENERATION_FAILED",
        "message": "The journal image could not be generated.",
        "retryable": True,
        "request_id": "job_safe",
    }
    assert "retry-after" not in response.headers


def test_get_ready_but_incomplete_resource_projects_to_safe_fail(
    settings: Settings,
    healthy_checker: ReadinessChecker,
) -> None:
    itinerary = itinerary_resource(ItineraryStatus.READY, complete_result=True)
    service = SimpleNamespace(get=AsyncMock(return_value=itinerary))

    with itinerary_client(settings, healthy_checker, service) as client:
        response = client.get(f"/api/v1/itineraries/{itinerary.id}")

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "fail"
    assert payload["stage"] is None
    assert payload["result"] is None
    assert payload["error"]["code"] == "RESULT_INCOMPLETE"
    assert payload["error"]["retryable"] is False


def test_get_missing_itinerary_returns_safe_structured_error(
    settings: Settings,
    healthy_checker: ReadinessChecker,
) -> None:
    itinerary_id = uuid4()
    service = SimpleNamespace(get=AsyncMock(side_effect=ItineraryNotFoundError()))

    with itinerary_client(settings, healthy_checker, service) as client:
        response = client.get(f"/api/v1/itineraries/{itinerary_id}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "ITINERARY_NOT_FOUND",
            "message": "The requested itinerary does not exist.",
            "retryable": False,
            "request_id": response.headers["x-request-id"],
        }
    }
    assert "traceback" not in response.text.lower()
    assert "database" not in response.text.lower()
    service.get.assert_awaited_once_with(itinerary_id)
