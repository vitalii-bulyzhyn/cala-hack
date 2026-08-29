from datetime import time, timedelta
from pathlib import Path
from urllib.parse import urlencode

from app.domain.itineraries import ItineraryStatus, MediaRole, MediaStatus
from app.domain.preferences import Activity
from app.integrations.media_storage import LocalMediaStore, MediaStorageError
from app.services.content_generation import (
    GeneratedMediaAsset,
    GeneratedStop,
    GenerationCheckpoint,
    GenerationCompletion,
    GenerationTask,
    ContentGenerationFailure,
    generated_image_id,
)

DEMO_ASSET_PATH = Path(__file__).resolve().parents[1] / "data" / "demo-journal-page.jpg"
DEMO_SCHEDULE = (
    (time(9), time(10, 30)),
    (time(12), time(13, 30)),
    (time(15, 30), time(17)),
    (time(18, 30), time(20)),
)


class DemoContentGenerationPipeline:
    """Create a complete deterministic journal without contacting external providers."""

    def __init__(
        self,
        *,
        image_public_path: Path,
        max_bytes: int = 15_000_000,
        max_pixels: int = 20_000_000,
        asset_path: Path = DEMO_ASSET_PATH,
    ) -> None:
        self._image_public_path = image_public_path.resolve()
        self._max_bytes = max_bytes
        self._max_pixels = max_pixels
        self._asset_path = asset_path.resolve()

    async def generate(
        self,
        task: GenerationTask,
        checkpoint: GenerationCheckpoint,
    ) -> GenerationCompletion:
        del checkpoint
        image_id = generated_image_id(task.run_id, MediaRole.HERO)
        try:
            async with LocalMediaStore(
                root=self._image_public_path,
                timeout_seconds=30,
                max_bytes=self._max_bytes,
                max_pixels=self._max_pixels,
            ) as media_store:
                stored = await media_store.copy_from_local(
                    source_path=self._asset_path,
                    image_id=image_id,
                )
        except MediaStorageError as exc:
            raise ContentGenerationFailure(
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
            ) from exc

        activities = self._demo_activities(task)
        stops = tuple(
            GeneratedStop(
                position=position,
                start_time=DEMO_SCHEDULE[position - 1][0],
                end_time=DEMO_SCHEDULE[position - 1][1],
                name=activity.name,
                category=activity.category,
                description=activity.description,
                reason_to_visit=(
                    "Included because your activity choices pointed toward this kind of experience."
                ),
                links=(
                    {
                        "kind": "map",
                        "label": "Explore nearby in maps",
                        "url": "https://www.google.com/maps/search/?"
                        + urlencode(
                            {
                                "api": "1",
                                "query": f"{activity.name}, {task.city}",
                            }
                        ),
                    },
                ),
            )
            for position, activity in enumerate(activities, start=1)
        )
        preference_copy = ", ".join(task.tags[:4]) or "your visual choices"
        return GenerationCompletion(
            final_status=ItineraryStatus.READY,
            destination=task.city,
            planned_date=task.reference_date + timedelta(days=7),
            destination_timezone="UTC",
            title=f"A demo day in {task.city}",
            summary=(
                f"An offline sample journal shaped by {preference_copy}. "
                "The activities and map searches are illustrative so the complete product flow "
                "can be tested without provider credentials."
            ),
            stops=stops,
            media_assets=(
                GeneratedMediaAsset(
                    id=image_id,
                    role=MediaRole.HERO,
                    status=MediaStatus.READY,
                    provider="local-demo",
                    provider_request_id=f"demo-{task.run_id.hex}",
                    attempt_count=task.attempt_count,
                    url=stored.public_url,
                    storage_key=stored.storage_key,
                    content_type=stored.content_type,
                    width=stored.width,
                    height=stored.height,
                    alt_text=f"Textured paper page for an offline demo journal about {task.city}.",
                    model_id="deterministic-demo-v1",
                    prompt_version="offline-demo-v1",
                ),
            ),
        )

    @staticmethod
    def _demo_activities(task: GenerationTask) -> tuple[Activity, ...]:
        selected = list(task.selected_activities[:4])
        defaults = (
            Activity(
                name="A relaxed neighborhood walk",
                category="culture",
                description=(
                    f"Notice the streets, public spaces, and everyday details of {task.city}."
                ),
                image_link="https://images.example/demo-walk.jpg",
            ),
            Activity(
                name="A local food pause",
                category="food",
                description=f"Make time for a flexible, locally inspired meal in {task.city}.",
                image_link="https://images.example/demo-food.jpg",
            ),
            Activity(
                name="A scenic outdoor break",
                category="nature",
                description=f"Slow down in an open-air part of {task.city}.",
                image_link="https://images.example/demo-nature.jpg",
            ),
        )
        known_names = {activity.name for activity in selected}
        for fallback in defaults:
            if len(selected) >= 3:
                break
            if fallback.name not in known_names:
                selected.append(fallback)
                known_names.add(fallback.name)
        return tuple(selected)
