from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.dependencies import get_preference_learning_service
from app.core.errors import PreferenceEngineUnavailableError
from app.db.models import GenerationRun, PreferenceItem, PreferencePage, PreferenceResponse
from app.domain.itineraries import ItineraryStatus
from app.domain.preferences import (
    Activity,
    PreferenceDecision,
    PreferenceLearningStatus,
    PreferencePageLayout,
    PreferencePageSource,
    PreferencePageSuggestion,
)
from app.main import create_app
from app.repositories.preference_learning import (
    CompletedPreferenceLearning,
    PreferenceLearningRepository,
    PreferenceLearningSnapshot,
)
from app.services.preference_learning import (
    PreferenceLearningService,
    UnconfiguredPreferenceLearningAlgorithm,
)
from app.services.readiness import ReadinessChecker


def activity(number: int) -> Activity:
    return Activity(
        name=f"Activity {number}",
        category="culture",
        description=f"Description for activity {number}.",
        image_link=f"https://images.example/activity-{number}.jpg",
    )


def suggestion(*numbers: int) -> PreferencePageSuggestion:
    return PreferencePageSuggestion(tuple(activity(number) for number in numbers))


def test_activity_contract_requires_display_copy_and_an_http_image_link() -> None:
    assert activity(1).image_link == "https://images.example/activity-1.jpg"
    with pytest.raises(ValueError):
        Activity(
            name="Choice",
            category="culture",
            description="Description",
            image_link="not-a-url",
        )


@pytest.mark.parametrize("count", [0, 3])
def test_page_suggestion_requires_single_or_pair_layout(count: int) -> None:
    with pytest.raises(ValueError, match="one or two"):
        PreferencePageSuggestion(tuple(activity(number) for number in range(count)))


def page(
    itinerary_id: UUID,
    position: int,
    *numbers: int,
    decisions: tuple[PreferenceDecision | None, ...] | None = None,
) -> PreferencePage:
    page_id = uuid4()
    choices = decisions or tuple(None for _ in numbers)
    entries = []
    numbered_choices = enumerate(zip(numbers, choices, strict=True), start=1)
    for entry_position, (number, decision) in numbered_choices:
        item = PreferenceItem(
            id=uuid4(),
            itinerary_id=itinerary_id,
            page_id=page_id,
            position=entry_position,
            name=f"Activity {number}",
            category="culture",
            description=f"Description for activity {number}.",
            image_link=f"https://images.example/activity-{number}.jpg",
        )
        item.response = (
            PreferenceResponse(
                id=uuid4(),
                itinerary_id=itinerary_id,
                item_id=item.id,
                decision=decision,
            )
            if decision is not None
            else None
        )
        entries.append(item)
    return PreferencePage(
        id=page_id,
        itinerary_id=itinerary_id,
        position=position,
        layout=(PreferencePageLayout.SINGLE if len(entries) == 1 else PreferencePageLayout.PAIR),
        source=(PreferencePageSource.INITIAL if position <= 3 else PreferencePageSource.ADAPTIVE),
        entries=entries,
    )


class FakeAlgorithm:
    version = "fake-v1"

    def __init__(self) -> None:
        self.initial = AsyncMock(
            return_value=(suggestion(1, 2), suggestion(3, 4), suggestion(5, 6))
        )
        self.next = AsyncMock(return_value=suggestion(7))
        self.update = AsyncMock(return_value=None)

    async def get_initial_pairs(self, city: str, tags: tuple[str, ...]):
        return await self.initial(city, tags)

    async def get_next_page(self, city, tags, selected, rejected):  # type: ignore[no-untyped-def]
        return await self.next(city, tags, selected, rejected)

    async def update_learning_algorithm(self, selected, rejected):  # type: ignore[no-untyped-def]
        return await self.update(selected, rejected)


class RecordingQueue:
    def __init__(self) -> None:
        self.run_ids: list[UUID] = []

    async def enqueue(self, run_id: UUID) -> None:
        self.run_ids.append(run_id)


def snapshot(
    itinerary_id: UUID,
    pages: tuple[PreferencePage, ...] = (),
    *,
    status: PreferenceLearningStatus = PreferenceLearningStatus.COLLECTING,
) -> PreferenceLearningSnapshot:
    return PreferenceLearningSnapshot(
        itinerary_id=itinerary_id,
        city="Barcelona",
        tags=("art", "food"),
        status=status,
        pages=pages,
    )


