import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import (
    ItineraryNotFoundError,
    PersistenceUnavailableError,
    PreferenceEngineInvalidOutputError,
    PreferenceEngineUnavailableError,
    PreferenceItemNotFoundError,
    PreferenceLearningClosedError,
    PreferencePageIncompleteError,
)
from app.db.models import PreferenceItem, PreferencePage, PreferenceResponse
from app.domain.preferences import (
    Activity,
    PreferenceDecision,
    PreferenceLearningStatus,
    PreferencePageSuggestion,
)
from app.repositories.preference_learning import (
    CompletedPreferenceLearning,
    PreferenceItemMissingError,
    PreferenceLearningClosedRepositoryError,
    PreferenceLearningRepository,
    PreferenceLearningSnapshot,
    PreferencePageIncompleteRepositoryError,
)
from app.worker.queue import GenerationQueue

logger = logging.getLogger(__name__)


class PreferenceAlgorithmNotConfiguredError(Exception):
    pass


class PreferenceLearningAlgorithm(Protocol):
    version: str

    async def get_initial_pairs(
        self,
        city: str,
        tags: tuple[str, ...],
    ) -> tuple[PreferencePageSuggestion, PreferencePageSuggestion, PreferencePageSuggestion]: ...

    async def get_next_page(
        self,
        city: str,
        tags: tuple[str, ...],
        selected_activities: tuple[Activity, ...],
        rejected_activities: tuple[Activity, ...],
    ) -> PreferencePageSuggestion | None: ...

    async def update_learning_algorithm(
        self,
        selected_activities: tuple[Activity, ...],
        rejected_activities: tuple[Activity, ...],
    ) -> None: ...


class UnconfiguredPreferenceLearningAlgorithm:
    """Explicit integration seam for the developer implementing recommendation logic."""

    version = "unconfigured"

    async def get_initial_pairs(
        self,
        city: str,
        tags: tuple[str, ...],
    ) -> tuple[PreferencePageSuggestion, PreferencePageSuggestion, PreferencePageSuggestion]:
        del city, tags
        raise PreferenceAlgorithmNotConfiguredError

    async def get_next_page(
        self,
        city: str,
        tags: tuple[str, ...],
        selected_activities: tuple[Activity, ...],
        rejected_activities: tuple[Activity, ...],
    ) -> PreferencePageSuggestion | None:
        del city, tags, selected_activities, rejected_activities
        raise PreferenceAlgorithmNotConfiguredError

    async def update_learning_algorithm(
        self,
        selected_activities: tuple[Activity, ...],
        rejected_activities: tuple[Activity, ...],
    ) -> None:
        del selected_activities, rejected_activities
        raise PreferenceAlgorithmNotConfiguredError


@dataclass(frozen=True)
class RecordedPreference:
    response: PreferenceResponse


