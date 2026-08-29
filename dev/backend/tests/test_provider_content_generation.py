import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import fal_client
import httpx
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
)

from app.domain.itineraries import ItineraryStatus, MediaRole, MediaStatus
from app.integrations.base import ProviderRequestError
from app.integrations.dto.cala import (
    CalaKnowledgeQueryResponse,
    CalaKnowledgeSearchResponse,
)
from app.integrations.media_storage import MediaStorageError, StoredMedia
from app.services.content_generation import ContentGenerationFailure, GenerationTask
from app.services.provider_content_generation import (
    CHECKPOINT_SCHEMA_VERSION,
    ILLUSTRATION_PROMPT_VERSION,
    CheckpointPlace,
    ModelItineraryPlan,
    ModelPlannedPlace,
    PlanCheckpoint,
    ProviderContentGenerationPipeline,
    TripIntent,
)


class FakeOpenAIResponses:
    def __init__(self, values: list[object]) -> None:
        self._values = values
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        value = self._values.pop(0)
        if isinstance(value, BaseException):
            raise value
        return SimpleNamespace(output_parsed=value)


class FakeOpenAI:
    def __init__(self, values: list[object]) -> None:
        self.responses = FakeOpenAIResponses(values)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeCala:
    def __init__(
        self,
        *,
        query: CalaKnowledgeQueryResponse | BaseException | None = None,
        search: CalaKnowledgeSearchResponse | BaseException | None = None,
    ) -> None:
        self.query = query or _cala_query()
        self.search = search or _cala_search()
        self.query_calls: list[str] = []
        self.search_calls: list[str] = []
        self.closed = False

    async def knowledge_query(self, query: str) -> CalaKnowledgeQueryResponse:
        self.query_calls.append(query)
        if isinstance(self.query, BaseException):
            raise self.query
        return self.query

    async def knowledge_search(self, query: str) -> CalaKnowledgeSearchResponse:
        self.search_calls.append(query)
        if isinstance(self.search, BaseException):
            raise self.search
        return self.search

    async def aclose(self) -> None:
        self.closed = True


class FakeFalHandle:
    def __init__(self, request_id: str, result: object) -> None:
        self.request_id = request_id
        self._result = result
        self.get_calls = 0

    async def get(self) -> object:
        self.get_calls += 1
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result


class FakeFal:
    def __init__(self, result: object, *, request_id: str = "fal-request-1") -> None:
        self.handle = FakeFalHandle(request_id, result)
        self.submit_calls: list[dict[str, Any]] = []
        self.get_handle_calls: list[tuple[str, str]] = []

    async def submit(self, model_id: str, **kwargs: Any) -> FakeFalHandle:
        self.submit_calls.append({"model_id": model_id, **kwargs})
        return self.handle

    async def get_handle(self, model_id: str, request_id: str) -> FakeFalHandle:
        self.get_handle_calls.append((model_id, request_id))
        return self.handle


class FakeMediaStore:
    def __init__(self, result: StoredMedia | BaseException | None = None) -> None:
        self.result = result or StoredMedia(
            storage_key="owned/journal.jpg",
            public_url="/media/owned/journal.jpg",
            content_type="image/jpeg",
            byte_count=1234,
        )
        self.copy_calls: list[dict[str, object]] = []
        self.closed = False

    async def copy_from_provider(self, **kwargs: object) -> StoredMedia:
        self.copy_calls.append(kwargs)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result

    async def aclose(self) -> None:
        self.closed = True


class RecordingCheckpoint:
    def __init__(self) -> None:
        self.plans: list[dict[str, Any]] = []
        self.image_submissions: list[dict[str, str]] = []

    async def save_plan(self, checkpoint_data: dict[str, Any]) -> None:
        self.plans.append(checkpoint_data)

    async def save_image_submission(
        self,
        *,
        provider: str,
        request_id: str,
        model_id: str,
    ) -> None:
        self.image_submissions.append(
            {"provider": provider, "request_id": request_id, "model_id": model_id}
        )