@pytest.mark.asyncio
async def test_first_next_page_generates_and_persists_three_initial_pairs() -> None:
    itinerary_id = uuid4()
    persisted = page(itinerary_id, 1, 1, 2)
    repository = SimpleNamespace(
        get_snapshot=AsyncMock(return_value=snapshot(itinerary_id)),
        add_initial_pages_if_empty=AsyncMock(return_value=persisted),
    )
    algorithm = FakeAlgorithm()
    service = PreferenceLearningService(
        repository,  # type: ignore[arg-type]
        algorithm,
        RecordingQueue(),
        generation_max_attempts=3,
    )

    result = await service.get_next_page(itinerary_id)

    assert result is persisted
    algorithm.initial.assert_awaited_once_with("Barcelona", ("art", "food"))
    saved = repository.add_initial_pages_if_empty.await_args.args[1]
    assert [len(candidate.activities) for candidate in saved] == [2, 2, 2]


@pytest.mark.asyncio
async def test_default_blank_algorithm_reports_an_explicit_unconfigured_error() -> None:
    itinerary_id = uuid4()
    repository = SimpleNamespace(get_snapshot=AsyncMock(return_value=snapshot(itinerary_id)))
    service = PreferenceLearningService(
        repository,  # type: ignore[arg-type]
        UnconfiguredPreferenceLearningAlgorithm(),
        RecordingQueue(),
        generation_max_attempts=3,
    )

    with pytest.raises(PreferenceEngineUnavailableError):
        await service.get_next_page(itinerary_id)


@pytest.mark.asyncio
async def test_existing_unanswered_page_is_replayed_without_algorithm_call() -> None:
    itinerary_id = uuid4()
    current = page(itinerary_id, 2, 3, 4)
    repository = SimpleNamespace(
        get_snapshot=AsyncMock(return_value=snapshot(itinerary_id, (current,)))
    )
    algorithm = FakeAlgorithm()
    service = PreferenceLearningService(
        repository,  # type: ignore[arg-type]
        algorithm,
        RecordingQueue(),
        generation_max_attempts=3,
    )

    assert await service.get_next_page(itinerary_id) is current
    algorithm.initial.assert_not_awaited()
    algorithm.next.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_pages_returns_every_issued_page_without_advancing_learning() -> None:
    itinerary_id = uuid4()
    issued = (
        page(
            itinerary_id,
            1,
            1,
            2,
            decisions=(PreferenceDecision.LIKE, PreferenceDecision.DISLIKE),
        ),
        page(
            itinerary_id,
            2,
            3,
            4,
            decisions=(PreferenceDecision.DISLIKE, PreferenceDecision.LIKE),
        ),
        page(
            itinerary_id,
            3,
            5,
            6,
            decisions=(PreferenceDecision.LIKE, PreferenceDecision.DISLIKE),
        ),
        page(
            itinerary_id,
            4,
            7,
            decisions=(PreferenceDecision.LIKE,),
        ),
    )
    repository = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=snapshot(
                itinerary_id,
                issued,
                status=PreferenceLearningStatus.COMPLETED,
            )
        )
    )
    algorithm = FakeAlgorithm()
    service = PreferenceLearningService(
        repository,  # type: ignore[arg-type]
        algorithm,
        RecordingQueue(),
        generation_max_attempts=3,
    )

    result = await service.list_pages(itinerary_id)

    assert result == issued
    repository.get_snapshot.assert_awaited_once_with(itinerary_id)
    algorithm.initial.assert_not_awaited()
    algorithm.next.assert_not_awaited()
    algorithm.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_after_answered_pages_algorithm_can_add_single_adaptive_page() -> None:
    itinerary_id = uuid4()
    answered = (
        page(
            itinerary_id,
            1,
            1,
            2,
            decisions=(PreferenceDecision.LIKE, PreferenceDecision.DISLIKE),
        ),
        page(
            itinerary_id,
            2,
            3,
            4,
            decisions=(PreferenceDecision.LIKE, PreferenceDecision.DISLIKE),
        ),
        page(
            itinerary_id,
            3,
            5,
            6,
            decisions=(PreferenceDecision.LIKE, PreferenceDecision.DISLIKE),
        ),
    )
    adaptive = page(itinerary_id, 4, 7)
    repository = SimpleNamespace(
        get_snapshot=AsyncMock(return_value=snapshot(itinerary_id, answered)),
        add_adaptive_page=AsyncMock(return_value=adaptive),
    )
    algorithm = FakeAlgorithm()
    service = PreferenceLearningService(
        repository,  # type: ignore[arg-type]
        algorithm,
        RecordingQueue(),
        generation_max_attempts=3,
    )

    result = await service.get_next_page(itinerary_id)

    assert result is adaptive
    city, tags, selected, rejected = algorithm.next.await_args.args
    assert city == "Barcelona"
    assert tags == ("art", "food")
    assert [entry.name for entry in selected] == ["Activity 1", "Activity 3", "Activity 5"]
    assert [entry.name for entry in rejected] == ["Activity 2", "Activity 4", "Activity 6"]


