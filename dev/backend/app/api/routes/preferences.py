from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.itinerary_schemas import ErrorResponse, ItineraryAcceptedResponse
from app.api.preference_schemas import (
    PreferenceEntryResponse,
    PreferencePageFeedbackRequest,
    PreferencePageResponse,
)
from app.core.dependencies import get_preference_learning_service
from app.domain.itineraries import PublicItineraryStatus
from app.services.preference_learning import PreferenceLearningService

router = APIRouter()


def _page_response(page) -> PreferencePageResponse:  # type: ignore[no-untyped-def]
    return PreferencePageResponse(
        id=page.id,
        position=page.position,
        layout=page.layout,
        source=page.source,
        entries=[
            PreferenceEntryResponse(
                id=entry.id,
                name=entry.name,
                category=entry.category,
                description=entry.description,
                image_link=entry.image_link,
                decision=(entry.response.decision if entry.response is not None else None),
            )
            for entry in page.entries
        ],
    )


@router.get(
    "/{itinerary_id}/preference-pages",
    response_model=list[PreferencePageResponse],
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def list_preference_pages(
    itinerary_id: UUID,
    response: Response,
    service: Annotated[PreferenceLearningService, Depends(get_preference_learning_service)],
) -> list[PreferencePageResponse]:
    pages = await service.list_pages(itinerary_id)
    response.headers["Cache-Control"] = "no-store"
    return [_page_response(page) for page in pages]


@router.get(
    "/{itinerary_id}/preference-pages/next",
    response_model=PreferencePageResponse,
    responses={
        status.HTTP_204_NO_CONTENT: {"description": "The algorithm has no next page."},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def get_next_preference_page(
    itinerary_id: UUID,
    response: Response,
    service: Annotated[PreferenceLearningService, Depends(get_preference_learning_service)],
) -> PreferencePageResponse | Response:
    page = await service.get_next_page(itinerary_id)
    if page is None:
        return Response(
            status_code=status.HTTP_204_NO_CONTENT,
            headers={"Cache-Control": "no-store"},
        )
    response.headers["Cache-Control"] = "no-store"
    return _page_response(page)


@router.put(
    "/{itinerary_id}/preference-pages/{page_id}/feedback",
    response_model=PreferencePageResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def record_preference_page_feedback(
    itinerary_id: UUID,
    page_id: UUID,
    payload: PreferencePageFeedbackRequest,
    response: Response,
    service: Annotated[PreferenceLearningService, Depends(get_preference_learning_service)],
) -> PreferencePageResponse:
    page = await service.record_page_feedback(itinerary_id, page_id, payload.decisions)
    response.headers["Cache-Control"] = "no-store"
    return _page_response(page)


@router.post(
    "/{itinerary_id}/preference-learning/complete",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ItineraryAcceptedResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def complete_preference_learning(
    itinerary_id: UUID,
    request: Request,
    response: Response,
    service: Annotated[PreferenceLearningService, Depends(get_preference_learning_service)],
) -> ItineraryAcceptedResponse:
    completed = await service.complete(itinerary_id)
    status_url = f"{request.app.state.settings.api_prefix}/itineraries/{itinerary_id}"
    response.headers["Location"] = status_url
    response.headers["Retry-After"] = str(request.app.state.settings.worker_poll_seconds)
    response.headers["Cache-Control"] = "no-store"
    if completed.replayed:
        response.headers["Preference-Learning-Replayed"] = "true"
    return ItineraryAcceptedResponse(
        id=itinerary_id,
        status=PublicItineraryStatus.PENDING,
        status_url=status_url,
    )
