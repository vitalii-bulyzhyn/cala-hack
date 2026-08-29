from datetime import date, time
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.domain.itineraries import ItineraryStatus, MediaRole, MediaStatus
from app.repositories.generation_runs import ClaimedGenerationRun
from app.services.content_generation import (
    ContentGenerationFailure,
    GeneratedMediaAsset,
    GeneratedStop,
    GenerationCheckpoint,
    GenerationCompletion,
    GenerationTask,
    UnconfiguredContentGenerationPipeline,
)
from app.worker.processor import GenerationProcessor


class RecordingRunStore:
    def __init__(self, claim: ClaimedGenerationRun | None) -> None:
        self.claim_result = claim
        self.claim_calls: list[tuple[str, UUID | None]] = []
        self.plan_checkpoints: list[dict[str, Any]] = []
        self.image_submissions: list[dict[str, Any]] = []
        self.retries: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.successes: list[dict[str, Any]] = []

    async def claim(
        self,
        *,
        worker_id: str,
        run_id: UUID | None = None,
    ) -> ClaimedGenerationRun | None:
        self.claim_calls.append((worker_id, run_id))
        return self.claim_result

    async def save_plan_checkpoint(
        self,
        claim: ClaimedGenerationRun,
        checkpoint_data: dict[str, object],
    ) -> None:
        self.plan_checkpoints.append({"claim": claim, "checkpoint_data": checkpoint_data})

    async def save_image_submission(
        self,
        claim: ClaimedGenerationRun,
        *,
        provider: str,
        request_id: str,
        model_id: str,
    ) -> None:
        self.image_submissions.append(
            {
                "claim": claim,
                "provider": provider,
                "request_id": request_id,
                "model_id": model_id,
            }
        )

    async def extend_lease(self, claim: ClaimedGenerationRun) -> bool:
        del claim
        return True

    async def schedule_retry(
        self,
        claim: ClaimedGenerationRun,
        *,
        code: str,
        message: str,
        delay_seconds: float,
    ) -> None:
        self.retries.append(
            {
                "claim": claim,
                "code": code,
                "message": message,
                "delay_seconds": delay_seconds,
            }
        )

    async def fail(
        self,
        claim: ClaimedGenerationRun,
        *,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        self.failures.append(
            {
                "claim": claim,
                "code": code,
                "message": message,
                "retryable": retryable,
            }
        )

    async def succeed(
        self,
        claim: ClaimedGenerationRun,
        *,
        completion: GenerationCompletion,
    ) -> None:
        self.successes.append({"claim": claim, "completion": completion})


class FailingPipeline:
    def __init__(self, failure: ContentGenerationFailure) -> None:
        self.failure = failure
        self.tasks: list[GenerationTask] = []

    async def generate(
        self,
        task: GenerationTask,
        checkpoint: GenerationCheckpoint,
    ) -> GenerationCompletion:
        del checkpoint
        self.tasks.append(task)
        raise self.failure


class SuccessfulPipeline:
    def __init__(
        self,
        completion: GenerationCompletion,
        *,
        save_checkpoints: bool = False,
    ) -> None:
        self.completion = completion
        self.save_checkpoints = save_checkpoints
        self.tasks: list[GenerationTask] = []

    async def generate(
        self,
        task: GenerationTask,
        checkpoint: GenerationCheckpoint,
    ) -> GenerationCompletion:
        self.tasks.append(task)
        if self.save_checkpoints:
            await checkpoint.save_plan({"schema_version": "test-v1", "title": "Saved"})
            await checkpoint.save_image_submission(
                provider="fal",
                request_id="fal-request-1",
                model_id="fal-ai/test",
            )
        return self.completion


def claimed_run(
    *,
    attempt_count: int = 1,
    max_attempts: int = 3,
    checkpoint_data: dict[str, object] | None = None,
    provider_request_id: str | None = None,
    provider_model_id: str | None = None,
) -> ClaimedGenerationRun:
    return ClaimedGenerationRun(
        id=uuid4(),
        itinerary_id=uuid4(),
        attempt_count=attempt_count,
        max_attempts=max_attempts,
        lease_owner="worker:test",
        lease_version=1,
        city="Barcelona",
        tags=("architecture", "food"),
        reference_date=date(2026, 8, 29),
        checkpoint_data=checkpoint_data,
        provider_request_id=provider_request_id,
        provider_model_id=provider_model_id,
    )


def valid_completion() -> GenerationCompletion:
    return GenerationCompletion(
        final_status=ItineraryStatus.READY,
        destination="Barcelona, Spain",
        planned_date=date(2026, 9, 5),
        destination_timezone="Europe/Madrid",
        title="A day in Barcelona",
        summary="A compact one-day route.",
        stops=(
            GeneratedStop(
                position=1,
                start_time=time(9),
                end_time=time(10),
                name="First stop",
                category="sightseeing",
                description="A structured stop.",
                reason_to_visit="It belongs in the route.",
                links=(
                    {
                        "kind": "map",
                        "label": "Open in maps",
                        "url": "https://maps.example/first-stop",
                    },
                ),
            ),
        ),
        media_assets=(
            GeneratedMediaAsset(
                role=MediaRole.HERO,
                status=MediaStatus.READY,
                provider="fal",
                provider_request_id="fal-request-1",
                attempt_count=1,
                url="/media/itinerary/journal.jpg",
                storage_key="itinerary/journal.jpg",
                content_type="image/jpeg",
                width=1536,
                height=1024,
                alt_text="Hand-drawn Barcelona journal.",
                model_id="fal-ai/test",
            ),
        ),
    )


def processor(
    store: RecordingRunStore,
    pipeline: object,
    *,
    retry_base_seconds: float = 2.0,
) -> GenerationProcessor:
    return GenerationProcessor(
        store,  # type: ignore[arg-type]
        pipeline,  # type: ignore[arg-type]
        worker_id="worker:test",
        heartbeat_seconds=60,
        retry_base_seconds=retry_base_seconds,
    )


@pytest.mark.asyncio
async def test_unconfigured_pipeline_records_safe_terminal_failure() -> None:
    claim = claimed_run()
    store = RecordingRunStore(claim)
    pipeline = UnconfiguredContentGenerationPipeline(("OPENAI_API_KEY", "CALA_API_KEY", "FAL_KEY"))

    processed = await processor(store, pipeline).process_once(claim.id)

    assert processed is True
    assert store.claim_calls == [("worker:test", claim.id)]
    assert store.retries == []
    assert store.successes == []
    assert store.failures == [
        {
            "claim": claim,
            "code": "PROVIDER_CONFIGURATION_MISSING",
            "message": (
                "Itinerary generation is not configured. Missing: "
                "OPENAI_API_KEY, CALA_API_KEY, FAL_KEY."
            ),
            "retryable": False,
        }
    ]


@pytest.mark.asyncio
async def test_retryable_pipeline_failure_is_scheduled_with_attempt_backoff() -> None:
    claim = claimed_run(attempt_count=2, max_attempts=3)
    store = RecordingRunStore(claim)
    pipeline = FailingPipeline(
        ContentGenerationFailure(
            code="PROVIDER_RATE_LIMITED",
            message="The provider is temporarily busy.",
            retryable=True,
        )
    )

    processed = await processor(store, pipeline, retry_base_seconds=2.0).process_once(claim.id)

    assert processed is True
    assert pipeline.tasks == [
        GenerationTask(
            run_id=claim.id,
            itinerary_id=claim.itinerary_id,
            attempt_count=claim.attempt_count,
            city=claim.city,
            tags=claim.tags,
            reference_date=claim.reference_date,
            checkpoint_data=None,
            provider_request_id=None,
            provider_model_id=None,
        )
    ]
    assert store.failures == []
    assert store.retries == [
        {
            "claim": claim,
            "code": "PROVIDER_RATE_LIMITED",
            "message": "The provider is temporarily busy.",
            "delay_seconds": 6.0,
        }
    ]


@pytest.mark.asyncio
async def test_retryable_failure_becomes_terminal_after_last_attempt() -> None:
    claim = claimed_run(attempt_count=3, max_attempts=3)
    store = RecordingRunStore(claim)
    pipeline = FailingPipeline(
        ContentGenerationFailure(
            code="PROVIDER_TIMEOUT",
            message="The provider did not respond in time.",
            retryable=True,
        )
    )

    processed = await processor(store, pipeline).process_once()

    assert processed is True
    assert store.retries == []
    assert store.failures == [
        {
            "claim": claim,
            "code": "PROVIDER_TIMEOUT",
            "message": "The provider did not respond in time.",
            "retryable": True,
        }
    ]


@pytest.mark.asyncio
async def test_checkpoint_context_is_passed_and_new_checkpoints_are_fenced_through_store() -> None:
    saved_plan = {"schema_version": "city-tags-itinerary-v1", "destination": "Barcelona"}
    claim = claimed_run(
        checkpoint_data=saved_plan,
        provider_request_id="fal-existing-request",
        provider_model_id="fal-ai/existing",
    )
    store = RecordingRunStore(claim)
    pipeline = SuccessfulPipeline(valid_completion(), save_checkpoints=True)

    processed = await processor(store, pipeline).process_once(claim.id)

    assert processed is True
    assert pipeline.tasks == [
        GenerationTask(
            run_id=claim.id,
            itinerary_id=claim.itinerary_id,
            attempt_count=1,
            city="Barcelona",
            tags=("architecture", "food"),
            reference_date=date(2026, 8, 29),
            checkpoint_data=saved_plan,
            provider_request_id="fal-existing-request",
            provider_model_id="fal-ai/existing",
        )
    ]
    assert store.plan_checkpoints == [
        {
            "claim": claim,
            "checkpoint_data": {"schema_version": "test-v1", "title": "Saved"},
        }
    ]
    assert store.image_submissions == [
        {
            "claim": claim,
            "provider": "fal",
            "request_id": "fal-request-1",
            "model_id": "fal-ai/test",
        }
    ]
    assert store.successes == [{"claim": claim, "completion": pipeline.completion}]
    assert store.failures == []


@pytest.mark.asyncio
async def test_success_is_returned_to_the_fenced_store_as_app_owned_content() -> None:
    claim = claimed_run()
    store = RecordingRunStore(claim)
    completion = valid_completion()

    processed = await processor(store, SuccessfulPipeline(completion)).process_once(claim.id)

    assert processed is True
    assert store.successes == [{"claim": claim, "completion": completion}]
    assert store.failures == []
