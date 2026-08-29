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
    image_link: str | None
    decision: PreferenceDecision | None


class PreferencePageResponse(BaseModel):
    id: UUID
    position: int
    layout: PreferencePageLayout
    source: PreferencePageSource
    entries: list[PreferenceEntryResponse]


class PreferencePageFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: dict[UUID, PreferenceDecision | None]
