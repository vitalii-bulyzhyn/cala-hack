import json
from types import SimpleNamespace

import pytest

from app.domain.preferences import BanditArm, PreferenceAlgorithmState
from app.services.activity_recommendations import (
    CATEGORIES,
    ActivityRecommendationAlgorithm,
    UnsupportedJournalCityError,
    load_city_journal_inventories,
)


class PredictableRandom:
    def __init__(self, samples: dict[tuple[float, float], float], page_size_roll: float) -> None:
        self.samples = samples
        self.page_size_roll = page_size_roll

    def betavariate(self, alpha: float, beta: float) -> float:
        return self.samples.get((alpha, beta), alpha / (alpha + beta))

    def random(self) -> float:
        return self.page_size_roll


def test_city_journal_inventories_are_authoritative_and_cover_every_category() -> None:
    inventories = load_city_journal_inventories()

    assert set(inventories) == {"barcelona", "toulouse", "valencia"}
    assert all(len(inventory.entries) >= 23 for inventory in inventories.values())
    assert all(
        {entry.categories[0] for entry in inventory.entries} == set(CATEGORIES)
        for inventory in inventories.values()
    )


@pytest.mark.asyncio
async def test_initial_retrieval_returns_three_unique_pairs_across_all_categories() -> None:
    algorithm = ActivityRecommendationAlgorithm(
        load_city_journal_inventories(),
        random_source=PredictableRandom({}, 0.5),
    )

    pages = await algorithm.get_initial_pairs("Barcelona", ("art", "local cuisine"))
    activities = [activity for page in pages for activity in page.activities]

    assert [len(page.activities) for page in pages] == [2, 2, 2]
    assert len({activity.name for activity in activities}) == 6
    assert {activity.category for activity in activities} == set(CATEGORIES)
    assert all(activity.description for activity in activities)
    assert all(
        activity.image_link == f"/{activity.cala_entity_id}.png"
        if activity.cala_entity_id is not None
        else activity.image_link is None
        for activity in activities
    )
    assert any(activity.cala_entity_id for activity in activities)


@pytest.mark.asyncio
async def test_llm_selects_the_six_initial_articles_and_pair_order() -> None:
    inventories = load_city_journal_inventories()
    entries = inventories["barcelona"].entries
    first_by_category = {
        category: next(entry for entry in entries if entry.categories == [category])
        for category in CATEGORIES
    }
    additional = [
        entry
        for entry in entries
        if entry.name not in {selected.name for selected in first_by_category.values()}
    ][:2]
    selected_names = [
        first_by_category["culture"].name,
        first_by_category["food"].name,
        first_by_category["outdoors"].name,
        first_by_category["neighbourhoods"].name,
        additional[0].name,
        additional[1].name,
    ]

    class FakeResponses:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def parse(self, **kwargs):  # type: ignore[no-untyped-def]
            self.calls.append(kwargs)
            return SimpleNamespace(
                output_parsed=SimpleNamespace(activity_names=selected_names)
            )

    responses = FakeResponses()
    algorithm = ActivityRecommendationAlgorithm(
        inventories,
        openai_client=SimpleNamespace(responses=responses),  # type: ignore[arg-type]
        openai_model="test-model",
    )

    pages = await algorithm.get_initial_pairs("Barcelona", ("art", "food"))

    assert [activity.name for page in pages for activity in page.activities] == selected_names
    assert len(responses.calls) == 1
    request = responses.calls[0]
    assert request["store"] is False
    assert request["text_format"].__name__ == "InitialActivitySelection"  # type: ignore[union-attr]
    payload = json.loads(request["input"])  # type: ignore[arg-type]
    assert payload["city"] == "Barcelona"
    assert payload["tags"] == ["art", "food"]
    assert len(payload["candidates"]) == len(entries)
    assert all(candidate["journal_entry"] for candidate in payload["candidates"])


