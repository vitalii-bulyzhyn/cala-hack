from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.itineraries import (
    PendingItineraryStage,
    PlaceLinkKind,
    PublicItineraryStatus,
    clean_city,
    clean_tags,
)
from app.domain.preferences import SUPPORTED_JOURNAL_CITIES


class ItineraryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: Annotated[str, Field(min_length=1, max_length=160)]
    tags: Annotated[list[str], Field(max_length=20)]

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str) -> str:
        city = clean_city(value)
        supported = {candidate.casefold(): candidate for candidate in SUPPORTED_JOURNAL_CITIES}
        canonical = supported.get(city.casefold())
        if canonical is None:
            raise ValueError("city must be Barcelona, Toulouse, or Valencia")
        return canonical

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        return clean_tags(value)


class ItineraryAcceptedResponse(BaseModel):
    id: UUID
    status: PublicItineraryStatus
    status_url: str


class PlaceLocationResponse(BaseModel):
    address: str | None
    latitude: float | None
    longitude: float | None


class PlaceLinkResponse(BaseModel):
    kind: PlaceLinkKind
    label: str
    url: str


class PlaceResponse(BaseModel):
    id: UUID
    position: int = Field(ge=1)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    name: str
    category: str
    description: str
    reason_to_visit: str
    location: PlaceLocationResponse | None
    links: list[PlaceLinkResponse]


class JournalImageResponse(BaseModel):
    id: UUID
    url: str
    content_type: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    alt_text: str


class ItineraryResultResponse(BaseModel):
    destination: str
    planned_date: date
    destination_timezone: str
    title: str
    summary: str
    journal_image: JournalImageResponse
    places: list[PlaceResponse]


class ItineraryErrorResponse(BaseModel):
    code: str
    message: str
    retryable: bool
    request_id: str


class ItineraryResponse(BaseModel):
    id: UUID
    city: str
    tags: list[str]
    status: PublicItineraryStatus
    stage: PendingItineraryStage | None
    result: ItineraryResultResponse | None
    error: ItineraryErrorResponse | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
