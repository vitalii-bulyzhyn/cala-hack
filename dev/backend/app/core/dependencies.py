from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.repositories.itineraries import ItineraryRepository
from app.repositories.preference_learning import PreferenceLearningRepository
from app.services.itineraries import ItineraryService
from app.services.preference_learning import PreferenceLearningAlgorithm, PreferenceLearningService
from app.services.readiness import ReadinessChecker
from app.worker.queue import GenerationQueue


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_readiness_checker(request: Request) -> ReadinessChecker:
    return request.app.state.readiness_checker


async def get_database_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.session_factory() as session:
        yield session


def get_generation_queue(request: Request) -> GenerationQueue:
    return request.app.state.generation_queue


def get_preference_learning_algorithm(request: Request) -> PreferenceLearningAlgorithm:
    return request.app.state.preference_learning_algorithm


def get_itinerary_service(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> ItineraryService:
    return ItineraryService(ItineraryRepository(session))


def get_preference_learning_service(
    session: Annotated[AsyncSession, Depends(get_database_session)],
    algorithm: Annotated[
        PreferenceLearningAlgorithm,
        Depends(get_preference_learning_algorithm),
    ],
    queue: Annotated[GenerationQueue, Depends(get_generation_queue)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> PreferenceLearningService:
    return PreferenceLearningService(
        PreferenceLearningRepository(session),
        algorithm,
        queue,
        generation_max_attempts=settings.generation_max_attempts,
    )
