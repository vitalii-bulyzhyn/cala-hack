import pytest

from app.domain.itineraries import (
    ItineraryStatus,
    PublicItineraryStatus,
    can_transition,
    clean_city,
    clean_tag,
    clean_tags,
    ensure_transition,
    normalize_city,
    public_itinerary_status,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "  Barcelona,   Spain  ",
            "Barcelona, Spain",
        ),
        (
            "\uff22\uff41\uff52\uff43\uff45\uff4c\uff4f\uff4e\uff41",
            "Barcelona",
        ),
        ("São   Paulo", "São Paulo"),
    ],
)
def test_clean_city_normalizes_safe_display_input(
    value: str,
    expected: str,
) -> None:
    assert clean_city(value) == expected


def test_city_accepts_exact_cleaned_limit() -> None:
    assert clean_city("a" * 160) == "a" * 160


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "1234 - 5678",
        "a" * 161,
        "Visit\x00Barcelona",
        "Visit\nBarcelona",
        "Visit\tBarcelona",
    ],
)
def test_clean_city_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match="city"):
        clean_city(value)


def test_clean_tags_normalizes_deduplicates_and_preserves_first_order() -> None:
    assert clean_tags(["  Art ", "local   food", "ART"]) == ["Art", "local food"]


def test_clean_tag_accepts_exact_limit() -> None:
    assert clean_tag("a" * 50) == "a" * 50


@pytest.mark.parametrize("value", ["", "   ", "1234", "a" * 51, "art\nfood"])
def test_clean_tag_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match="tag"):
        clean_tag(value)


def test_clean_tags_rejects_more_than_twenty_values() -> None:
    with pytest.raises(ValueError, match="at most 20"):
        clean_tags([f"tag-{index}" for index in range(21)])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  Barcelona, Spain  ", "Barcelona, Spain"),
        ("São   Paulo", "São Paulo"),
        ("\uff22\uff41\uff52\uff43\uff45\uff4c\uff4f\uff4e\uff41", "Barcelona"),
    ],
)
def test_clean_city_validates_provider_resolved_destination(
    value: str,
    expected: str,
) -> None:
    assert clean_city(value) == expected


def test_normalize_city_supports_legacy_fingerprints() -> None:
    assert normalize_city("  BARCELONA ") == "barcelona"
    assert normalize_city("Barcelona") == normalize_city("barcelona")


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "1234 - 5678",
        "a" * 161,
        "Barce\x00lona",
    ],
)
def test_clean_city_rejects_other_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match="city"):
        clean_city(value)


@pytest.mark.parametrize(
    ("internal", "public"),
    [
        (ItineraryStatus.LEARNING_PREFERENCES, PublicItineraryStatus.PENDING),
        (ItineraryStatus.QUEUED, PublicItineraryStatus.PENDING),
        (ItineraryStatus.RESEARCHING, PublicItineraryStatus.PENDING),
        (ItineraryStatus.PLANNING, PublicItineraryStatus.PENDING),
        (ItineraryStatus.ILLUSTRATING, PublicItineraryStatus.PENDING),
        (ItineraryStatus.READY, PublicItineraryStatus.DONE),
        (ItineraryStatus.PARTIAL, PublicItineraryStatus.FAIL),
        (ItineraryStatus.FAILED, PublicItineraryStatus.FAIL),
    ],
)
def test_internal_lifecycle_projects_to_three_public_states(
    internal: ItineraryStatus,
    public: PublicItineraryStatus,
) -> None:
    assert public_itinerary_status(internal) == public


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (
            ItineraryStatus.LEARNING_PREFERENCES,
            ItineraryStatus.LEARNING_PREFERENCES,
        ),
        (ItineraryStatus.LEARNING_PREFERENCES, ItineraryStatus.QUEUED),
        (ItineraryStatus.LEARNING_PREFERENCES, ItineraryStatus.FAILED),
        (ItineraryStatus.QUEUED, ItineraryStatus.QUEUED),
        (ItineraryStatus.QUEUED, ItineraryStatus.RESEARCHING),
        (ItineraryStatus.QUEUED, ItineraryStatus.FAILED),
        (ItineraryStatus.RESEARCHING, ItineraryStatus.PLANNING),
        (ItineraryStatus.RESEARCHING, ItineraryStatus.FAILED),
        (ItineraryStatus.PLANNING, ItineraryStatus.ILLUSTRATING),
        (ItineraryStatus.PLANNING, ItineraryStatus.READY),
        (ItineraryStatus.PLANNING, ItineraryStatus.FAILED),
        (ItineraryStatus.ILLUSTRATING, ItineraryStatus.READY),
        (ItineraryStatus.ILLUSTRATING, ItineraryStatus.PARTIAL),
        (ItineraryStatus.ILLUSTRATING, ItineraryStatus.FAILED),
        (ItineraryStatus.READY, ItineraryStatus.READY),
    ],
)
def test_allowed_itinerary_lifecycle_transitions(
    current: ItineraryStatus,
    target: ItineraryStatus,
) -> None:
    assert can_transition(current, target) is True
    ensure_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ItineraryStatus.LEARNING_PREFERENCES, ItineraryStatus.RESEARCHING),
        (ItineraryStatus.QUEUED, ItineraryStatus.READY),
        (ItineraryStatus.RESEARCHING, ItineraryStatus.PARTIAL),
        (ItineraryStatus.ILLUSTRATING, ItineraryStatus.PLANNING),
        (ItineraryStatus.READY, ItineraryStatus.RESEARCHING),
        (ItineraryStatus.FAILED, ItineraryStatus.QUEUED),
    ],
)
def test_invalid_itinerary_lifecycle_transitions_are_rejected(
    current: ItineraryStatus,
    target: ItineraryStatus,
) -> None:
    assert can_transition(current, target) is False
    with pytest.raises(
        ValueError,
        match=rf"{current.value} -> {target.value}",
    ):
        ensure_transition(current, target)
