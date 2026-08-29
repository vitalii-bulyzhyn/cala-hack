from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Itinerary, PreferenceLearningSession
from app.domain.itineraries import ItineraryStatus


class IdempotencyFingerprintMismatchError(Exception):
    pass


@dataclass(frozen=True)
class CreatedItinerary:
    itinerary: Itinerary
    replayed: bool


class ItineraryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        city: str,
        tags: list[str],
        request_fingerprint: str,
        legacy_request_fingerprint: str | None,
        idempotency_key_hash: str | None,
    ) -> CreatedItinerary:
        if idempotency_key_hash is not None:
            existing = await self._get_by_idempotency_hash(idempotency_key_hash)
            if existing is not None:
                return self._replay(
                    existing,
                    request_fingerprint,
                    legacy_request_fingerprint,
                )

        itinerary_id = uuid4()
        itinerary = Itinerary(
            id=itinerary_id,
            city=city,
            tags=tags,
            destination=None,
            request_fingerprint=request_fingerprint,
            idempotency_key_hash=idempotency_key_hash,
            status=ItineraryStatus.LEARNING_PREFERENCES,
        )
        preference_learning = PreferenceLearningSession(itinerary_id=itinerary_id)
        self._session.add_all([itinerary, preference_learning])

        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            if idempotency_key_hash is None:
                raise
            existing = await self._get_by_idempotency_hash(idempotency_key_hash)
            if existing is None:
                raise
            return self._replay(
                existing,
                request_fingerprint,
                legacy_request_fingerprint,
            )

        return CreatedItinerary(
            itinerary=itinerary,
            replayed=False,
        )

    async def get(self, itinerary_id: UUID) -> Itinerary | None:
        statement = (
            select(Itinerary)
            .where(Itinerary.id == itinerary_id)
            .options(
                selectinload(Itinerary.stops),
                selectinload(Itinerary.media_assets),
            )
        )
        return await self._session.scalar(statement)

    async def _get_by_idempotency_hash(self, key_hash: str) -> Itinerary | None:
        statement = select(Itinerary).where(Itinerary.idempotency_key_hash == key_hash)
        return await self._session.scalar(statement)

    @staticmethod
    def _replay(
        existing: Itinerary,
        request_fingerprint: str,
        legacy_request_fingerprint: str | None,
    ) -> CreatedItinerary:
        compatible_fingerprints = {request_fingerprint, legacy_request_fingerprint}
        if existing.request_fingerprint not in compatible_fingerprints:
            raise IdempotencyFingerprintMismatchError
        return CreatedItinerary(
            itinerary=existing,
            replayed=True,
        )
