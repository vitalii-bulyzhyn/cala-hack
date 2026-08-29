from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

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
    PreferenceDecision,
    PreferenceLearningStatus,
    PreferencePageSource,
    PreferencePageSuggestion,
)


class PreferenceLearningClosedRepositoryError(Exception):
    pass


class PreferenceItemMissingError(Exception):
    pass


class PreferencePageIncompleteRepositoryError(Exception):
    pass


class PreferenceLearningIncompleteRepositoryError(Exception):
    pass


@dataclass(frozen=True)
class PreferenceLearningSnapshot:
    itinerary_id: UUID
    city: str
    tags: tuple[str, ...]
    status: PreferenceLearningStatus
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
        return PreferenceLearningSnapshot(
            itinerary_id=itinerary.id,
            city=itinerary.city,
            tags=tuple(itinerary.tags),
            status=learning.status,
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
        current = self._first_unanswered(pages)
        if current is not None:
            return current
        if len(pages) != expected_page_count:
            return pages[-1]

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

    async def record_response(
        self,
        itinerary_id: UUID,
        item_id: UUID,
        decision: PreferenceDecision,
    ) -> PreferenceResponse:
        learning = await self._locked_learning(itinerary_id)
        self._ensure_collecting(learning)
        item = await self._session.scalar(
            select(PreferenceItem)
            .where(
                PreferenceItem.itinerary_id == itinerary_id,
                PreferenceItem.id == item_id,
            )
            .options(selectinload(PreferenceItem.response))
            .with_for_update()
        )
        if item is None:
            await self._session.rollback()
            raise PreferenceItemMissingError
        response = item.response
        if response is None:
            response = PreferenceResponse(
                itinerary_id=itinerary_id,
                item_id=item_id,
                decision=decision,
            )
            self._session.add(response)
        else:
            response.decision = decision
        await self._session.commit()
        await self._session.refresh(response)
        return response

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
        pages = await self._load_pages(itinerary_id)
        responses = [
            entry.response for page in pages for entry in page.entries if entry.response is not None
        ]
        has_answered_adaptive_page = any(
            page.source == PreferencePageSource.ADAPTIVE
            and page.entries
            and all(entry.response is not None for entry in page.entries)
            for page in pages
        )
        if (
            len(responses) < 7
            or not has_answered_adaptive_page
            or self._first_unanswered(pages) is not None
        ):
            await self._session.rollback()
            raise PreferenceLearningIncompleteRepositoryError

        itinerary = await self._session.scalar(
            select(Itinerary).where(Itinerary.id == itinerary_id).with_for_update()
        )
        if itinerary is None or itinerary.status != ItineraryStatus.LEARNING_PREFERENCES:
            await self._session.rollback()
            raise PreferenceLearningClosedRepositoryError
        now = await self._session.scalar(select(func.now()))
        assert isinstance(now, datetime)
        run_id = uuid4()
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
