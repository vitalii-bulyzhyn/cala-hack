import logging
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
    PreferencePageNotFoundError,
    UnsupportedJournalCityError,
)
from app.db.models import PreferenceItem, PreferencePage
from app.domain.preferences import (
    Activity,
    PreferenceAlgorithmState,
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
    PreferencePageMissingError,
)
from app.services.activity_recommendations import (
    UnsupportedJournalCityError as UnsupportedJournalCityAlgorithmError,
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
        issued_activities: tuple[Activity, ...],
        selected_activities: tuple[Activity, ...],
        rejected_activities: tuple[Activity, ...],
        algorithm_state: PreferenceAlgorithmState,
    ) -> PreferencePageSuggestion | None: ...


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
        issued_activities: tuple[Activity, ...],
        selected_activities: tuple[Activity, ...],
        rejected_activities: tuple[Activity, ...],
        algorithm_state: PreferenceAlgorithmState,
    ) -> PreferencePageSuggestion | None:
        del city, tags, issued_activities, selected_activities, rejected_activities, algorithm_state
        raise PreferenceAlgorithmNotConfiguredError


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

        selected, rejected = _partition_activities(snapshot)
        issued = _issued_activities(snapshot)
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
                issued,
                selected,
                rejected,
                snapshot.algorithm_state,
            )
        except PreferenceAlgorithmNotConfiguredError as exc:
            raise PreferenceEngineUnavailableError from exc
        except UnsupportedJournalCityAlgorithmError as exc:
            raise UnsupportedJournalCityError from exc
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

    async def record_page_feedback(
        self,
        itinerary_id: UUID,
        page_id: UUID,
        decisions: dict[UUID, PreferenceDecision | None],
    ) -> PreferencePage:
        try:
            return await self._repository.record_page_feedback(
                itinerary_id,
                page_id,
                decisions,
            )
        except PreferencePageMissingError as exc:
            raise PreferencePageNotFoundError from exc
        except PreferenceItemMissingError as exc:
            raise PreferenceItemNotFoundError from exc
        except PreferencePageIncompleteRepositoryError as exc:
            raise PreferencePageIncompleteError from exc
        except PreferenceLearningClosedRepositoryError as exc:
            raise PreferenceLearningClosedError from exc
        except SQLAlchemyError as exc:
            logger.exception("Could not record preference response for itinerary %s", itinerary_id)
            raise PersistenceUnavailableError from exc

    async def complete(self, itinerary_id: UUID) -> CompletedPreferenceLearning:
        snapshot = await self._snapshot(itinerary_id)
        if snapshot.status == PreferenceLearningStatus.COMPLETED:
            return await self._repository.completed_result(itinerary_id)
        try:
            completed = await self._repository.complete(
                itinerary_id,
                algorithm_version=self._algorithm.version,
                max_attempts=self._generation_max_attempts,
            )
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


def _issued_activities(snapshot: PreferenceLearningSnapshot) -> tuple[Activity, ...]:
    return tuple(_activity(entry) for page in snapshot.pages for entry in page.entries)


def _activity(entry: PreferenceItem) -> Activity:
    return Activity(
        name=entry.name,
        category=entry.category,
        description=entry.description,
        image_link=entry.image_link,
        cala_entity_id=entry.cala_entity_id,
        cala_entity_type=entry.cala_entity_type,
    )