def _task(**updates: object) -> GenerationTask:
    values: dict[str, object] = {
        "run_id": uuid4(),
        "itinerary_id": UUID("660c265a-32d8-4b14-ad56-8f8d466b0cc9"),
        "attempt_count": 2,
        "city": "Barcelona",
        "tags": ("architecture", "local food"),
        "reference_date": date(2026, 8, 29),
    }
    values.update(updates)
    return GenerationTask(**values)  # type: ignore[arg-type]


def _intent() -> TripIntent:
    return TripIntent(
        is_valid_trip_request=True,
        destination="  Barcelona,   Spain ",
        planned_date=date(2026, 9, 5),
        destination_timezone="Europe/Madrid",
        preferences=["architecture"],
    )


def _plan() -> ModelItineraryPlan:
    return ModelItineraryPlan(
        title="Ink and stone in Barcelona",
        summary="A walk through three grounded architectural highlights.",
        places=[
            ModelPlannedPlace(
                position=2,
                start_time="11:00",
                end_time="12:30",
                name="Park Guell",
                category="park",
                description="A hillside garden shaped by Gaudi's imagination.",
                reason_to_visit="It adds greenery and playful forms to the day.",
                address="08024 Barcelona",
                latitude=41.4145,
                longitude=None,
                cala_entity_id="invented-entity",
                official_url="https://invented.example/park",
                source_urls=[],
            ),
            ModelPlannedPlace(
                position=1,
                start_time="09:00",
                end_time="10:30",
                name="Sagrada Familia",
                category="landmark",
                description="Gaudi's unfinished basilica anchors the morning.",
                reason_to_visit="Its light and geometry set the journal's visual theme.",
                address="Carrer de Mallorca, 401, Barcelona",
                latitude=41.4036,
                longitude=2.1744,
                cala_entity_id="entity-sagrada",
                official_url="https://sagrada.example/visit",
                source_urls=[
                    "https://sagrada.example/visit",
                    "https://source.example/sagrada",
                    "https://hallucinated.example/not-grounded",
                ],
            ),
            ModelPlannedPlace(
                position=3,
                start_time="14:00",
                end_time="16:00",
                name="Casa Batllo",
                category="museum",
                description="A colorful residential facade closes the route.",
                reason_to_visit="The interiors extend the day's organic design story.",
                address=None,
                latitude=None,
                longitude=None,
                cala_entity_id=None,
                official_url=None,
                source_urls=["https://source.example/casa-batllo"],
            ),
        ],
    )


def _cala_query() -> CalaKnowledgeQueryResponse:
    return CalaKnowledgeQueryResponse(
        results=[
            {
                "name": "Sagrada Familia",
                "official_url": "https://sagrada.example/visit",
                "entity": {
                    "id": "entity-sagrada",
                    "entity_type": "place",
                },
            },
            {
                "name": "Casa Batllo",
                "source_url": "https://source.example/casa-batllo",
            },
        ],
        entities=[
            {
                "id": "entity-sagrada",
                "name": "Sagrada Familia",
                "entity_type": "place",
            }
        ],
    )


def _cala_search() -> CalaKnowledgeSearchResponse:
    return CalaKnowledgeSearchResponse(
        content="Background: https://source.example/sagrada.",
        context=[],
        entities=[],
    )


def _fal_result() -> dict[str, object]:
    return {
        "images": [
            {
                "url": "https://fal.example/generated/journal.jpg",
                "width": 1536,
                "height": 1024,
                "content_type": "image/jpeg",
            }
        ],
        "has_nsfw_concepts": [False],
    }


