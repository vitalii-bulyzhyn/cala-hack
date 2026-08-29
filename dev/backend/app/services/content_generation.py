from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID, uuid5

from app.domain.itineraries import ItineraryStatus, MediaRole, MediaStatus
from app.domain.preferences import Activity


@dataclass(frozen=True)
class GenerationTask:
    run_id: UUID
    itinerary_id: UUID
    attempt_count: int
    city: str
    tags: tuple[str, ...]
    reference_date: date
    checkpoint_data: dict[str, Any] | None = None
    provider_request_id: str | None = None
    provider_model_id: str | None = None
    selected_activities: tuple[Activity, ...] = ()
    rejected_activities: tuple[Activity, ...] = ()


@dataclass(frozen=True)
class GeneratedStop:
    position: int
    start_time: time
    end_time: time
    name: str
    category: str
    description: str
    reason_to_visit: str
    address: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    cala_entity_id: str | None = None
    evidence: tuple[dict[str, object], ...] = ()
    evidence_retrieved_at: datetime | None = None
    evidence_confidence: float | None = None
    links: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class GeneratedMediaAsset:
    id: UUID
    role: MediaRole
    status: MediaStatus
    stop_position: int | None = None
    provider: str | None = None
    provider_request_id: str | None = None
    attempt_count: int = 0
    url: str | None = None
    storage_key: str | None = None
    content_type: str | None = None
    expires_at: datetime | None = None
    width: int | None = None
    height: int | None = None
    alt_text: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def generated_image_id(run_id: UUID, role: MediaRole, stop_position: int | None = None) -> UUID:
    """Return the stable public image ID for a logical image slot in one durable run."""
    owner = "itinerary" if stop_position is None else f"stop:{stop_position}"
    return uuid5(run_id, f"{role.value}:{owner}")


@dataclass(frozen=True)
class GenerationCompletion:
    final_status: ItineraryStatus
    destination: str
    planned_date: date
    destination_timezone: str
    title: str
    summary: str
    stops: tuple[GeneratedStop, ...]
    media_assets: tuple[GeneratedMediaAsset, ...] = ()
    error_code: str | None = None
    error_message: str | None = None
    error_retryable: bool | None = None


@dataclass(eq=False)
class ContentGenerationFailure(Exception):
    code: str
    message: str
    retryable: bool


class GenerationCheckpoint(Protocol):
    async def save_plan(self, checkpoint_data: dict[str, Any]) -> None: ...

    async def save_image_submission(
        self,
        *,
        provider: str,
        request_id: str,
        model_id: str,
    ) -> None: ...


class ContentGenerationPipeline(Protocol):
    """Generate app-owned values only; durable writes belong to the fenced processor."""

    async def generate(
        self,
        task: GenerationTask,
        checkpoint: GenerationCheckpoint,
    ) -> GenerationCompletion: ...


class UnconfiguredContentGenerationPipeline:
    """Keep the worker alive while reporting missing provider configuration safely."""

    def __init__(self, missing_providers: tuple[str, ...]) -> None:
        self._missing_providers = missing_providers

    async def generate(
        self,
        task: GenerationTask,
        checkpoint: GenerationCheckpoint,
    ) -> GenerationCompletion:
        del task
        del checkpoint
        raise ContentGenerationFailure(
            code="PROVIDER_CONFIGURATION_MISSING",
            message=(
                "Itinerary generation is not configured. Missing: "
                + ", ".join(self._missing_providers)
                + "."
            ),
            retryable=False,
        )
