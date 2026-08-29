import asyncio
import logging
from contextlib import suppress
from typing import Any
from uuid import UUID

from app.repositories.generation_runs import (
    ClaimedGenerationRun,
    GenerationRunStore,
    InvalidGenerationCompletionError,
    LostLeaseError,
)
from app.services.content_generation import (
    ContentGenerationFailure,
    ContentGenerationPipeline,
    GenerationCheckpoint,
    GenerationTask,
)

logger = logging.getLogger(__name__)


class StoreGenerationCheckpoint(GenerationCheckpoint):
    def __init__(self, store: GenerationRunStore, claim: ClaimedGenerationRun) -> None:
        self._store = store
        self._claim = claim

    async def save_plan(self, checkpoint_data: dict[str, Any]) -> None:
        await self._store.save_plan_checkpoint(self._claim, checkpoint_data)

    async def save_image_submission(
        self,
        *,
        provider: str,
        request_id: str,
        model_id: str,
    ) -> None:
        await self._store.save_image_submission(
            self._claim,
            provider=provider,
            request_id=request_id,
            model_id=model_id,
        )


class GenerationProcessor:
    def __init__(
        self,
        store: GenerationRunStore,
        pipeline: ContentGenerationPipeline,
        *,
        worker_id: str,
        heartbeat_seconds: int,
        retry_base_seconds: float,
    ) -> None:
        self._store = store
        self._pipeline = pipeline
        self._worker_id = worker_id
        self._heartbeat_seconds = heartbeat_seconds
        self._retry_base_seconds = retry_base_seconds

    async def process_once(self, run_id: UUID | None = None) -> bool:
        claim = await self._store.claim(worker_id=self._worker_id, run_id=run_id)
        if claim is None:
            return False

        work = GenerationTask(
            run_id=claim.id,
            itinerary_id=claim.itinerary_id,
            attempt_count=claim.attempt_count,
            city=claim.city,
            tags=claim.tags,
            reference_date=claim.reference_date,
            checkpoint_data=claim.checkpoint_data,
            provider_request_id=claim.provider_request_id,
            provider_model_id=claim.provider_model_id,
            selected_activities=claim.selected_activities,
            rejected_activities=claim.rejected_activities,
        )
        checkpoint = StoreGenerationCheckpoint(self._store, claim)
        pipeline_task = asyncio.create_task(self._pipeline.generate(work, checkpoint))
        heartbeat_task = asyncio.create_task(self._heartbeat(claim, pipeline_task))
        try:
            completion = await pipeline_task
        except ContentGenerationFailure as exc:
            await self._record_failure(claim, exc)
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            logger.warning("Processing stopped after losing the lease for run %s", claim.id)
        except Exception as exc:
            logger.error(
                "Unexpected content pipeline failure for run %s (%s)",
                claim.id,
                type(exc).__name__,
            )
            await self._fail_if_owned(
                claim,
                code="UNEXPECTED_GENERATION_ERROR",
                message="The itinerary could not be completed.",
                retryable=False,
            )
        else:
            try:
                await self._store.succeed(claim, completion=completion)
            except LostLeaseError:
                logger.warning("Lost lease before recording success for run %s", claim.id)
            except InvalidGenerationCompletionError as exc:
                logger.error(
                    "Content pipeline violated completion invariants for run %s (%s)",
                    claim.id,
                    type(exc).__name__,
                )
                await self._fail_if_owned(
                    claim,
                    code="INVALID_GENERATION_OUTPUT",
                    message="The generated itinerary did not satisfy the required structure.",
                    retryable=False,
                )
        finally:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
        return True

    async def _record_failure(
        self,
        claim: ClaimedGenerationRun,
        failure: ContentGenerationFailure,
    ) -> None:
        if failure.retryable and claim.attempt_count < claim.max_attempts:
            delay = self._retry_base_seconds * (3 ** (claim.attempt_count - 1))
            try:
                await self._store.schedule_retry(
                    claim,
                    code=failure.code,
                    message=failure.message,
                    delay_seconds=delay,
                )
            except LostLeaseError:
                logger.warning("Lost lease before scheduling retry for run %s", claim.id)
            return
        await self._fail_if_owned(
            claim,
            code=failure.code,
            message=failure.message,
            retryable=failure.retryable,
        )

    async def _fail_if_owned(
        self,
        claim: ClaimedGenerationRun,
        *,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        try:
            await self._store.fail(
                claim,
                code=code,
                message=message,
                retryable=retryable,
            )
        except LostLeaseError:
            logger.warning("Lost lease before recording failure for run %s", claim.id)

    async def _heartbeat(
        self,
        claim: ClaimedGenerationRun,
        pipeline_task: asyncio.Task,
    ) -> None:
        while not pipeline_task.done():
            await asyncio.sleep(self._heartbeat_seconds)
            if pipeline_task.done():
                return
            try:
                lease_extended = await self._store.extend_lease(claim)
            except Exception as exc:
                logger.error(
                    "Could not extend lease for run %s (%s)",
                    claim.id,
                    type(exc).__name__,
                )
                pipeline_task.cancel()
                return
            if not lease_extended:
                logger.warning("Lease was lost while processing run %s", claim.id)
                pipeline_task.cancel()
                return