class PreferenceLearningService:
    def __init__(
        self,
        repository: PreferenceLearningRepository,
        algorithm: PreferenceLearningAlgorithm,
        queue: GenerationQueue,
        *,
        generation_max_attempts: int,
    ) -> None:
        self._repository = repository
        self._algorithm = algorithm
        self._queue = queue
        self._generation_max_attempts = generation_max_attempts

    async def list_pages(self, itinerary_id: UUID) -> tuple[PreferencePage, ...]:
        snapshot = await self._snapshot(itinerary_id)
        return snapshot.pages

    async def get_next_page(self, itinerary_id: UUID) -> PreferencePage | None:
        snapshot = await self._snapshot(itinerary_id)
        self._ensure_collecting(snapshot)

        unanswered = _first_unanswered_page(snapshot)
        if unanswered is not None:
            return unanswered

        selected, rejected = _partition_activities(snapshot)
        try:
            if not snapshot.pages:
                initial = await self._algorithm.get_initial_pairs(
                    snapshot.city,
                    snapshot.tags,
                )
                if len(initial) != 3 or any(len(page.activities) != 2 for page in initial):
                    raise ValueError("initial preference output must contain exactly three pairs")
                return await self._repository.add_initial_pages_if_empty(
                    itinerary_id,
                    initial,
                    algorithm_version=self._algorithm.version,
                )
            suggestion = await self._algorithm.get_next_page(
                snapshot.city,
                snapshot.tags,
                selected,
                rejected,
            )
        except PreferenceAlgorithmNotConfiguredError as exc:
            raise PreferenceEngineUnavailableError from exc
        except ValueError as exc:
            raise PreferenceEngineInvalidOutputError from exc

        if suggestion is None:
            return None
        try:
            return await self._repository.add_adaptive_page(
                itinerary_id,
                suggestion,
                expected_page_count=len(snapshot.pages),
            )
        except PreferencePageIncompleteRepositoryError as exc:
            raise PreferencePageIncompleteError from exc
        except PreferenceLearningClosedRepositoryError as exc:
            raise PreferenceLearningClosedError from exc
        except SQLAlchemyError as exc:
            logger.exception("Could not append a preference page for itinerary %s", itinerary_id)
            raise PersistenceUnavailableError from exc

    async def record_response(
        self,
        itinerary_id: UUID,
        item_id: UUID,
        decision: PreferenceDecision,
    ) -> RecordedPreference:
        snapshot = await self._snapshot(itinerary_id)
        self._ensure_collecting(snapshot)
        try:
            response = await self._repository.record_response(
                itinerary_id,
                item_id,
                decision,
            )
        except PreferenceItemMissingError as exc:
            raise PreferenceItemNotFoundError from exc
        except PreferencePageIncompleteRepositoryError as exc:
            raise PreferencePageIncompleteError from exc
        except PreferenceLearningClosedRepositoryError as exc:
            raise PreferenceLearningClosedError from exc
        except SQLAlchemyError as exc:
            logger.exception("Could not record preference response for itinerary %s", itinerary_id)
            raise PersistenceUnavailableError from exc
        return RecordedPreference(response=response)

    async def complete(self, itinerary_id: UUID) -> CompletedPreferenceLearning:
        snapshot = await self._snapshot(itinerary_id)
        if snapshot.status == PreferenceLearningStatus.COMPLETED:
            return await self._repository.completed_result(itinerary_id)
        selected, rejected = _partition_activities(snapshot)
        try:
            await self._algorithm.update_learning_algorithm(selected, rejected)
            completed = await self._repository.complete(
                itinerary_id,
                algorithm_version=self._algorithm.version,
                max_attempts=self._generation_max_attempts,
            )
        except PreferenceAlgorithmNotConfiguredError as exc:
            raise PreferenceEngineUnavailableError from exc
        except PreferenceLearningClosedRepositoryError as exc:
            raise PreferenceLearningClosedError from exc
        except SQLAlchemyError as exc:
            logger.exception(
                "Could not complete preference learning for itinerary %s",
                itinerary_id,
            )
            raise PersistenceUnavailableError from exc

        if not completed.replayed:
            try:
                await self._queue.enqueue(completed.generation_run_id)
            except Exception as exc:
                logger.warning(
                    "Generation wake-up notification failed for durable run %s (%s)",
                    completed.generation_run_id,
                    type(exc).__name__,
                )
        return completed

    async def _snapshot(self, itinerary_id: UUID) -> PreferenceLearningSnapshot:
        try:
            snapshot = await self._repository.get_snapshot(itinerary_id)
        except SQLAlchemyError as exc:
            logger.exception("Could not load preference learning for itinerary %s", itinerary_id)
            raise PersistenceUnavailableError from exc
        if snapshot is None:
            raise ItineraryNotFoundError
        return snapshot

    @staticmethod
    def _ensure_collecting(snapshot: PreferenceLearningSnapshot) -> None:
        if snapshot.status != PreferenceLearningStatus.COLLECTING:
            raise PreferenceLearningClosedError


def _first_unanswered_page(snapshot: PreferenceLearningSnapshot) -> PreferencePage | None:
    for page in snapshot.pages:
        if any(entry.response is None for entry in page.entries):
            return page
    return None


def _partition_activities(
    snapshot: PreferenceLearningSnapshot,
) -> tuple[tuple[Activity, ...], tuple[Activity, ...]]:
    selected: list[Activity] = []
    rejected: list[Activity] = []
    for page in snapshot.pages:
        for entry in page.entries:
            if entry.response is None:
                continue
            activity = _activity(entry)
            if entry.response.decision == PreferenceDecision.LIKE:
                selected.append(activity)
            else:
                rejected.append(activity)
    return tuple(selected), tuple(rejected)


def _activity(entry: PreferenceItem) -> Activity:
    return Activity(
        name=entry.name,
        category=entry.category,
        description=entry.description,
        image_link=entry.image_link,
    )