def _saved_plan() -> dict[str, Any]:
    places = [
        CheckpointPlace(
            position=index,
            start_time=start,
            end_time=end,
            name=name,
            category="landmark",
            description=f"A grounded description of {name}.",
            reason_to_visit=f"A grounded reason to visit {name}.",
            address=None,
            latitude=None,
            longitude=None,
            cala_entity_id=None,
            links=[
                {
                    "kind": "map",
                    "label": "Open in maps",
                    "url": f"https://maps.example/search/{index}",
                }
            ],
            evidence=[],
        )
        for index, start, end, name in [
            (1, "09:00", "10:00", "First Place"),
            (2, "11:00", "12:00", "Second Place"),
            (3, "14:00", "15:00", "Third Place"),
        ]
    ]
    return PlanCheckpoint(
        schema_version=CHECKPOINT_SCHEMA_VERSION,
        destination="Barcelona, Spain",
        planned_date=date(2026, 9, 5),
        destination_timezone="Europe/Madrid",
        title="Saved Barcelona day",
        summary="A saved, resumable itinerary.",
        places=places,
        illustration_prompt="A hand-drawn Barcelona journal.",
        illustration_alt_text="Hand-drawn Barcelona journal.",
        research_retrieved_at=datetime(2026, 8, 29, 12, tzinfo=UTC),
    ).model_dump(mode="json")


def _pipeline(
    *,
    openai: FakeOpenAI | None = None,
    cala: FakeCala | None = None,
    fal: FakeFal | None = None,
    media: FakeMediaStore | None = None,
) -> tuple[ProviderContentGenerationPipeline, FakeOpenAI, FakeCala, FakeFal, FakeMediaStore]:
    openai = openai or FakeOpenAI([_intent(), _plan()])
    cala = cala or FakeCala()
    fal = fal or FakeFal(_fal_result())
    media = media or FakeMediaStore()
    pipeline = ProviderContentGenerationPipeline(
        openai_client=openai,  # type: ignore[arg-type]
        cala=cala,  # type: ignore[arg-type]
        fal_client_instance=fal,  # type: ignore[arg-type]
        media_store=media,  # type: ignore[arg-type]
        openai_model="test-planner",
        fal_image_model="test-image-model",
        fal_start_timeout_seconds=2,
        fal_result_timeout_seconds=2,
        context_max_chars=30_000,
    )
    return pipeline, openai, cala, fal, media


@pytest.mark.asyncio
async def test_generates_grounded_itinerary_and_persists_owned_hero() -> None:
    pipeline, openai, cala, fal, media = _pipeline()
    checkpoint = RecordingCheckpoint()
    task = _task()

    completion = await pipeline.generate(task, checkpoint)

    assert completion.final_status is ItineraryStatus.READY
    assert completion.destination == "Barcelona, Spain"
    assert completion.planned_date == date(2026, 9, 5)
    assert completion.destination_timezone == "Europe/Madrid"
    assert [stop.name for stop in completion.stops] == [
        "Sagrada Familia",
        "Park Guell",
        "Casa Batllo",
    ]

    first = completion.stops[0]
    assert first.latitude == Decimal("41.4036")
    assert first.longitude == Decimal("2.1744")
    assert first.cala_entity_id == "entity-sagrada"
    assert [link["kind"] for link in first.links] == ["map", "official", "source"]
    assert first.evidence == (
        {"url": "https://sagrada.example/visit"},
        {"url": "https://source.example/sagrada"},
    )
    assert all("hallucinated.example" not in link["url"] for link in first.links)
    map_query = parse_qs(urlsplit(first.links[0]["url"]).query)["query"]
    assert map_query == ["Sagrada Familia, Carrer de Mallorca, 401, Barcelona, Barcelona, Spain"]

    second = completion.stops[1]
    assert second.latitude is None
    assert second.longitude is None
    assert second.cala_entity_id is None
    assert [link["kind"] for link in second.links] == ["map"]

    hero = completion.media_assets[0]
    assert hero.role is MediaRole.HERO
    assert hero.status is MediaStatus.READY
    assert hero.provider == "fal"
    assert hero.provider_request_id == "fal-request-1"
    assert hero.attempt_count == 2
    assert hero.url == "/media/owned/journal.jpg"
    assert hero.storage_key == "owned/journal.jpg"
    assert hero.content_type == "image/jpeg"
    assert (hero.width, hero.height) == (1536, 1024)
    assert hero.prompt_version == ILLUSTRATION_PROMPT_VERSION
    assert hero.alt_text is not None and "Barcelona, Spain" in hero.alt_text

    assert len(checkpoint.plans) == 1
    assert checkpoint.image_submissions == [
        {
            "provider": "fal",
            "request_id": "fal-request-1",
            "model_id": "test-image-model",
        }
    ]
    assert len(openai.responses.calls) == 2
    assert openai.responses.calls[0]["text_format"] is TripIntent
    assert openai.responses.calls[1]["text_format"] is ModelItineraryPlan
    assert json.loads(openai.responses.calls[0]["input"]) == {
        "city": "Barcelona",
        "tags": ["architecture", "local food"],
        "selected_activities": [],
        "rejected_activities": [],
    }
    assert all(call["store"] is False for call in openai.responses.calls)
    assert len(cala.query_calls) == len(cala.search_calls) == 1

    assert len(fal.submit_calls) == 1
    submission = fal.submit_calls[0]
    assert submission["model_id"] == "test-image-model"
    assert (
        submission["arguments"]["seed"]
        == int.from_bytes(  # type: ignore[index]
            hashlib.sha256(task.itinerary_id.bytes).digest()[:4], "big"
        )
    )
    assert submission["arguments"]["prompt"].startswith(  # type: ignore[index]
        "An open hand-drawn travel journal"
    )
    assert media.copy_calls == [
        {
            "source_url": "https://fal.example/generated/journal.jpg",
            "itinerary_id": task.itinerary_id,
            "expected_content_type": "image/jpeg",
        }
    ]

    await pipeline.aclose()
    assert openai.closed is True
    assert cala.closed is True
    assert media.closed is True