@pytest.mark.asyncio
async def test_completion_updates_algorithm_creates_run_and_notifies_worker() -> None:
    itinerary_id = uuid4()
    run_id = uuid4()
    answered = (
        *(
            page(
                itinerary_id,
                position,
                first,
                second,
                decisions=(PreferenceDecision.LIKE, PreferenceDecision.DISLIKE),
            )
            for position, (first, second) in enumerate(((1, 2), (3, 4), (5, 6)), start=1)
        ),
        page(
            itinerary_id,
            4,
            7,
            decisions=(PreferenceDecision.LIKE,),
        ),
    )
    repository = SimpleNamespace(
        get_snapshot=AsyncMock(return_value=snapshot(itinerary_id, answered)),
        complete=AsyncMock(
            return_value=CompletedPreferenceLearning(
                itinerary_id=itinerary_id,
                generation_run_id=run_id,
                replayed=False,
            )
        ),
    )
    queue = RecordingQueue()
    algorithm = FakeAlgorithm()
    service = PreferenceLearningService(
        repository,  # type: ignore[arg-type]
        algorithm,
        queue,
        generation_max_attempts=4,
    )

    completed = await service.complete(itinerary_id)

    assert completed.generation_run_id == run_id
    assert queue.run_ids == [run_id]
    repository.complete.assert_awaited_once_with(
        itinerary_id,
        algorithm_version="fake-v1",
        max_attempts=4,
    )
    selected, rejected = algorithm.update.await_args.args
    assert len(selected) == 4
    assert len(rejected) == 3


@pytest.mark.asyncio
async def test_completion_allows_all_issued_items_to_remain_unanswered() -> None:
    itinerary_id = uuid4()
    run_id = uuid4()
    issued = tuple(
        page(itinerary_id, position, first, second)
        for position, (first, second) in enumerate(((1, 2), (3, 4), (5, 6)), start=1)
    )
    repository = SimpleNamespace(
        get_snapshot=AsyncMock(return_value=snapshot(itinerary_id, issued)),
        complete=AsyncMock(
            return_value=CompletedPreferenceLearning(
                itinerary_id=itinerary_id,
                generation_run_id=run_id,
                replayed=False,
            )
        ),
    )
    queue = RecordingQueue()
    algorithm = FakeAlgorithm()
    service = PreferenceLearningService(
        repository,  # type: ignore[arg-type]
        algorithm,
        queue,
        generation_max_attempts=3,
    )

    completed = await service.complete(itinerary_id)

    assert completed.generation_run_id == run_id
    assert queue.run_ids == [run_id]
    algorithm.update.assert_awaited_once_with((), ())
    repository.complete.assert_awaited_once_with(
        itinerary_id,
        algorithm_version="fake-v1",
        max_attempts=3,
    )


