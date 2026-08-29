from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    GenerationRun,
    Itinerary,
    PreferenceItem,
    PreferenceLearningSession,
    PreferencePage,
    PreferenceResponse,
)
from app.domain.itineraries import GenerationStage, ItineraryStatus
from app.domain.preferences import (
    PreferenceAlgorithmState,
    PreferenceDecision,
    PreferenceLearningStatus,
    PreferencePageSource,
    PreferencePageSuggestion,
)


class PreferenceLearningClosedRepositoryError(Exception):
    pass


class PreferenceItemMissingError(Exception):
    pass


class PreferencePageMissingError(Exception):
    pass


class PreferenceAlgorithmStateInvalidError(Exception):
    pass


class PreferencePageIncompleteRepositoryError(Exception):
    pass


@dataclass(frozen=True)
class PreferenceLearningSnapshot:
    itinerary_id: UUID
    city: str
    tags: tuple[str, ...]
    status: PreferenceLearningStatus
    algorithm_state: PreferenceAlgorithmState
    pages: tuple[PreferencePage, ...]


@dataclass(frozen=True)
class CompletedPreferenceLearning:
    itinerary_id: UUID
    generation_run_id: UUID
    replayed: bool


class PreferenceLearningRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_snapshot(self, itinerary_id: UUID) -> PreferenceLearningSnapshot | None:
        itinerary = await self._session.scalar(
            select(Itinerary).where(Itinerary.id == itinerary_id)
        )
        if itinerary is None:
            return None
        learning = await self._session.scalar(
            select(PreferenceLearningSession).where(
                PreferenceLearningSession.itinerary_id == itinerary_id
            )
        )
        if learning is None:
            return None
        pages = await self._load_pages(itinerary_id)
        algorithm_state = self._validated_state(learning.algorithm_state)
        return PreferenceLearningSnapshot(
            itinerary_id=itinerary.id,
            city=itinerary.city,
            tags=tuple(itinerary.tags),
            status=learning.status,
            algorithm_state=algorithm_state,
            pages=tuple(pages),
        )

    async def add_initial_pages_if_empty(
        self,
        itinerary_id: UUID,
        suggestions: tuple[
            PreferencePageSuggestion,
            PreferencePageSuggestion,
            PreferencePageSuggestion,
        ],
        *,
        algorithm_version: str,
    ) -> PreferencePage:
        learning = await self._locked_learning(itinerary_id)
        self._ensure_collecting(learning)
        pages = await self._load_pages(itinerary_id)
        if pages:
            return self._first_unanswered(pages) or pages[-1]

        created_pages = [
            self._page_from_suggestion(
                itinerary_id,
                position=position,
                source=PreferencePageSource.INITIAL,
                suggestion=suggestion,
            )
            for position, suggestion in enumerate(suggestions, start=1)
        ]
        learning.algorithm_version = algorithm_version
        self._session.add_all(created_pages)
        await self._session.commit()
        persisted_pages = await self._load_pages(itinerary_id)
        return persisted_pages[0]

    async def add_adaptive_page(
        self,
        itinerary_id: UUID,
        suggestion: PreferencePageSuggestion,
        *,
        expected_page_count: int,
    ) -> PreferencePage:
        learning = await self._locked_learning(itinerary_id)
        self._ensure_collecting(learning)
        pages = await self._load_pages(itinerary_id)
        if len(pages) == expected_page_count + 1:
            return pages[-1]
        if len(pages) != expected_page_count or len(pages) < 3:
            raise PreferencePageIncompleteRepositoryError

        page = self._page_from_suggestion(
            itinerary_id,
            position=len(pages) + 1,
            source=PreferencePageSource.ADAPTIVE,
            suggestion=suggestion,
        )
        self._session.add(page)
        await self._session.commit()
        persisted_pages = await self._load_pages(itinerary_id)
        return persisted_pages[-1]

    async def record_page_feedback(
        self,
        itinerary_id: UUID,
        page_id: UUID,
        decisions: dict[UUID, PreferenceDecision | None],
    ) -> PreferencePage:
        learning = await self._locked_learning(itinerary_id)
        self._ensure_collecting(learning)
        page = await self._session.scalar(
            select(PreferencePage)
            .where(
                PreferencePage.itinerary_id == itinerary_id,
                PreferencePage.id == page_id,
            )
            .options(selectinload(PreferencePage.entries).selectinload(PreferenceItem.response))
            .with_for_update()
        )
        if page is None:
            await self._session.rollback()
            raise PreferencePageMissingError

        entries = {entry.id: entry for entry in page.entries}
        if not set(decisions).issubset(entries):
            await self._session.rollback()
            raise PreferenceItemMissingError

        for item_id, entry in entries.items():
            decision = decisions.get(item_id)
            if decision is None:
                if entry.response is not None:
                    entry.response = None
            elif entry.response is None:
                entry.response = PreferenceResponse(
                    itinerary_id=itinerary_id,
                    item_id=item_id,
                    decision=decision,
                )
            else:
                entry.response.decision = decision

        await self._session.flush()
        learning.algorithm_state = (await self._rebuild_algorithm_state(itinerary_id)).model_dump(
            mode="json"
        )
        await self._session.commit()
        return await self._load_page(itinerary_id, page_id)

    async def complete(
        self,
        itinerary_id: UUID,
        *,
        algorithm_version: str,
        max_attempts: int,
    ) -> CompletedPreferenceLearning:
        learning = await self._locked_learning(itinerary_id)
        if learning.status == PreferenceLearningStatus.COMPLETED:
            await self._session.rollback()
            return await self.completed_result(itinerary_id)

        itinerary = await self._session.scalar(
            select(Itinerary).where(Itinerary.id == itinerary_id).with_for_update()
        )
        if itinerary is None or itinerary.status != ItineraryStatus.LEARNING_PREFERENCES:
            await self._session.rollback()
            raise PreferenceLearningClosedRepositoryError
        now = await self._session.scalar(select(func.now()))
        assert isinstance(now, datetime)
        run_id = uuid4()
        learning.algorithm_state = (await self._rebuild_algorithm_state(itinerary_id)).model_dump(
            mode="json"
        )
        learning.status = PreferenceLearningStatus.COMPLETED
        learning.algorithm_version = algorithm_version
        learning.completed_at = now
        itinerary.status = ItineraryStatus.QUEUED
        itinerary.status_changed_at = now
        itinerary.state_version += 1
        run = GenerationRun(
            id=run_id,
            itinerary_id=itinerary_id,
            dedupe_key=f"itinerary:{itinerary_id}:orchestration:v4",
            stage=GenerationStage.ORCHESTRATION,
            max_attempts=max_attempts,
        )
        self._session.add(run)
        await self._session.commit()
        return CompletedPreferenceLearning(
            itinerary_id=itinerary_id,
            generation_run_id=run_id,
            replayed=False,
        )

    async def completed_result(self, itinerary_id: UUID) -> CompletedPreferenceLearning:
        run = await self._session.scalar(
            select(GenerationRun).where(
                GenerationRun.dedupe_key == f"itinerary:{itinerary_id}:orchestration:v4"
            )
        )
        if run is None:
            raise PreferenceLearningClosedRepositoryError
        return CompletedPreferenceLearning(
            itinerary_id=itinerary_id,
            generation_run_id=run.id,
            replayed=True,
        )

    async def _locked_learning(self, itinerary_id: UUID) -> PreferenceLearningSession:
        learning = await self._session.scalar(
            select(PreferenceLearningSession)
            .where(PreferenceLearningSession.itinerary_id == itinerary_id)
            .with_for_update()
        )
        if learning is None:
            raise PreferenceLearningClosedRepositoryError
        return learning

    async def _load_pages(self, itinerary_id: UUID) -> list[PreferencePage]:
        result = await self._session.scalars(
            select(PreferencePage)
            .where(PreferencePage.itinerary_id == itinerary_id)
            .options(selectinload(PreferencePage.entries).selectinload(PreferenceItem.response))
            .order_by(PreferencePage.position)
        )
        return list(result)

    async def _load_page(self, itinerary_id: UUID, page_id: UUID) -> PreferencePage:
        page = await self._session.scalar(
            select(PreferencePage)
            .where(
                PreferencePage.itinerary_id == itinerary_id,
                PreferencePage.id == page_id,
            )
            .options(selectinload(PreferencePage.entries).selectinload(PreferenceItem.response))
        )
        if page is None:
            raise PreferencePageMissingError
        return page

    async def _rebuild_algorithm_state(self, itinerary_id: UUID) -> PreferenceAlgorithmState:
        state = PreferenceAlgorithmState.priors()
        result = await self._session.execute(
            select(
                PreferencePage.source,
                PreferenceItem.category,
                PreferenceResponse.decision,
            )
            .join(PreferenceItem, PreferenceItem.page_id == PreferencePage.id)
            .join(
                PreferenceResponse,
                (PreferenceResponse.itinerary_id == PreferenceItem.itinerary_id)
                & (PreferenceResponse.item_id == PreferenceItem.id),
            )
            .where(PreferencePage.itinerary_id == itinerary_id)
        )
        arms = {category: arm.model_copy() for category, arm in state.arms.items()}
        for source, category, decision in result:
            arm = arms.get(category)
            if arm is None:
                continue
            if decision == PreferenceDecision.LIKE:
                arms[category] = arm.model_copy(update={"alpha": arm.alpha + 1.0})
            elif decision == PreferenceDecision.DISLIKE:
                penalty = 0.25 if source == PreferencePageSource.INITIAL else 0.5
                arms[category] = arm.model_copy(update={"beta": arm.beta + penalty})
        return PreferenceAlgorithmState(arms=arms)

    @staticmethod
    def _validated_state(payload: object) -> PreferenceAlgorithmState:
        if payload is None:
            return PreferenceAlgorithmState.priors()
        try:
            return PreferenceAlgorithmState.model_validate(payload)
        except ValidationError as exc:
            raise PreferenceAlgorithmStateInvalidError from exc

    @staticmethod
    def _ensure_collecting(learning: PreferenceLearningSession) -> None:
        if learning.status != PreferenceLearningStatus.COLLECTING:
            raise PreferenceLearningClosedRepositoryError

    @staticmethod
    def _first_unanswered(pages: list[PreferencePage]) -> PreferencePage | None:
        return next(
            (page for page in pages if any(entry.response is None for entry in page.entries)),
            None,
        )

    @staticmethod
    def _page_from_suggestion(
        itinerary_id: UUID,
        *,
        position: int,
        source: PreferencePageSource,
        suggestion: PreferencePageSuggestion,
    ) -> PreferencePage:
        page_id = uuid4()
        entries = [
            PreferenceItem(
                itinerary_id=itinerary_id,
                page_id=page_id,
                position=entry_position,
                name=activity.name,
                category=activity.category,
                description=activity.description,
                image_link=activity.image_link,
                cala_entity_id=activity.cala_entity_id,
                cala_entity_type=activity.cala_entity_type,
            )
            for entry_position, activity in enumerate(suggestion.activities, start=1)
        ]
        return PreferencePage(
            id=page_id,
            itinerary_id=itinerary_id,
            position=position,
            layout=suggestion.layout,
            source=source,
            entries=entries,
        )
