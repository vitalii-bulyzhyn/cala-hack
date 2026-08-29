from dataclasses import dataclass

from fastapi import status


@dataclass(eq=False)
class AppError(Exception):
    code: str
    message: str
    status_code: int
    retryable: bool = False


class ItineraryNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ITINERARY_NOT_FOUND",
            message="The requested itinerary does not exist.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class IdempotencyConflictError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="IDEMPOTENCY_KEY_REUSED",
            message="That idempotency key was already used for different city/tag input.",
            status_code=status.HTTP_409_CONFLICT,
        )


class PersistenceUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="SERVICE_UNAVAILABLE",
            message="The itinerary service is temporarily unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            retryable=True,
        )


class PreferenceEngineUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PREFERENCE_ENGINE_NOT_CONFIGURED",
            message="Preference suggestions are not configured yet.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            retryable=False,
        )


class PreferenceEngineInvalidOutputError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PREFERENCE_ENGINE_INVALID_OUTPUT",
            message="The preference engine returned an invalid activity page.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            retryable=False,
        )


class UnsupportedJournalCityError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="CITY_NOT_SUPPORTED",
            message="Travel Journal currently supports Barcelona, Toulouse, and Valencia.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            retryable=False,
        )


class PreferenceLearningClosedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PREFERENCE_LEARNING_CLOSED",
            message="Preference learning is already complete for this itinerary.",
            status_code=status.HTTP_409_CONFLICT,
        )


class PreferenceItemNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PREFERENCE_ITEM_NOT_FOUND",
            message="The requested preference item does not belong to this itinerary.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class PreferencePageNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PREFERENCE_PAGE_NOT_FOUND",
            message="The requested preference page does not belong to this itinerary.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class PreferencePageIncompleteError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PREFERENCE_PAGE_INCOMPLETE",
            message="Respond to every item on the current page before continuing.",
            status_code=status.HTTP_409_CONFLICT,
        )
