from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.api.itinerary_schemas import (
    ErrorResponse,
    ItineraryAcceptedResponse,
    ItineraryCreateRequest,
    ItineraryErrorResponse,
    ItineraryResponse,
    ItineraryResultResponse,
    JournalImageResponse,
    PlaceLinkResponse,
    PlaceLocationResponse,
    PlaceResponse,
)
from app.core.dependencies import get_itinerary_service
from app.db.models import Itinerary
from app.domain.itineraries import (
    MediaRole,
    MediaStatus,
    PendingItineraryStage,
    PublicItineraryStatus,
    public_itinerary_status,
)
from app.services.itineraries import ItineraryService

router = APIRouter()


def _resource_response(itinerary: Itinerary) -> ItineraryResponse:
    places = []
    for stop in itinerary.stops:
        location = None
        if stop.address is not None or stop.latitude is not None or stop.longitude is not None:
            location = PlaceLocationResponse(
                address=stop.address,
                latitude=float(stop.latitude) if stop.latitude is not None else None,
                longitude=float(stop.longitude) if stop.longitude is not None else None,
            )
        places.append(
            PlaceResponse(
                id=stop.id,
                position=stop.position,
                start_time=stop.start_time.strftime("%H:%M"),
                end_time=stop.end_time.strftime("%H:%M"),
                name=stop.name,
                category=stop.category,
                description=stop.description,
                reason_to_visit=stop.reason_to_visit,
                location=location,
                links=[PlaceLinkResponse.model_validate(link) for link in stop.links],
            )
        )

    error = None
    if itinerary.error_code is not None:
        error = ItineraryErrorResponse(
            code=itinerary.error_code,
            message=itinerary.error_message or "The itinerary could not be completed.",
            retryable=bool(itinerary.error_retryable),
            request_id=itinerary.error_request_id or f"job_{itinerary.id.hex}",
        )

    public_status = public_itinerary_status(itinerary.status)
    result = None
    if public_status == PublicItineraryStatus.DONE:
        hero = next(
            (
                asset
                for asset in itinerary.media_assets
                if asset.role == MediaRole.HERO and asset.status == MediaStatus.READY
            ),
            None,
        )
        result_is_complete = not (
            hero is None
            or not hero.url
            or not hero.content_type
            or not hero.width
            or not hero.height
            or not hero.alt_text
            or not itinerary.destination
            or itinerary.planned_date is None
            or not itinerary.destination_timezone
            or not itinerary.title
            or not itinerary.summary
            or not places
        )
        if result_is_complete:
            result = ItineraryResultResponse(
                destination=itinerary.destination,  # type: ignore[arg-type]
                planned_date=itinerary.planned_date,
                destination_timezone=itinerary.destination_timezone,
                title=itinerary.title,  # type: ignore[arg-type]
                summary=itinerary.summary,  # type: ignore[arg-type]
                journal_image=JournalImageResponse(
                    id=hero.id,  # type: ignore[union-attr]
                    url=hero.url,  # type: ignore[arg-type,union-attr]
                    content_type=hero.content_type,  # type: ignore[union-attr]
                    width=hero.width,  # type: ignore[union-attr]
                    height=hero.height,  # type: ignore[union-attr]
                    alt_text=hero.alt_text,  # type: ignore[union-attr]
                ),
                places=places,
            )
        else:
            public_status = PublicItineraryStatus.FAIL
            error = error or ItineraryErrorResponse(
                code="RESULT_INCOMPLETE",
                message="The generated itinerary is incomplete.",
                retryable=False,
                request_id=f"job_{itinerary.id.hex}",
            )

    return ItineraryResponse(
        id=itinerary.id,
        city=itinerary.city,
        tags=itinerary.tags,
        status=public_status,
        stage=(
            PendingItineraryStage(itinerary.status)
            if public_status == PublicItineraryStatus.PENDING
            else None
        ),
        result=result,
        error=error,
        created_at=itinerary.created_at,
        updated_at=itinerary.updated_at,
        completed_at=itinerary.completed_at,
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ItineraryAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def create_itinerary(
    payload: ItineraryCreateRequest,
    response: Response,
    request: Request,
    service: Annotated[ItineraryService, Depends(get_itinerary_service)],
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
            pattern=r"^[A-Za-z0-9._:-]+$",
        ),
    ] = None,
) -> ItineraryAcceptedResponse:
    accepted = await service.create(payload.city, payload.tags, idempotency_key)
    status_url = f"{request.app.state.settings.api_prefix}/itineraries/{accepted.id}"
    response.headers["Location"] = status_url
    response.headers["Cache-Control"] = "no-store"
    if accepted.replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return ItineraryAcceptedResponse(
        id=accepted.id,
        status=accepted.status,
        status_url=status_url,
    )


@router.get(
    "/{itinerary_id}",
    response_model=ItineraryResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def get_itinerary(
    itinerary_id: UUID,
    response: Response,
    request: Request,
    service: Annotated[ItineraryService, Depends(get_itinerary_service)],
) -> ItineraryResponse:
    itinerary = await service.get(itinerary_id)
    response.headers["Cache-Control"] = "no-store"
    resource = _resource_response(itinerary)
    if (
        resource.status == PublicItineraryStatus.PENDING
        and resource.stage != PendingItineraryStage.LEARNING_PREFERENCES
    ):
        response.headers["Retry-After"] = str(request.app.state.settings.worker_poll_seconds)
    return resource
