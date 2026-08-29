import hashlib
from typing import Any
from uuid import uuid4

import pytest

from app.db.models import Itinerary
from app.domain.itineraries import ItineraryStatus, PublicItineraryStatus
from app.repositories.itineraries import CreatedItinerary
from app.services.itineraries import ItineraryService


class RecordingRepository:
    def __init__(self, created: CreatedItinerary) -> None:
        self.created = created
        self.create_calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> CreatedItinerary:
        self.create_calls.append(kwargs)
        return self.created


def created_itinerary(
    *,
    replayed: bool = False,
    status: ItineraryStatus = ItineraryStatus.LEARNING_PREFERENCES,
) -> CreatedItinerary:
    itinerary = Itinerary(
        id=uuid4(),
        city="Barcelona",
        tags=["art", "food"],
        destination=None,
        request_fingerprint="f" * 64,
        status=status,
    )
    return CreatedItinerary(
        itinerary=itinerary,
        replayed=replayed,
    )


@pytest.mark.asyncio
async def test_service_cleans_city_and_tags_and_hashes_idempotency_data() -> None:
    created = created_itinerary()
    repository = RecordingRepository(created)
    service = ItineraryService(repository)  # type: ignore[arg-type]

    accepted = await service.create(
        "  Barcelona  ",
        ["  Art  ", "local   food", "ART"],
        "client-request:1",
    )

    assert accepted.id == created.itinerary.id
    assert accepted.status == PublicItineraryStatus.PENDING
    assert accepted.replayed is False
    assert len(repository.create_calls) == 1
    persisted = repository.create_calls[0]
    assert persisted["city"] == "Barcelona"
    assert persisted["tags"] == ["Art", "local food"]
    assert persisted["idempotency_key_hash"] == hashlib.sha256(b"client-request:1").hexdigest()
    assert persisted["idempotency_key_hash"] != "client-request:1"
    assert persisted["request_fingerprint"] == ItineraryService._fingerprint(
        "Barcelona", ["Art", "local food"]
    )
    assert persisted["legacy_request_fingerprint"] is None


def test_city_tag_fingerprint_ignores_case_order_and_duplicate_tags() -> None:
    assert ItineraryService._fingerprint("Barcelona", ["Art", "Food"]) == (
        ItineraryService._fingerprint("barcelona", ["food", "ART", "art"])
    )


def test_legacy_fingerprint_matches_the_city_only_v1_contract() -> None:
    canonical = b'{"city":"barcelona","version":1}'

    assert (
        ItineraryService._legacy_fingerprint("Barcelona") == hashlib.sha256(canonical).hexdigest()
    )


@pytest.mark.asyncio
async def test_idempotency_replay_returns_current_public_status() -> None:
    created = created_itinerary(replayed=True, status=ItineraryStatus.READY)
    repository = RecordingRepository(created)
    service = ItineraryService(repository)  # type: ignore[arg-type]

    accepted = await service.create("Barcelona", ["architecture"], "replayed-request")

    assert accepted.replayed is True
    assert accepted.status == PublicItineraryStatus.DONE