@pytest.mark.asyncio
async def test_invalid_llm_initial_selection_falls_back_locally() -> None:
    inventories = load_city_journal_inventories()

    class FakeResponses:
        async def parse(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            return SimpleNamespace(
                output_parsed=SimpleNamespace(activity_names=["unknown"] * 6)
            )

    local = ActivityRecommendationAlgorithm(inventories)
    expected = await local.get_initial_pairs("Barcelona", ("art",))
    algorithm = ActivityRecommendationAlgorithm(
        inventories,
        openai_client=SimpleNamespace(responses=FakeResponses()),  # type: ignore[arg-type]
        openai_model="test-model",
    )

    actual = await algorithm.get_initial_pairs("Barcelona", ("art",))

    assert actual == expected


@pytest.mark.asyncio
async def test_adaptive_pages_continue_selecting_unseen_items() -> None:
    algorithm = ActivityRecommendationAlgorithm(load_city_journal_inventories())
    pages = await algorithm.get_initial_pairs("Barcelona", ("art",))
    initial = tuple(activity for page in pages for activity in page.activities)
    selected = (initial[0], initial[2], initial[4])
    rejected = (initial[1], initial[3], initial[5])

    adaptive = await algorithm.get_next_page(
        "Barcelona",
        ("art",),
        initial,
        selected,
        rejected,
        PreferenceAlgorithmState.priors(),
    )

    assert adaptive is not None
    assert len(adaptive.activities) in {1, 2}
    assert not {activity.name for activity in adaptive.activities} & {
        activity.name for activity in initial
    }

    final_selected = (*selected, adaptive.activities[0])
    following = await algorithm.get_next_page(
        "Barcelona",
        ("art",),
        (*initial, *adaptive.activities),
        final_selected,
        rejected,
        PreferenceAlgorithmState.priors(),
    )
    assert following is not None
    assert not {activity.name for activity in following.activities} & {
        activity.name for activity in (*initial, *adaptive.activities)
    }


@pytest.mark.asyncio
async def test_adaptive_page_uses_thompson_priors_without_any_ratings() -> None:
    algorithm = ActivityRecommendationAlgorithm(
        load_city_journal_inventories(),
        random_source=PredictableRandom({}, 0.5),
    )
    pages = await algorithm.get_initial_pairs("Barcelona", ("art",))
    initial = tuple(activity for page in pages for activity in page.activities)

    adaptive = await algorithm.get_next_page(
        "Barcelona",
        ("art",),
        initial,
        (),
        (),
        PreferenceAlgorithmState.priors(),
    )

    assert adaptive is not None
    assert len(adaptive.activities) == 1
    assert adaptive.activities[0].category == "food"
    assert adaptive.activities[0].name not in {activity.name for activity in initial}


@pytest.mark.asyncio
async def test_llm_ranking_receives_choices_and_controls_the_adaptive_pick() -> None:
    inventories = load_city_journal_inventories()
    local_algorithm = ActivityRecommendationAlgorithm(inventories)
    initial_pages = await local_algorithm.get_initial_pairs("Barcelona", ("art",))
    initial = tuple(activity for page in initial_pages for activity in page.activities)
    selected = (initial[0], initial[2], initial[4])
    rejected = (initial[1], initial[3], initial[5])
    fallback = local_algorithm._local_rank(
        "Barcelona",
        ("art",),
        selected,
        rejected,
        local_algorithm._entries_for_city("Barcelona"),
    )
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
        inventories,
        openai_client=openai,  # type: ignore[arg-type]
        openai_model="test-model",
        random_source=PredictableRandom({}, 0.5),
    )

    state = PreferenceAlgorithmState.priors()
    adaptive = await algorithm.get_next_page(
        "Barcelona", ("art",), initial, selected, rejected, state
    )

    assert adaptive is not None
    assert len(responses.calls) == 1
    request = responses.calls[0]
    assert request["store"] is False
    assert request["text_format"].__name__ == "RankedActivities"  # type: ignore[union-attr]
    payload = json.loads(request["input"])  # type: ignore[arg-type]
    assert payload["liked"] == [activity.name for activity in selected]
    assert payload["disliked"] == [activity.name for activity in rejected]
    assert all(
        candidate["journal_entry"]
        for candidates in payload["candidates_by_category"].values()
        for candidate in candidates
    )
    selected_categories = algorithm._select_categories(state, CATEGORIES)
    assert [activity.name for activity in adaptive.activities] == [
        next(
            activity.name for activity in reversed(fallback[category]) if activity.name not in seen
        )
        for category in selected_categories
    ]


def test_thompson_sampling_uses_persisted_arms_and_page_size_probability() -> None:
    state = PreferenceAlgorithmState(
        arms={
            "food": BanditArm(alpha=4, beta=1),
            "culture": BanditArm(alpha=2, beta=2),
            "outdoors": BanditArm(alpha=1, beta=4),
            "neighbourhoods": BanditArm(alpha=1, beta=3),
        }
    )
    random_source = PredictableRandom(
        {(4, 1): 0.9, (1, 3): 0.2, (2, 2): 0.8, (1, 4): 0.1},
        0.34,
    )
    algorithm = ActivityRecommendationAlgorithm(
        load_city_journal_inventories(),
        random_source=random_source,
    )

    assert algorithm._select_categories(state, CATEGORIES) == ("food", "culture")


@pytest.mark.asyncio
async def test_unsupported_city_never_falls_back_to_placeholder_inventory() -> None:
    algorithm = ActivityRecommendationAlgorithm(load_city_journal_inventories())

    with pytest.raises(UnsupportedJournalCityError):
        await algorithm.get_initial_pairs("Madrid", ())