@pytest.mark.asyncio
async def test_resumes_saved_plan_and_fal_request_without_repeating_provider_work() -> None:
    openai = FakeOpenAI([])
    cala = FakeCala()
    fal = FakeFal(_fal_result(), request_id="fal-resumed-request")
    pipeline, _, _, _, media = _pipeline(openai=openai, cala=cala, fal=fal)
    checkpoint = RecordingCheckpoint()
    task = _task(
        checkpoint_data=_saved_plan(),
        provider_request_id="fal-resumed-request",
        provider_model_id="resumed-image-model",
    )

    completion = await pipeline.generate(task, checkpoint)

    assert completion.title == "Saved Barcelona day"
    assert checkpoint.plans == []
    assert checkpoint.image_submissions == []
    assert openai.responses.calls == []
    assert cala.query_calls == []
    assert cala.search_calls == []
    assert fal.submit_calls == []
    assert fal.get_handle_calls == [("resumed-image-model", "fal-resumed-request")]
    assert media.copy_calls[0]["source_url"] == "https://fal.example/generated/journal.jpg"


@pytest.mark.asyncio
async def test_rejects_invalid_checkpoint_before_calling_providers() -> None:
    openai = FakeOpenAI([])
    cala = FakeCala()
    fal = FakeFal(_fal_result())
    pipeline, _, _, _, media = _pipeline(openai=openai, cala=cala, fal=fal)

    with pytest.raises(ContentGenerationFailure) as raised:
        await pipeline.generate(
            _task(checkpoint_data={"schema_version": CHECKPOINT_SCHEMA_VERSION, "places": []}),
            RecordingCheckpoint(),
        )

    assert raised.value.code == "GENERATION_CHECKPOINT_INVALID"
    assert raised.value.retryable is False
    assert openai.responses.calls == []
    assert cala.query_calls == []
    assert fal.submit_calls == []
    assert media.copy_calls == []


