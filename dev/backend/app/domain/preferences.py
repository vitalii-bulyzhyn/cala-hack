from dataclasses import dataclass
from enum import StrEnum

from pydantic import AnyHttpUrl, TypeAdapter

from app.domain.itineraries import clean_human_text

_http_url = TypeAdapter(AnyHttpUrl)


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
    image_link: str

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
        image_link = str(_http_url.validate_python(self.image_link))
        if not image_link.startswith(("http://", "https://")) or len(image_link) > 2000:
            raise ValueError(
                "activity image_link must be an HTTP(S) URL of at most 2000 characters"
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
