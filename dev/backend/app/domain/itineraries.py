import unicodedata
from enum import StrEnum


class ItineraryStatus(StrEnum):
    LEARNING_PREFERENCES = "learning_preferences"
    QUEUED = "queued"
    RESEARCHING = "researching"
    PLANNING = "planning"
    ILLUSTRATING = "illustrating"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"


class PublicItineraryStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAIL = "fail"


class PendingItineraryStage(StrEnum):
    LEARNING_PREFERENCES = "learning_preferences"
    QUEUED = "queued"
    RESEARCHING = "researching"
    PLANNING = "planning"
    ILLUSTRATING = "illustrating"


class GenerationStage(StrEnum):
    ORCHESTRATION = "orchestration"
    RESEARCH = "research"
    PLANNING = "planning"
    ILLUSTRATION = "illustration"


class GenerationRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class MediaStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class MediaRole(StrEnum):
    HERO = "hero"
    STOP_ILLUSTRATION = "stop_illustration"


class PlaceLinkKind(StrEnum):
    MAP = "map"
    OFFICIAL = "official"
    SOURCE = "source"


TERMINAL_ITINERARY_STATUSES = frozenset(
    {ItineraryStatus.READY, ItineraryStatus.PARTIAL, ItineraryStatus.FAILED}
)

_ALLOWED_TRANSITIONS: dict[ItineraryStatus, frozenset[ItineraryStatus]] = {
    ItineraryStatus.LEARNING_PREFERENCES: frozenset(
        {ItineraryStatus.QUEUED, ItineraryStatus.FAILED}
    ),
    ItineraryStatus.QUEUED: frozenset({ItineraryStatus.RESEARCHING, ItineraryStatus.FAILED}),
    ItineraryStatus.RESEARCHING: frozenset({ItineraryStatus.PLANNING, ItineraryStatus.FAILED}),
    ItineraryStatus.PLANNING: frozenset(
        {
            ItineraryStatus.ILLUSTRATING,
            ItineraryStatus.READY,
            ItineraryStatus.FAILED,
        }
    ),
    ItineraryStatus.ILLUSTRATING: frozenset(
        {ItineraryStatus.READY, ItineraryStatus.PARTIAL, ItineraryStatus.FAILED}
    ),
    ItineraryStatus.READY: frozenset(),
    ItineraryStatus.PARTIAL: frozenset(),
    ItineraryStatus.FAILED: frozenset(),
}


def clean_human_text(value: str, *, field: str, max_length: int) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise ValueError(f"{field} cannot contain control characters")
    cleaned = " ".join(normalized.split())
    if not cleaned:
        raise ValueError(f"{field} must contain at least 1 character")
    if len(cleaned) > max_length:
        raise ValueError(f"{field} must contain at most {max_length} characters")
    if not any(character.isalpha() for character in cleaned):
        raise ValueError(f"{field} must contain at least one letter")
    return cleaned


def clean_city(value: str) -> str:
    """Validate a requested or provider-resolved destination."""
    return clean_human_text(value, field="city", max_length=160)


def normalize_city(value: str) -> str:
    """Return the comparison form without claiming geographic disambiguation."""
    return clean_city(value).casefold()


def clean_tag(value: str) -> str:
    return clean_human_text(value, field="tag", max_length=50)


def clean_tags(values: list[str] | tuple[str, ...]) -> list[str]:
    if len(values) > 20:
        raise ValueError("tags must contain at most 20 items")
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = clean_tag(value)
        comparison = tag.casefold()
        if comparison not in seen:
            cleaned.append(tag)
            seen.add(comparison)
    return cleaned


def public_itinerary_status(status: ItineraryStatus) -> PublicItineraryStatus:
    if status in {ItineraryStatus.FAILED, ItineraryStatus.PARTIAL}:
        return PublicItineraryStatus.FAIL
    if status == ItineraryStatus.READY:
        return PublicItineraryStatus.DONE
    return PublicItineraryStatus.PENDING


def can_transition(current: ItineraryStatus, target: ItineraryStatus) -> bool:
    return current == target or target in _ALLOWED_TRANSITIONS[current]


def ensure_transition(current: ItineraryStatus, target: ItineraryStatus) -> None:
    if not can_transition(current, target):
        raise ValueError(f"invalid itinerary transition: {current.value} -> {target.value}")
