import hashlib
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Literal

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.domain.preferences import Activity, PreferencePageSuggestion
from app.integrations.openai import create_openai_client

logger = logging.getLogger(__name__)

ActivityCategory = Literal["food", "drinks_party", "culture", "nature"]
CATEGORIES: tuple[ActivityCategory, ...] = ("food", "drinks_party", "culture", "nature")
CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "activities.json"


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    category: ActivityCategory
    description: str = Field(min_length=1, max_length=600)
    image_link: str = Field(min_length=1, max_length=2000)
    signals: list[str] = Field(default_factory=list, max_length=20)

    def activity_for(self, city: str) -> Activity:
        return Activity(
            name=self.name,
            category=self.category,
            description=self.description.format(city=city),
            image_link=self.image_link,
        )


class RankedCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: ActivityCategory
    activity_names: list[str]


class RankedActivities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rankings: list[RankedCategory] = Field(min_length=4, max_length=4)


class ActivityRecommendationAlgorithm:
    """Catalog retrieval, LLM ranking, and a small online category learner."""

    version = "catalog-bandit-v1"

    def __init__(
        self,
        entries: tuple[CatalogEntry, ...],
        *,
        openai_client: AsyncOpenAI | None = None,
        openai_model: str | None = None,
    ) -> None:
        self._entries = entries
        self._openai = openai_client
        self._openai_model = openai_model
        names = [entry.name for entry in entries]
        if len(names) != len(set(names)):
            raise ValueError("activity catalog names must be unique")
        if any("{city}" not in entry.description for entry in entries):
            raise ValueError("every activity description must contain the {city} placeholder")
        for category in CATEGORIES:
            if len([entry for entry in entries if entry.category == category]) < 2:
                raise ValueError(f"activity catalog needs at least two {category} entries")

    async def get_initial_pairs(
        self,
        city: str,
        tags: tuple[str, ...],
    ) -> tuple[PreferencePageSuggestion, PreferencePageSuggestion, PreferencePageSuggestion]:
        ranked = self._local_rank(city, tags, (), ())
        chosen: list[Activity] = []
        category_order = self._stable_category_order(city, tags)
        for category in category_order:
            chosen.append(ranked[category][0])
        for category in category_order[:2]:
            chosen.append(ranked[category][1])

        # Mix categories in each comparison while keeping all four represented.
        pairs = ((chosen[0], chosen[1]), (chosen[2], chosen[3]), (chosen[4], chosen[5]))
        return tuple(PreferencePageSuggestion(pair) for pair in pairs)  # type: ignore[return-value]

    async def get_next_page(
        self,
        city: str,
        tags: tuple[str, ...],
        selected_activities: tuple[Activity, ...],
        rejected_activities: tuple[Activity, ...],
    ) -> PreferencePageSuggestion | None:
        answered_count = len(selected_activities) + len(rejected_activities)
        if answered_count >= 7:
            return None
        if answered_count < 6:
            raise ValueError("adaptive ranking requires all six initial responses")

        ranked = await self._rank_remaining(
            city,
            tags,
            selected_activities,
            rejected_activities,
        )
        categories = self._select_categories(selected_activities, rejected_activities)
        seen_names = {activity.name for activity in (*selected_activities, *rejected_activities)}
        suggestions = tuple(
            next(
                (activity for activity in ranked[category] if activity.name not in seen_names),
                None,
            )
            for category in categories
        )
        suggestions = tuple(activity for activity in suggestions if activity is not None)
        return PreferencePageSuggestion(suggestions) if suggestions else None

    async def update_learning_algorithm(
        self,
        selected_activities: tuple[Activity, ...],
        rejected_activities: tuple[Activity, ...],
    ) -> None:
        # This implementation learns online from the durable response snapshot and has no
        # separate mutable model to update at completion.
        del selected_activities, rejected_activities

    async def aclose(self) -> None:
        if self._openai is not None:
            await self._openai.close()

    async def _rank_remaining(
        self,
        city: str,
        tags: tuple[str, ...],
        selected: tuple[Activity, ...],
        rejected: tuple[Activity, ...],
    ) -> dict[ActivityCategory, list[Activity]]:
        full_ranking = self._local_rank(city, tags, selected, rejected)
        seen_names = {activity.name for activity in (*selected, *rejected)}
        fallback = {
            category: [activity for activity in activities if activity.name not in seen_names]
            for category, activities in full_ranking.items()
        }
        if self._openai is None or self._openai_model is None:
            return fallback

        candidates = {
            category: [activity.name for activity in activities]
            for category, activities in fallback.items()
        }
        try:
            response = await self._openai.responses.parse(
                model=self._openai_model,
                instructions=(
                    "Rank every candidate activity within its existing category for this traveler. "
                    "Use the city, initial tags, liked activities, and disliked activities only as "
                    "preference evidence. Return every supplied name exactly once, do not rename "
                    "activities, and do not move an activity to another category."
                ),
                input=json.dumps(
                    {
                        "city": city,
                        "tags": list(tags),
                        "liked": [activity.name for activity in selected],
                        "disliked": [activity.name for activity in rejected],
                        "candidates_by_category": candidates,
                    },
                    ensure_ascii=False,
                ),
                text_format=RankedActivities,
                max_output_tokens=1200,
                store=False,
            )
            parsed = response.output_parsed
            if parsed is None:
                return fallback
            return self._validated_model_rank(parsed, fallback, seen_names)
        except (
            RateLimitError,
            APITimeoutError,
            APIConnectionError,
            APIStatusError,
            ValidationError,
            ValueError,
        ) as exc:
            logger.warning(
                "Preference LLM ranking unavailable; using deterministic ranking (%s)",
                type(exc).__name__,
            )
            return fallback
        except Exception as exc:
            logger.warning(
                "Preference LLM ranking failed; using deterministic ranking (%s)",
                type(exc).__name__,
            )
            return fallback

    @staticmethod
    def _validated_model_rank(
        parsed: RankedActivities,
        fallback: dict[ActivityCategory, list[Activity]],
        seen_names: set[str],
    ) -> dict[ActivityCategory, list[Activity]]:
        by_name = {
            activity.name: activity
            for activities in fallback.values()
            for activity in activities
            if activity.name not in seen_names
        }
        output: dict[ActivityCategory, list[Activity]] = {category: [] for category in CATEGORIES}
        returned_categories: set[str] = set()
        for ranking in parsed.rankings:
            if ranking.category in returned_categories:
                raise ValueError("duplicate category ranking")
            returned_categories.add(ranking.category)
            expected = [
                activity.name
                for activity in fallback[ranking.category]
                if activity.name not in seen_names
            ]
            if sorted(ranking.activity_names) != sorted(expected):
                raise ValueError("ranked activity names do not match candidates")
            output[ranking.category] = [by_name[name] for name in ranking.activity_names]
        if returned_categories != set(CATEGORIES):
            raise ValueError("model did not rank every category")
        return output

    def _local_rank(
        self,
        city: str,
        tags: tuple[str, ...],
        selected: tuple[Activity, ...],
        rejected: tuple[Activity, ...],
    ) -> dict[ActivityCategory, list[Activity]]:
        preference_text = " ".join(
            [
                *tags,
                *(activity.name for activity in selected),
                *(activity.description for activity in selected),
            ]
        ).casefold()
        rejected_text = " ".join(
            [activity.name for activity in rejected]
            + [activity.description for activity in rejected]
        ).casefold()
        ranked: dict[ActivityCategory, list[tuple[int, str, Activity]]] = defaultdict(list)
        for entry in self._entries:
            signal_score = (
                sum(signal.casefold() in preference_text for signal in entry.signals) * 10
            )
            rejection_penalty = (
                sum(signal.casefold() in rejected_text for signal in entry.signals) * 3
            )
            stable_key = hashlib.sha256(
                f"{city.casefold()}|{'|'.join(tags).casefold()}|{entry.name}".encode()
            ).hexdigest()
            ranked[entry.category].append(
                (signal_score - rejection_penalty, stable_key, entry.activity_for(city))
            )
        return {
            category: [
                activity
                for _, _, activity in sorted(ranked[category], key=lambda row: (-row[0], row[1]))
            ]
            for category in CATEGORIES
        }

    @staticmethod
    def _select_categories(
        selected: tuple[Activity, ...],
        rejected: tuple[Activity, ...],
    ) -> tuple[ActivityCategory, ...]:
        likes = defaultdict(int)
        dislikes = defaultdict(int)
        for activity in selected:
            likes[activity.category] += 1
        for activity in rejected:
            dislikes[activity.category] += 1
        scores = {
            category: (1 + likes[category]) / (2 + likes[category] + dislikes[category])
            for category in CATEGORIES
        }
        ordered = sorted(
            CATEGORIES, key=lambda category: (-scores[category], CATEGORIES.index(category))
        )
        if likes[ordered[0]] > 0 and scores[ordered[0]] - scores[ordered[1]] >= 0.25:
            return (ordered[0],)
        return (ordered[0], ordered[1])

    @staticmethod
    def _stable_category_order(city: str, tags: tuple[str, ...]) -> tuple[ActivityCategory, ...]:
        return tuple(
            sorted(
                CATEGORIES,
                key=lambda category: hashlib.sha256(
                    f"{city.casefold()}|{'|'.join(tags).casefold()}|{category}".encode()
                ).hexdigest(),
            )
        )  # type: ignore[return-value]


def load_activity_catalog(path: Path = CATALOG_PATH) -> tuple[CatalogEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(CatalogEntry.model_validate(entry) for entry in payload)


def create_activity_recommendation_algorithm(settings: Settings) -> ActivityRecommendationAlgorithm:
    client = create_openai_client(settings) if settings.openai_configured else None
    return ActivityRecommendationAlgorithm(
        load_activity_catalog(),
        openai_client=client,
        openai_model=settings.openai_model if client is not None else None,
    )
