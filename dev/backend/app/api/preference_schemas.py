from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.preferences import (
    PreferenceDecision,
    PreferencePageLayout,
    PreferencePageSource,
)


class PreferenceEntryResponse(BaseModel):
    id: UUID
    name: str
    category: str
    description: str
    image_link: str
    decision: PreferenceDecision | None


class PreferencePageResponse(BaseModel):
    id: UUID
    position: int
    layout: PreferencePageLayout
    source: PreferencePageSource
    entries: list[PreferenceEntryResponse]


class PreferenceDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: PreferenceDecision


class PreferenceDecisionResponse(BaseModel):
    itinerary_id: UUID
    item_id: UUID
    decision: PreferenceDecision
    recorded_at: datetime
