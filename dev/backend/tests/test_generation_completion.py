from dataclasses import replace
from datetime import date, time

import pytest

from app.domain.itineraries import ItineraryStatus, MediaRole, MediaStatus
from app.repositories.generation_runs import (
    GenerationRunStore,
    InvalidGenerationCompletionError,
)
from app.services.content_generation import (
    GeneratedMediaAsset,
    GeneratedStop,
    GenerationCompletion,
)


def valid_stop() -> GeneratedStop:
    return GeneratedStop(
        position=1,
        start_time=time(9),
        end_time=time(10, 30),
        name="Sagrada Família",
        category="landmark",
        description="A structured journal entry.",
        reason_to_visit="Begin the route with architecture.",
        address="Carrer de Mallorca, Barcelona",
        links=(
            {
                "kind": "map",
                "label": "Open in maps",
                "url": "https://maps.example/sagrada-familia",
            },
            {
                "kind": "official",
                "label": "Official website",
                "url": "https://sagradafamilia.org/",
            },
        ),
    )


def valid_hero() -> GeneratedMediaAsset:
    return GeneratedMediaAsset(
        role=MediaRole.HERO,
        status=MediaStatus.READY,
        provider="fal",
        provider_request_id="fal-request-1",
        attempt_count=1,
        url="/media/itinerary-id/journal.jpg",
        storage_key="itinerary-id/journal.jpg",
        content_type="image/jpeg",
        width=1536,
        height=1024,
        alt_text="Hand-drawn Barcelona travel journal.",
        model_id="fal-ai/test",
    )


def valid_completion() -> GenerationCompletion:
    return GenerationCompletion(
        final_status=ItineraryStatus.READY,
        destination="Barcelona, Spain",
        planned_date=date(2026, 9, 5),
        destination_timezone="Europe/Madrid",
        title="A day in Barcelona",
        summary="A compact one-day route.",
        stops=(valid_stop(),),
        media_assets=(valid_hero(),),
    )


def assert_invalid(completion: GenerationCompletion, match: str) -> None:
    with pytest.raises(InvalidGenerationCompletionError, match=match):
        GenerationRunStore._validate_completion(completion)


def test_complete_result_with_date_timezone_links_and_one_hero_is_valid() -> None:
    GenerationRunStore._validate_completion(valid_completion())


def test_complete_result_requires_planned_date_and_timezone() -> None:
    completion = valid_completion()

    assert_invalid(replace(completion, planned_date=None), "planned date is required")  # type: ignore[arg-type]
    assert_invalid(replace(completion, destination_timezone=" "), "timezone is invalid")


def test_every_place_requires_at_least_one_map_link() -> None:
    completion = valid_completion()
    no_links = replace(valid_stop(), links=())
    official_only = replace(
        valid_stop(),
        links=(
            {
                "kind": "official",
                "label": "Official website",
                "url": "https://sagradafamilia.org/",
            },
        ),
    )

    assert_invalid(replace(completion, stops=(no_links,)), "at least one link")
    assert_invalid(replace(completion, stops=(official_only,)), "requires a map link")


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "/relative/maps/place",
        "https://",
        "https://user:password@example.com/place",
    ],
)
def test_place_links_require_public_http_urls_without_credentials(url: str) -> None:
    stop = replace(
        valid_stop(),
        links=({"kind": "map", "label": "Open in maps", "url": url},),
    )

    assert_invalid(replace(valid_completion(), stops=(stop,)), "URL is invalid")


def test_place_link_shape_and_values_are_strict() -> None:
    extra_field = replace(
        valid_stop(),
        links=(
            {
                "kind": "map",
                "label": "Open in maps",
                "url": "https://maps.example/place",
                "provider": "model",
            },
        ),
    )
    non_string = replace(
        valid_stop(),
        links=(
            {
                "kind": "map",
                "label": "Open in maps",
                "url": 42,
            },
        ),
    )

    assert_invalid(replace(valid_completion(), stops=(extra_field,)), "invalid shape")
    assert_invalid(  # type: ignore[arg-type]
        replace(valid_completion(), stops=(non_string,)),
        "values must be strings",
    )


def test_ready_result_requires_exactly_one_complete_itinerary_hero() -> None:
    completion = valid_completion()

    assert_invalid(replace(completion, media_assets=()), "exactly one ready journal image")
    assert_invalid(
        replace(completion, media_assets=(valid_hero(), valid_hero())),
        "exactly one ready journal image",
    )
    assert_invalid(
        replace(completion, media_assets=(replace(valid_hero(), stop_position=1),)),
        "cannot belong to a stop",
    )
    assert_invalid(
        replace(completion, media_assets=(replace(valid_hero(), content_type=None),)),
        "ready media output is incomplete",
    )


@pytest.mark.asyncio
async def test_store_rejects_partial_completion_before_opening_a_database_session() -> None:
    completion = replace(valid_completion(), final_status=ItineraryStatus.PARTIAL)
    store = GenerationRunStore(None, lease_seconds=60)  # type: ignore[arg-type]

    with pytest.raises(
        InvalidGenerationCompletionError,
        match="did not return a complete itinerary",
    ):
        await store.succeed(None, completion=completion)  # type: ignore[arg-type]
