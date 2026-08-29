from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.domain.itineraries import clean_human_text

_http_url = TypeAdapter(AnyHttpUrl)

ActivityCategory = Literal["food", "culture", "outdoors", "neighbourhoods"]
ACTIVITY_CATEGORIES: tuple[ActivityCategory, ...] = (
    "food",
    "culture",
    "outdoors",
    "neighbourhoods",
)
SUPPORTED_JOURNAL_CITIES = ("Barcelona", "Toulouse", "Valencia")


class BanditArm(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    alpha: float = Field(gt=0)
    beta: float = Field(gt=0)


class PreferenceAlgorithmState(BaseModel):
    """Versioned, application-owned durable state for category sampling."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    arms: dict[ActivityCategory, BanditArm]

    @model_validator(mode="after")
    def require_every_category(self) -> "PreferenceAlgorithmState":
        if set(self.arms) != set(ACTIVITY_CATEGORIES):
            raise ValueError("algorithm state must contain exactly the four activity categories")
        return self

    @classmethod
    def priors(cls) -> "PreferenceAlgorithmState":
        return cls(
            arms={category: BanditArm(alpha=1.0, beta=1.0) for category in ACTIVITY_CATEGORIES}
        )


class PreferencePageLayout(StrEnum):
    SINGLE = "single"
    PAIR = "pair"


class PreferencePageSource(StrEnum):
    INITIAL = "initial"
    ADAPTIVE = "adaptive"


class PreferenceDecision(StrEnum):
    LIKE = "like"
    DISLIKE = "dislike"


class PreferenceLearningStatus(StrEnum):
    COLLECTING = "collecting"
    COMPLETED = "completed"


@dataclass(frozen=True)
class Activity:
    name: str
    category: str
    description: str
    image_link: str | None = None
    cala_entity_id: str | None = None
    cala_entity_type: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "name",
            clean_human_text(self.name, field="activity name", max_length=160),
        )
        object.__setattr__(
            self,
            "category",
            clean_human_text(self.category, field="activity category", max_length=80),
        )
        object.__setattr__(
            self,
            "description",
            clean_human_text(
                self.description,
                field="activity description",
                max_length=600,
            ),
        )
        if self.image_link is not None:
            raw_image_link = self.image_link.strip()
            if raw_image_link.startswith("/"):
                try:
                    image_id = raw_image_link.removeprefix("/").removesuffix(".png")
                    valid_relative = raw_image_link == f"/{UUID(image_id)}.png"
                except ValueError:
                    valid_relative = False
                image_link = raw_image_link
            else:
                image_link = str(_http_url.validate_python(raw_image_link))
                valid_relative = False
            if (
                not valid_relative
                and not image_link.startswith(("http://", "https://"))
            ) or len(image_link) > 2000:
                raise ValueError(
                    "activity image_link must be an HTTP(S) URL or /{UUID}.png"
                )
            object.__setattr__(self, "image_link", image_link)


@dataclass(frozen=True)
class PreferencePageSuggestion:
    activities: tuple[Activity, ...]

    def __post_init__(self) -> None:
        if len(self.activities) not in {1, 2}:
            raise ValueError("a preference page must contain one or two activities")

    @property
    def layout(self) -> PreferencePageLayout:
        if len(self.activities) == 1:
            return PreferencePageLayout.SINGLE
        return PreferencePageLayout.PAIR