@pytest.mark.asyncio
async def test_rejects_request_without_complete_trip_intent() -> None:
    invalid = TripIntent(
        is_valid_trip_request=False,
        destination=None,
        planned_date=None,
        destination_timezone=None,
        preferences=[],
    )
    pipeline, _, cala, fal, media = _pipeline(openai=FakeOpenAI([invalid]))

    with pytest.raises(ContentGenerationFailure) as raised:
        await pipeline.generate(_task(), RecordingCheckpoint())

    assert raised.value.code == "TRIP_REQUEST_INVALID"
    assert raised.value.retryable is False
    assert cala.query_calls == []
    assert fal.submit_calls == []
    assert media.copy_calls == []


@pytest.mark.asyncio
async def test_translates_cala_failure_without_exposing_provider_body() -> None:
    failure = ProviderRequestError(
        provider="cala",
        code="CALA_RATE_LIMITED",
        message="Place research is temporarily busy.",
        retryable=True,
        status_code=429,
    )
    pipeline, _, _, fal, media = _pipeline(
        openai=FakeOpenAI([_intent()]),
        cala=FakeCala(query=failure),
    )

    with pytest.raises(ContentGenerationFailure) as raised:
        await pipeline.generate(_task(), RecordingCheckpoint())

    assert raised.value.code == "CALA_RATE_LIMITED"
    assert raised.value.message == "Place research is temporarily busy."
    assert raised.value.retryable is True
    assert fal.submit_calls == []
    assert media.copy_calls == []


@pytest.mark.asyncio
async def test_rejects_empty_cala_research() -> None:
    pipeline, _, _, fal, media = _pipeline(
        openai=FakeOpenAI([_intent()]),
        cala=FakeCala(
            query=CalaKnowledgeQueryResponse(results=[], entities=[]),
            search=CalaKnowledgeSearchResponse(content="", context=[], entities=[]),
        ),
    )

    with pytest.raises(ContentGenerationFailure) as raised:
        await pipeline.generate(_task(), RecordingCheckpoint())

    assert raised.value.code == "PLACE_RESEARCH_EMPTY"
    assert raised.value.retryable is False
    assert fal.submit_calls == []
    assert media.copy_calls == []


@pytest.mark.asyncio
async def test_rejects_missing_openai_structured_output() -> None:
    pipeline, _, cala, fal, media = _pipeline(openai=FakeOpenAI([None]))

    with pytest.raises(ContentGenerationFailure) as raised:
        await pipeline.generate(_task(), RecordingCheckpoint())

    assert raised.value.code == "OPENAI_INVALID_RESPONSE"
    assert raised.value.retryable is False
    assert cala.query_calls == []
    assert fal.submit_calls == []
    assert media.copy_calls == []


