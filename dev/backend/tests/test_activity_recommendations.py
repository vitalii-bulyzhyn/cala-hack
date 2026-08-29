from types import SimpleNamespace

import pytest

from app.domain.preferences import Activity
from app.services.activity_recommendations import (
    CATEGORIES,
    ActivityRecommendationAlgorithm,
    load_activity_catalog,
)


def test_catalog_is_extendable_and_covers_every_learning_category() -> None:
    entries = load_activity_catalog()

    assert len(entries) >= 16
    assert {entry.category for entry in entries} == set(CATEGORIES)
    assert all("{city}" in entry.description for entry in entries)


@pytest.mark.asyncio
async def test_initial_retrieval_returns_three_unique_pairs_across_all_categories() -> None:
    algorithm = ActivityRecommendationAlgorithm(load_activity_catalog())

    pages = await algorithm.get_initial_pairs("Barcelona", ("art", "local cuisine"))
    activities = [activity for page in pages for activity in page.activities]

    assert [len(page.activities) for page in pages] == [2, 2, 2]
    assert len({activity.name for activity in activities}) == 6
    assert {activity.category for activity in activities} == set(CATEGORIES)
    assert all("Barcelona" in activity.description for activity in activities)


@pytest.mark.asyncio
async def test_adaptive_page_selects_top_unseen_items_then_stops() -> None:
    algorithm = ActivityRecommendationAlgorithm(load_activity_catalog())
    pages = await algorithm.get_initial_pairs("Barcelona", ("art",))
    initial = tuple(activity for page in pages for activity in page.activities)
    selected = (initial[0], initial[2], initial[4])
    rejected = (initial[1], initial[3], initial[5])

    adaptive = await algorithm.get_next_page(
        "Barcelona",
        ("art",),
        selected,
        rejected,
    )

    assert adaptive is not None
    assert len(adaptive.activities) in {1, 2}
    assert not {activity.name for activity in adaptive.activities} & {
        activity.name for activity in initial
    }

    final_selected = (*selected, adaptive.activities[0])
    assert (
        await algorithm.get_next_page(
            "Barcelona",
            ("art",),
            final_selected,
            rejected,
        )
        is None
    )


@pytest.mark.asyncio
async def test_llm_ranking_receives_choices_and_controls_the_adaptive_pick() -> None:
    entries = load_activity_catalog()
    local_algorithm = ActivityRecommendationAlgorithm(entries)
    initial_pages = await local_algorithm.get_initial_pairs("Barcelona", ("art",))
    initial = tuple(activity for page in initial_pages for activity in page.activities)
    selected = (initial[0], initial[2], initial[4])
    rejected = (initial[1], initial[3], initial[5])
    fallback = local_algorithm._local_rank("Barcelona", ("art",), selected, rejected)
    seen = {activity.name for activity in initial}
    rankings = [
        SimpleNamespace(
            category=category,
            activity_names=[
                activity.name
                for activity in reversed(fallback[category])
                if activity.name not in seen
            ],
        )
        for category in CATEGORIES
    ]

    class FakeResponses:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def parse(self, **kwargs):  # type: ignore[no-untyped-def]
            self.calls.append(kwargs)
            return SimpleNamespace(output_parsed=SimpleNamespace(rankings=rankings))

    responses = FakeResponses()
    openai = SimpleNamespace(responses=responses)
    algorithm = ActivityRecommendationAlgorithm(
        entries,
        openai_client=openai,  # type: ignore[arg-type]
        openai_model="test-model",
    )

    adaptive = await algorithm.get_next_page("Barcelona", ("art",), selected, rejected)

    assert adaptive is not None
    assert len(responses.calls) == 1
    request = responses.calls[0]
    assert request["store"] is False
    assert request["text_format"].__name__ == "RankedActivities"  # type: ignore[union-attr]
    selected_categories = algorithm._select_categories(selected, rejected)
    assert [activity.name for activity in adaptive.activities] == [
        next(
            activity.name for activity in reversed(fallback[category]) if activity.name not in seen
        )
        for category in selected_categories
    ]


def test_category_learner_can_select_one_clear_winner() -> None:
    likes = tuple(
        Activity(
            name=f"Culture {index}",
            category="culture",
            description="A cultural activity.",
            image_link=f"https://images.example/culture-{index}.jpg",
        )
        for index in range(3)
    )
    dislikes = tuple(
        Activity(
            name=f"Nature {index}",
            category="nature",
            description="An outdoor activity.",
            image_link=f"https://images.example/nature-{index}.jpg",
        )
        for index in range(3)
    )

    assert ActivityRecommendationAlgorithm._select_categories(likes, dislikes) == ("culture",)