@pytest.mark.asyncio
async def test_completion_treats_unanswered_items_as_neutral() -> None:
    itinerary_id = uuid4()
    run_id = uuid4()
    issued = (
        page(
            itinerary_id,
            1,
            1,
            2,
            decisions=(PreferenceDecision.LIKE, None),
        ),
        page(
            itinerary_id,
            2,
            3,
            4,
            decisions=(None, PreferenceDecision.DISLIKE),
        ),
        page(itinerary_id, 3, 5, 6),
    )
    repository = SimpleNamespace(
        get_snapshot=AsyncMock(return_value=snapshot(itinerary_id, issued)),
        complete=AsyncMock(
            return_value=CompletedPreferenceLearning(
                itinerary_id=itinerary_id,
                generation_run_id=run_id,
                replayed=False,
            )
        ),
    )
    algorithm = FakeAlgorithm()
    service = PreferenceLearningService(
        repository,  # type: ignore[arg-type]
        algorithm,
        RecordingQueue(),
        generation_max_attempts=3,
    )

    await service.complete(itinerary_id)

    selected, rejected = algorithm.update.await_args.args
    assert [entry.name for entry in selected] == ["Activity 1"]
    assert [entry.name for entry in rejected] == ["Activity 4"]


@pytest.mark.asyncio
async def test_repository_completion_has_no_response_or_adaptive_page_gate() -> None:
    itinerary_id = uuid4()
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    learning = SimpleNamespace(
        status=PreferenceLearningStatus.COLLECTING,
        algorithm_version=None,
        completed_at=None,
    )
    itinerary = SimpleNamespace(
        status=ItineraryStatus.LEARNING_PREFERENCES,
        status_changed_at=None,
        state_version=0,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[itinerary, now]),
        add=Mock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    repository = PreferenceLearningRepository(session)  # type: ignore[arg-type]
    repository._locked_learning = AsyncMock(return_value=learning)  # type: ignore[method-assign]

    completed = await repository.complete(
        itinerary_id,
        algorithm_version="fake-v1",
        max_attempts=3,
    )

    assert completed.itinerary_id == itinerary_id
    assert completed.replayed is False
    assert learning.status == PreferenceLearningStatus.COMPLETED
    assert learning.algorithm_version == "fake-v1"
    assert learning.completed_at == now
    assert itinerary.status == ItineraryStatus.QUEUED
    assert itinerary.status_changed_at == now
    assert itinerary.state_version == 1
    run = session.add.call_args.args[0]
    assert isinstance(run, GenerationRun)
    assert run.id == completed.generation_run_id
    assert run.itinerary_id == itinerary_id
    assert run.dedupe_key == f"itinerary:{itinerary_id}:orchestration:v4"
    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()


@contextmanager
def preference_client(
    settings: Settings,
    healthy_checker: ReadinessChecker,
    service: object,
) -> Iterator[TestClient]:
    application = create_app(settings, healthy_checker)

    def override_service() -> object:
        return service

    application.dependency_overrides[get_preference_learning_service] = override_service
    with TestClient(application) as test_client:
        yield test_client


def test_preference_page_api_returns_layout_and_json_entries(
    settings: Settings,
    healthy_checker: ReadinessChecker,
) -> None:
    itinerary_id = uuid4()
    returned_page = page(itinerary_id, 1, 1, 2)
    returned_page.entries[0].response = PreferenceResponse(
        id=uuid4(),
        itinerary_id=itinerary_id,
        item_id=returned_page.entries[0].id,
        decision=PreferenceDecision.LIKE,
    )
    service = SimpleNamespace(get_next_page=AsyncMock(return_value=returned_page))

    with preference_client(settings, healthy_checker, service) as client:
        response = client.get(f"/api/v1/itineraries/{itinerary_id}/preference-pages/next")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(returned_page.id),
        "position": 1,
        "layout": "pair",
        "source": "initial",
        "entries": [
            {
                "id": str(entry.id),
                "name": entry.name,
                "category": "culture",
                "description": entry.description,
                "image_link": entry.image_link,
                "decision": "like" if entry.position == 1 else None,
            }
            for entry in returned_page.entries
        ],
    }
    assert response.headers["cache-control"] == "no-store"


