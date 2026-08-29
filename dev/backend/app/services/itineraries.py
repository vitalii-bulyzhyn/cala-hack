import hashlib
import json
import logging
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import (
    IdempotencyConflictError,
    ItineraryNotFoundError,
    PersistenceUnavailableError,
)
from app.db.models import Itinerary
from app.domain.itineraries import (
    PublicItineraryStatus,
    clean_city,
    clean_tags,
    normalize_city,
    public_itinerary_status,
)
from app.repositories.itineraries import (
    IdempotencyFingerprintMismatchError,
    ItineraryRepository,
)

logger = logging.getLogger(__name__)
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@dataclass(frozen=True)
class AcceptedItinerary:
    id: UUID
    status: PublicItineraryStatus
    replayed: bool


class ItineraryService:
    def __init__(
        self,
        repository: ItineraryRepository,
    ) -> None:
        self._repository = repository

    async def create(
        self,
        city: str,
        tags: list[str],
        idempotency_key: str | None,
    ) -> AcceptedItinerary:
        cleaned_city = clean_city(city)
        cleaned_tags = clean_tags(tags)
        fingerprint = self._fingerprint(cleaned_city, cleaned_tags)
        key_hash = self._hash_idempotency_key(idempotency_key)

        try:
            created = await self._repository.create(
                city=cleaned_city,
                tags=cleaned_tags,
                request_fingerprint=fingerprint,
                legacy_request_fingerprint=(
                    self._legacy_fingerprint(cleaned_city) if not cleaned_tags else None
                ),
                idempotency_key_hash=key_hash,
            )
        except IdempotencyFingerprintMismatchError as exc:
            raise IdempotencyConflictError from exc
        except SQLAlchemyError as exc:
            logger.exception("Could not persist itinerary")
            raise PersistenceUnavailableError from exc

        return AcceptedItinerary(
            id=created.itinerary.id,
            status=public_itinerary_status(created.itinerary.status),
            replayed=created.replayed,
        )

    async def get(self, itinerary_id: UUID) -> Itinerary:
        try:
            itinerary = await self._repository.get(itinerary_id)
        except SQLAlchemyError as exc:
            logger.exception("Could not load itinerary %s", itinerary_id)
            raise PersistenceUnavailableError from exc
        if itinerary is None:
            raise ItineraryNotFoundError
        return itinerary

    @staticmethod
    def _fingerprint(city: str, tags: list[str]) -> str:
        canonical_request = json.dumps(
            {
                "city": normalize_city(city),
                "tags": sorted(tag.casefold() for tag in clean_tags(tags)),
                "version": 3,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical_request.encode()).hexdigest()

    @staticmethod
    def _legacy_fingerprint(city: str) -> str | None:
        try:
            legacy_city = normalize_city(city)
        except ValueError:
            return None
        canonical_request = json.dumps(
            {"city": legacy_city, "version": 1},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical_request.encode()).hexdigest()

    @staticmethod
    def _hash_idempotency_key(idempotency_key: str | None) -> str | None:
        if idempotency_key is None:
            return None
        if IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key) is None:
            raise ValueError("Idempotency-Key must be 1-128 letters, digits, '.', '_', ':', or '-'")
        return hashlib.sha256(idempotency_key.encode()).hexdigest()