def _openai_failure_cases() -> list[tuple[BaseException, str, bool]]:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return [
        (
            RateLimitError(
                "sensitive provider detail",
                response=httpx.Response(429, request=request),
                body=None,
            ),
            "OPENAI_RATE_LIMITED",
            True,
        ),
        (APIConnectionError(request=request), "OPENAI_UNAVAILABLE", True),
        (APITimeoutError(request), "OPENAI_UNAVAILABLE", True),
        (
            APIStatusError(
                "sensitive provider detail",
                response=httpx.Response(500, request=request),
                body=None,
            ),
            "OPENAI_REQUEST_FAILED",
            True,
        ),
        (
            APIStatusError(
                "sensitive provider detail",
                response=httpx.Response(400, request=request),
                body=None,
            ),
            "OPENAI_REQUEST_FAILED",
            False,
        ),
        (RuntimeError("sensitive provider detail"), "OPENAI_INVALID_RESPONSE", False),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_retryable"), _openai_failure_cases()
)
async def test_classifies_openai_failures_with_safe_errors(
    failure: BaseException,
    expected_code: str,
    expected_retryable: bool,
) -> None:
    pipeline, _, cala, fal, media = _pipeline(openai=FakeOpenAI([failure]))

    with pytest.raises(ContentGenerationFailure) as raised:
        await pipeline.generate(_task(), RecordingCheckpoint())

    assert raised.value.code == expected_code
    assert raised.value.retryable is expected_retryable
    assert "sensitive provider detail" not in raised.value.message
    assert cala.query_calls == []
    assert fal.submit_calls == []
    assert media.copy_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "expected_code"),
    [
        ({"images": []}, "IMAGE_GENERATION_INVALID_RESPONSE"),
        (
            {
                "images": [
                    {
                        "url": "http://fal.example/image.jpg",
                        "width": 100,
                        "height": 100,
                        "content_type": "image/jpeg",
                    }
                ]
            },
            "IMAGE_GENERATION_INVALID_RESPONSE",
        ),
        (
            {
                "images": [
                    {
                        "url": "https://fal.example/image.jpg",
                        "width": 100,
                        "height": 100,
                        "content_type": "image/jpeg",
                    }
                ],
                "has_nsfw_concepts": [True],
            },
            "IMAGE_SAFETY_REJECTED",
        ),
    ],
)
async def test_rejects_unsafe_or_malformed_fal_results(
    result: object,
    expected_code: str,
) -> None:
    fal = FakeFal(result)
    pipeline, _, _, _, media = _pipeline(fal=fal)

    with pytest.raises(ContentGenerationFailure) as raised:
        await pipeline.generate(
            _task(checkpoint_data=_saved_plan()),
            RecordingCheckpoint(),
        )

    assert raised.value.code == expected_code
    assert raised.value.retryable is False
    assert fal.handle.get_calls == 1
    assert media.copy_calls == []


def _fal_http_error(status_code: int) -> fal_client.FalClientHTTPError:
    request = httpx.Request("POST", "https://queue.fal.run/test")
    response = httpx.Response(status_code, request=request)
    return fal_client.FalClientHTTPError(
        message="sensitive fal provider detail",
        status_code=status_code,
        response_headers={},
        response=response,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_retryable"),
    [
        (fal_client.FalClientTimeoutError(1), "IMAGE_GENERATION_TIMEOUT", True),
        (_fal_http_error(429), "IMAGE_GENERATION_FAILED", True),
        (_fal_http_error(503), "IMAGE_GENERATION_FAILED", True),
        (_fal_http_error(400), "IMAGE_GENERATION_FAILED", False),
        (RuntimeError("sensitive fal provider detail"), "IMAGE_GENERATION_FAILED", False),
    ],
)
async def test_classifies_fal_failures_with_safe_errors(
    failure: BaseException,
    expected_code: str,
    expected_retryable: bool,
) -> None:
    fal = FakeFal(failure)
    pipeline, _, _, _, media = _pipeline(fal=fal)
    checkpoint = RecordingCheckpoint()

    with pytest.raises(ContentGenerationFailure) as raised:
        await pipeline.generate(
            _task(checkpoint_data=_saved_plan()),
            checkpoint,
        )

    assert raised.value.code == expected_code
    assert raised.value.retryable is expected_retryable
    assert "sensitive fal provider detail" not in raised.value.message
    assert checkpoint.image_submissions == [
        {
            "provider": "fal",
            "request_id": "fal-request-1",
            "model_id": "test-image-model",
        }
    ]
    assert media.copy_calls == []


@pytest.mark.asyncio
async def test_translates_owned_media_persistence_failure() -> None:
    media = FakeMediaStore(
        MediaStorageError(
            code="IMAGE_DOWNLOAD_UNAVAILABLE",
            message="The generated journal image could not be downloaded yet.",
            retryable=True,
        )
    )
    pipeline, _, _, _, _ = _pipeline(media=media)

    with pytest.raises(ContentGenerationFailure) as raised:
        await pipeline.generate(
            _task(checkpoint_data=_saved_plan()),
            RecordingCheckpoint(),
        )

    assert raised.value.code == "IMAGE_DOWNLOAD_UNAVAILABLE"
    assert raised.value.message == "The generated journal image could not be downloaded yet."
    assert raised.value.retryable is True
    assert len(media.copy_calls) == 1