def test_preference_pages_api_lists_all_issued_pages_in_order(
    settings: Settings,
    healthy_checker: ReadinessChecker,
) -> None:
    itinerary_id = uuid4()
    returned_pages = [
        page(itinerary_id, 1, 1, 2),
        page(itinerary_id, 2, 3, 4),
        page(itinerary_id, 3, 5, 6),
    ]
    returned_pages[1].entries[0].response = PreferenceResponse(
        id=uuid4(),
        itinerary_id=itinerary_id,
        item_id=returned_pages[1].entries[0].id,
        decision=PreferenceDecision.DISLIKE,
    )
    service = SimpleNamespace(list_pages=AsyncMock(return_value=tuple(returned_pages)))

    with preference_client(settings, healthy_checker, service) as client:
        response = client.get(f"/api/v1/itineraries/{itinerary_id}/preference-pages")

    assert response.status_code == 200
    assert [candidate["position"] for candidate in response.json()] == [1, 2, 3]
    assert [len(candidate["entries"]) for candidate in response.json()] == [2, 2, 2]
    assert response.json()[1]["entries"][0]["decision"] == "dislike"
    assert response.headers["cache-control"] == "no-store"
    service.list_pages.assert_awaited_once_with(itinerary_id)


def test_preference_pages_api_returns_an_empty_list_before_issuance(
    settings: Settings,
    healthy_checker: ReadinessChecker,
) -> None:
    itinerary_id = uuid4()
    service = SimpleNamespace(list_pages=AsyncMock(return_value=()))

    with preference_client(settings, healthy_checker, service) as client:
        response = client.get(f"/api/v1/itineraries/{itinerary_id}/preference-pages")

    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["cache-control"] == "no-store"


def test_preference_decision_api_records_like_or_dislike(
    settings: Settings,
    healthy_checker: ReadinessChecker,
) -> None:
    itinerary_id = uuid4()
    item_id = uuid4()
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    stored = PreferenceResponse(
        id=uuid4(),
        itinerary_id=itinerary_id,
        item_id=item_id,
        decision=PreferenceDecision.LIKE,
        created_at=now,
        updated_at=now,
    )
    service = SimpleNamespace(
        record_response=AsyncMock(return_value=SimpleNamespace(response=stored))
    )

    with preference_client(settings, healthy_checker, service) as client:
        response = client.put(
            f"/api/v1/itineraries/{itinerary_id}/preference-items/{item_id}/response",
            json={"decision": "like"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "itinerary_id": str(itinerary_id),
        "item_id": str(item_id),
        "decision": "like",
        "recorded_at": "2026-08-29T12:00:00Z",
    }
    service.record_response.assert_awaited_once_with(
        itinerary_id,
        item_id,
        PreferenceDecision.LIKE,
    )


def test_preference_complete_api_returns_worker_poll_resource(
    settings: Settings,
    healthy_checker: ReadinessChecker,
) -> None:
    itinerary_id = uuid4()
    completed = CompletedPreferenceLearning(
        itinerary_id=itinerary_id,
        generation_run_id=uuid4(),
        replayed=False,
    )
    service = SimpleNamespace(complete=AsyncMock(return_value=completed))

    with preference_client(settings, healthy_checker, service) as client:
        response = client.post(f"/api/v1/itineraries/{itinerary_id}/preference-learning/complete")

    status_url = f"/api/v1/itineraries/{itinerary_id}"
    assert response.status_code == 202
    assert response.json() == {
        "id": str(itinerary_id),
        "status": "pending",
        "status_url": status_url,
    }
    assert response.headers["location"] == status_url
    assert response.headers["retry-after"] == str(settings.worker_poll_seconds)


def test_no_next_preference_page_returns_204(
    settings: Settings,
    healthy_checker: ReadinessChecker,
) -> None:
    itinerary_id = uuid4()
    service = SimpleNamespace(get_next_page=AsyncMock(return_value=None))

    with preference_client(settings, healthy_checker, service) as client:
        response = client.get(f"/api/v1/itineraries/{itinerary_id}/preference-pages/next")

    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["cache-control"] == "no-store"


def test_invalid_preference_decision_is_rejected_before_service(
    settings: Settings,
    healthy_checker: ReadinessChecker,
) -> None:
    itinerary_id = uuid4()
    item_id = uuid4()
    service = SimpleNamespace(record_response=AsyncMock())

    with preference_client(settings, healthy_checker, service) as client:
        response = client.put(
            f"/api/v1/itineraries/{itinerary_id}/preference-items/{item_id}/response",
            json={"decision": "maybe"},
        )

    assert response.status_code == 422
    service.record_response.assert_not_awaited()
