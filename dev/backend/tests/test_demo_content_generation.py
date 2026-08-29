from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.domain.itineraries import ItineraryStatus, MediaRole, MediaStatus
from app.domain.preferences import Activity
from app.repositories.generation_runs import GenerationRunStore
from app.services.content_generation import GenerationTask, UnconfiguredContentGenerationPipeline
from app.services.demo_content_generation import DemoContentGenerationPipeline
from app.services.provider_content_generation import create_content_generation_pipeline


@pytest.mark.asyncio
async def test_demo_pipeline_creates_a_complete_owned_journal(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"\xff\xd8\xffdemo-jpeg")
    itinerary_id = uuid4()
    task = GenerationTask(
        run_id=uuid4(),
        itinerary_id=itinerary_id,
        attempt_count=1,
        city="Barcelona",
        tags=("art", "local food"),
        reference_date=date(2026, 8, 29),
        selected_activities=(
            Activity(
                name="Independent gallery trail",
                category="culture",
                description="Move between small galleries in Barcelona.",
                image_link="https://images.example/gallery.jpg",
            ),
        ),
    )
    pipeline = DemoContentGenerationPipeline(
        media_root=tmp_path / "media",
        media_url_path="/media",
        asset_path=source,
    )

    completion = await pipeline.generate(task, SimpleNamespace())  # type: ignore[arg-type]

    assert completion.final_status == ItineraryStatus.READY
    assert completion.planned_date == date(2026, 9, 5)
    assert completion.destination_timezone == "UTC"
    assert len(completion.stops) == 3
    assert completion.stops[0].name == "Independent gallery trail"
    assert all(stop.links[0]["kind"] == "map" for stop in completion.stops)
    assert completion.media_assets[0].role == MediaRole.HERO
    assert completion.media_assets[0].status == MediaStatus.READY
    stored_journal = tmp_path / "media" / str(itinerary_id) / "journal.jpg"
    assert stored_journal.read_bytes() == source.read_bytes()
    GenerationRunStore._validate_completion(completion)


def test_pipeline_factory_uses_demo_without_provider_keys(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key=None,
        cala_api_key=None,
        fal_key=None,
        media_storage_path=tmp_path,
    )

    assert isinstance(create_content_generation_pipeline(settings), DemoContentGenerationPipeline)

    disabled = settings.model_copy(update={"offline_demo_enabled": False})
    assert isinstance(
        create_content_generation_pipeline(disabled),
        UnconfiguredContentGenerationPipeline,
    )
