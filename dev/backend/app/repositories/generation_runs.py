from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    GenerationRun,
    Itinerary,
    MediaAsset,
    PreferenceItem,
    PreferencePage,
    PreferenceResponse,
    Stop,
)
from app.domain.itineraries import (
    GenerationRunStatus,
    GenerationStage,
    ItineraryStatus,
    MediaRole,
    MediaStatus,
    can_transition,
)
from app.domain.preferences import Activity, PreferenceDecision
from app.services.content_generation import GenerationCompletion


class LostLeaseError(Exception):
    pass


class InvalidGenerationCompletionError(Exception):
    pass


@dataclass(frozen=True)
class ClaimedGenerationRun:
    id: UUID
    itinerary_id: UUID
    attempt_count: int
    max_attempts: int
    lease_owner: str
    lease_version: int
    city: str
    tags: tuple[str, ...]
    reference_date: date
    checkpoint_data: dict[str, object] | None
    provider_request_id: str | None
    provider_model_id: str | None
    selected_activities: tuple[Activity, ...] = ()
    rejected_activities: tuple[Activity, ...] = ()


class GenerationRunStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        lease_seconds: int,
    ) -> None:
        self._session_factory = session_factory
        self._lease_seconds = lease_seconds

    async def claim(
        self,
        *,
        worker_id: str,
        run_id: UUID | None = None,
    ) -> ClaimedGenerationRun | None:
        async with self._session_factory() as session, session.begin():
            now = await self._database_now(session)
            claimable = or_(
                and_(
                    GenerationRun.status.in_(
                        [GenerationRunStatus.QUEUED, GenerationRunStatus.RETRY_WAIT]
                    ),
                    GenerationRun.available_at <= now,
                    GenerationRun.attempt_count < GenerationRun.max_attempts,
                ),
                and_(
                    GenerationRun.status == GenerationRunStatus.RUNNING,
                    GenerationRun.lease_expires_at <= now,
                    GenerationRun.attempt_count < GenerationRun.max_attempts,
                ),
            )
            statement = (
                select(GenerationRun)
                .where(claimable)
                .order_by(GenerationRun.available_at, GenerationRun.queued_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if run_id is not None:
                statement = statement.where(GenerationRun.id == run_id)
            run = await session.scalar(statement)
            if run is None:
                return None

            run.status = GenerationRunStatus.RUNNING
            run.attempt_count += 1
            run.lease_owner = worker_id
            run.lease_version += 1
            run.heartbeat_at = now
            run.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            run.started_at = run.started_at or now
            run.finished_at = None
            run.error_code = None
            run.error_message = None
            run.error_retryable = None

            itinerary = await session.scalar(
                select(Itinerary).where(Itinerary.id == run.itinerary_id).with_for_update()
            )
            if itinerary is None:
                return None
            if itinerary.status == ItineraryStatus.QUEUED:
                self._transition_itinerary(itinerary, ItineraryStatus.RESEARCHING, now)

            preference_rows = await session.execute(
                select(PreferenceItem, PreferenceResponse.decision)
                .join(
                    PreferenceResponse,
                    (PreferenceResponse.itinerary_id == PreferenceItem.itinerary_id)
                    & (PreferenceResponse.item_id == PreferenceItem.id),
                )
                .join(PreferencePage, PreferencePage.id == PreferenceItem.page_id)
                .where(PreferenceItem.itinerary_id == itinerary.id)
                .order_by(PreferencePage.position, PreferenceItem.position)
            )
            selected: list[Activity] = []
            rejected: list[Activity] = []
            for item, decision in preference_rows:
                activity = Activity(
                    name=item.name,
                    category=item.category,
                    description=item.description,
                    image_link=item.image_link,
                )
                if decision == PreferenceDecision.LIKE:
                    selected.append(activity)
                else:
                    rejected.append(activity)

            return ClaimedGenerationRun(
                id=run.id,
                itinerary_id=run.itinerary_id,
                attempt_count=run.attempt_count,
                max_attempts=run.max_attempts,
                lease_owner=worker_id,
                lease_version=run.lease_version,
                city=itinerary.city,
                tags=tuple(itinerary.tags),
                reference_date=itinerary.created_at.astimezone(UTC).date(),
                checkpoint_data=run.checkpoint_data,
                provider_request_id=run.provider_request_id,
                provider_model_id=run.model_id,
                selected_activities=tuple(selected),
                rejected_activities=tuple(rejected),
            )

    async def save_plan_checkpoint(
        self,
        claim: ClaimedGenerationRun,
        checkpoint_data: dict[str, object],
    ) -> None:
        async with self._session_factory() as session, session.begin():
            now = await self._database_now(session)
            run = await self._owned_run(session, claim, now, lock=True)
            if run is None:
                raise LostLeaseError
            if run.checkpoint_data is not None:
                if run.checkpoint_data != checkpoint_data:
                    raise InvalidGenerationCompletionError(
                        "an existing plan checkpoint cannot be overwritten"
                    )
                return
            run.checkpoint_data = checkpoint_data
            run.stage = GenerationStage.PLANNING
            itinerary = await session.scalar(
                select(Itinerary).where(Itinerary.id == run.itinerary_id).with_for_update()
            )
            if itinerary is None:
                raise InvalidGenerationCompletionError("itinerary disappeared during planning")
            if itinerary.status == ItineraryStatus.RESEARCHING:
                self._transition_itinerary(itinerary, ItineraryStatus.PLANNING, now)

    async def save_image_submission(
        self,
        claim: ClaimedGenerationRun,
        *,
        provider: str,
        request_id: str,
        model_id: str,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            now = await self._database_now(session)
            run = await self._owned_run(session, claim, now, lock=True)
            if run is None:
                raise LostLeaseError
            if run.provider_request_id is not None:
                if (
                    run.provider_request_id != request_id
                    or run.provider != provider
                    or run.model_id != model_id
                ):
                    raise InvalidGenerationCompletionError(
                        "an existing provider submission cannot be overwritten"
                    )
                return
            run.provider = provider
            run.provider_request_id = request_id
            run.model_id = model_id
            run.stage = GenerationStage.ILLUSTRATION
            itinerary = await session.scalar(
                select(Itinerary).where(Itinerary.id == run.itinerary_id).with_for_update()
            )
            if itinerary is None:
                raise InvalidGenerationCompletionError("itinerary disappeared during illustration")
            if itinerary.status == ItineraryStatus.RESEARCHING:
                self._transition_itinerary(itinerary, ItineraryStatus.PLANNING, now)
            if itinerary.status == ItineraryStatus.PLANNING:
                self._transition_itinerary(itinerary, ItineraryStatus.ILLUSTRATING, now)

    async def extend_lease(self, claim: ClaimedGenerationRun) -> bool:
        async with self._session_factory() as session, session.begin():
            now = await self._database_now(session)
            run = await self._owned_run(session, claim, now, lock=True)
            if run is None:
                return False
            run.heartbeat_at = now
            run.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            return True

    async def schedule_retry(
        self,
        claim: ClaimedGenerationRun,
        *,
        code: str,
        message: str,
        delay_seconds: float,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            now = await self._database_now(session)
            run = await self._owned_run(session, claim, now, lock=True)
            if run is None:
                raise LostLeaseError
            run.status = GenerationRunStatus.RETRY_WAIT
            run.available_at = now + timedelta(seconds=delay_seconds)
            run.error_code = code
            run.error_message = message
            run.error_retryable = True
            self._clear_lease(run)

    async def fail(
        self,
        claim: ClaimedGenerationRun,
        *,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            now = await self._database_now(session)
            run = await self._owned_run(session, claim, now, lock=True)
            if run is None:
                raise LostLeaseError
            run.status = GenerationRunStatus.FAILED
            run.finished_at = now
            run.error_code = code
            run.error_message = message
            run.error_retryable = retryable
            self._clear_lease(run)
            await self._fail_itinerary(
                session,
                itinerary_id=run.itinerary_id,
                now=now,
                code=code,
                message=message,
                retryable=retryable,
                request_id=f"job_{run.id.hex}",
            )

    async def succeed(
        self,
        claim: ClaimedGenerationRun,
        *,
        completion: GenerationCompletion,
    ) -> None:
        if completion.final_status != ItineraryStatus.READY:
            raise InvalidGenerationCompletionError("pipeline did not return a complete itinerary")
        self._validate_completion(completion)

        async with self._session_factory() as session, session.begin():
            now = await self._database_now(session)
            run = await self._owned_run(session, claim, now, lock=True)
            if run is None:
                raise LostLeaseError
            itinerary = await session.scalar(
                select(Itinerary).where(Itinerary.id == run.itinerary_id).with_for_update()
            )
            if itinerary is None:
                raise InvalidGenerationCompletionError("itinerary disappeared during completion")

            existing_stop_count = await session.scalar(
                select(func.count(Stop.id)).where(Stop.itinerary_id == run.itinerary_id)
            )
            if existing_stop_count:
                raise InvalidGenerationCompletionError(
                    "completion cannot overwrite already persisted itinerary content"
                )

            stop_ids: dict[int, UUID] = {}
            for generated in completion.stops:
                stop = Stop(
                    itinerary_id=run.itinerary_id,
                    position=generated.position,
                    start_time=generated.start_time,
                    end_time=generated.end_time,
                    name=generated.name,
                    category=generated.category,
                    description=generated.description,
                    reason_to_visit=generated.reason_to_visit,
                    address=generated.address,
                    latitude=generated.latitude,
                    longitude=generated.longitude,
                    cala_entity_id=generated.cala_entity_id,
                    evidence=list(generated.evidence),
                    evidence_retrieved_at=generated.evidence_retrieved_at,
                    evidence_confidence=generated.evidence_confidence,
                    links=list(generated.links),
                )
                session.add(stop)
                await session.flush()
                stop_ids[generated.position] = stop.id

            for generated in completion.media_assets:
                session.add(
                    MediaAsset(
                        itinerary_id=run.itinerary_id,
                        stop_id=(
                            stop_ids[generated.stop_position]
                            if generated.stop_position is not None
                            else None
                        ),
                        role=generated.role,
                        status=generated.status,
                        provider=generated.provider,
                        provider_request_id=generated.provider_request_id,
                        attempt_count=generated.attempt_count,
                        url=generated.url,
                        storage_key=generated.storage_key,
                        content_type=generated.content_type,
                        expires_at=generated.expires_at,
                        width=generated.width,
                        height=generated.height,
                        alt_text=generated.alt_text,
                        model_id=generated.model_id,
                        prompt_version=generated.prompt_version,
                        error_code=generated.error_code,
                        error_message=generated.error_message,
                    )
                )

            itinerary.destination = completion.destination
            itinerary.planned_date = completion.planned_date
            itinerary.destination_timezone = completion.destination_timezone
            itinerary.title = completion.title
            itinerary.summary = completion.summary
            self._advance_to_final(
                itinerary,
                final_status=completion.final_status,
                has_media=bool(completion.media_assets),
                now=now,
            )
            itinerary.completed_at = now
            run.status = GenerationRunStatus.SUCCEEDED
            run.finished_at = now
            run.checkpoint_data = None
            self._clear_lease(run)

    @staticmethod
    def _validate_completion(completion: GenerationCompletion) -> None:
        if not completion.destination.strip() or len(completion.destination) > 200:
            raise InvalidGenerationCompletionError("destination is invalid")
        if completion.planned_date is None:
            raise InvalidGenerationCompletionError("planned date is required")
        if not completion.destination_timezone.strip() or len(completion.destination_timezone) > 64:
            raise InvalidGenerationCompletionError("destination timezone is invalid")
        if not completion.title.strip() or len(completion.title) > 200:
            raise InvalidGenerationCompletionError("destination and title are required")
        if not completion.summary.strip():
            raise InvalidGenerationCompletionError("summary is required")
        if not 1 <= len(completion.stops) <= 10:
            raise InvalidGenerationCompletionError("a completed itinerary needs 1-10 stops")
        positions = [stop.position for stop in completion.stops]
        if positions != list(range(1, len(completion.stops) + 1)):
            raise InvalidGenerationCompletionError("stop positions must be consecutive from one")
        previous_end = None
        for stop in completion.stops:
            if not stop.name.strip() or len(stop.name) > 200:
                raise InvalidGenerationCompletionError("stop names are invalid")
            if not stop.category.strip() or len(stop.category) > 80:
                raise InvalidGenerationCompletionError("stop categories are invalid")
            if not stop.description.strip() or not stop.reason_to_visit.strip():
                raise InvalidGenerationCompletionError("stop journal content is required")
            if stop.address is not None and len(stop.address) > 300:
                raise InvalidGenerationCompletionError("stop addresses are too long")
            if (stop.latitude is None) != (stop.longitude is None):
                raise InvalidGenerationCompletionError("stop coordinates must be supplied together")
            if stop.latitude is not None and not Decimal("-90") <= stop.latitude <= Decimal("90"):
                raise InvalidGenerationCompletionError("stop latitude is invalid")
            if stop.longitude is not None and not Decimal("-180") <= stop.longitude <= Decimal(
                "180"
            ):
                raise InvalidGenerationCompletionError("stop longitude is invalid")
            if not stop.links:
                raise InvalidGenerationCompletionError("every place requires at least one link")
            for link in stop.links:
                if set(link) != {"kind", "label", "url"}:
                    raise InvalidGenerationCompletionError("place links have an invalid shape")
                if not all(isinstance(value, str) for value in link.values()):
                    raise InvalidGenerationCompletionError("place link values must be strings")
                if link["kind"] not in {"map", "official", "source"}:
                    raise InvalidGenerationCompletionError("place link kind is invalid")
                if not link["label"].strip() or len(link["label"]) > 100:
                    raise InvalidGenerationCompletionError("place link label is invalid")
                if not GenerationRunStore._is_public_http_url(link["url"]):
                    raise InvalidGenerationCompletionError("place link URL is invalid")
            if not any(link["kind"] == "map" for link in stop.links):
                raise InvalidGenerationCompletionError("every place requires a map link")
            if stop.start_time >= stop.end_time:
                raise InvalidGenerationCompletionError("stop time windows must be positive")
            if previous_end is not None and stop.start_time < previous_end:
                raise InvalidGenerationCompletionError("stop time windows cannot overlap")
            previous_end = stop.end_time
        stop_positions = set(positions)
        for asset in completion.media_assets:
            if asset.stop_position is not None and asset.stop_position not in stop_positions:
                raise InvalidGenerationCompletionError("media references an unknown stop")
            if asset.role == MediaRole.STOP_ILLUSTRATION and asset.stop_position is None:
                raise InvalidGenerationCompletionError("stop illustrations require a stop")
            if asset.role == MediaRole.HERO and asset.stop_position is not None:
                raise InvalidGenerationCompletionError("journal images cannot belong to a stop")
            if asset.status not in {MediaStatus.READY, MediaStatus.FAILED}:
                raise InvalidGenerationCompletionError("final media must be ready or failed")
            if asset.status == MediaStatus.READY and (
                not asset.url
                or not asset.content_type
                or not asset.content_type.startswith("image/")
                or not asset.alt_text
                or asset.width is None
                or asset.width <= 0
                or asset.height is None
                or asset.height <= 0
            ):
                raise InvalidGenerationCompletionError("ready media output is incomplete")
            if asset.status == MediaStatus.READY and not (
                asset.url.startswith("/") or GenerationRunStore._is_public_http_url(asset.url)
            ):
                raise InvalidGenerationCompletionError("ready media URL is invalid")
            if asset.role == MediaRole.HERO and not asset.storage_key:
                raise InvalidGenerationCompletionError("journal images require owned storage")
            if asset.status == MediaStatus.FAILED and (
                not asset.error_code or not asset.error_message
            ):
                raise InvalidGenerationCompletionError("failed media requires a safe error")
        if completion.final_status == ItineraryStatus.READY and any(
            asset.status != MediaStatus.READY for asset in completion.media_assets
        ):
            raise InvalidGenerationCompletionError("ready itineraries cannot contain failed media")
        ready_heroes = [
            asset
            for asset in completion.media_assets
            if asset.role == MediaRole.HERO and asset.status == MediaStatus.READY
        ]
        if completion.final_status == ItineraryStatus.READY and len(ready_heroes) != 1:
            raise InvalidGenerationCompletionError(
                "ready itineraries require exactly one ready journal image"
            )
        if completion.final_status == ItineraryStatus.READY and completion.error_code:
            raise InvalidGenerationCompletionError("ready itineraries cannot contain an error")

    @staticmethod
    def _is_public_http_url(value: str) -> bool:
        try:
            parsed = urlsplit(value)
        except ValueError:
            return False
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )

    def _advance_to_final(
        self,
        itinerary: Itinerary,
        *,
        final_status: ItineraryStatus,
        has_media: bool,
        now: datetime,
    ) -> None:
        if itinerary.status == ItineraryStatus.RESEARCHING:
            self._transition_itinerary(itinerary, ItineraryStatus.PLANNING, now)
        if itinerary.status == ItineraryStatus.PLANNING and (
            has_media or final_status == ItineraryStatus.PARTIAL
        ):
            self._transition_itinerary(itinerary, ItineraryStatus.ILLUSTRATING, now)
        self._transition_itinerary(itinerary, final_status, now)

    async def terminalize_exhausted(self) -> int:
        async with self._session_factory() as session, session.begin():
            now = await self._database_now(session)
            exhausted = or_(
                and_(
                    GenerationRun.status.in_(
                        [GenerationRunStatus.QUEUED, GenerationRunStatus.RETRY_WAIT]
                    ),
                    GenerationRun.available_at <= now,
                    GenerationRun.attempt_count >= GenerationRun.max_attempts,
                ),
                and_(
                    GenerationRun.status == GenerationRunStatus.RUNNING,
                    GenerationRun.lease_expires_at <= now,
                    GenerationRun.attempt_count >= GenerationRun.max_attempts,
                ),
            )
            runs = list(
                await session.scalars(
                    select(GenerationRun)
                    .where(exhausted)
                    .order_by(GenerationRun.available_at)
                    .limit(100)
                    .with_for_update(skip_locked=True)
                )
            )
            for run in runs:
                run.status = GenerationRunStatus.FAILED
                run.finished_at = now
                run.error_code = "GENERATION_ATTEMPTS_EXHAUSTED"
                run.error_message = "The itinerary could not be completed after several attempts."
                run.error_retryable = False
                self._clear_lease(run)
                await self._fail_itinerary(
                    session,
                    itinerary_id=run.itinerary_id,
                    now=now,
                    code=run.error_code,
                    message=run.error_message,
                    retryable=False,
                    request_id=f"job_{run.id.hex}",
                )
            return len(runs)

    @staticmethod
    async def _database_now(session: AsyncSession) -> datetime:
        return await session.scalar(select(func.now()))  # type: ignore[return-value]

    @staticmethod
    async def _owned_run(
        session: AsyncSession,
        claim: ClaimedGenerationRun,
        now: datetime,
        *,
        lock: bool,
    ) -> GenerationRun | None:
        statement = select(GenerationRun).where(
            GenerationRun.id == claim.id,
            GenerationRun.status == GenerationRunStatus.RUNNING,
            GenerationRun.lease_owner == claim.lease_owner,
            GenerationRun.lease_version == claim.lease_version,
            GenerationRun.lease_expires_at > now,
        )
        if lock:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    @staticmethod
    def _clear_lease(run: GenerationRun) -> None:
        run.lease_owner = None
        run.lease_expires_at = None
        run.heartbeat_at = None

    @staticmethod
    def _transition_itinerary(
        itinerary: Itinerary,
        target: ItineraryStatus,
        now: datetime,
    ) -> None:
        if not can_transition(itinerary.status, target):
            raise InvalidGenerationCompletionError(
                f"invalid itinerary transition: {itinerary.status.value} -> {target.value}"
            )
        itinerary.status = target
        itinerary.state_version += 1
        itinerary.status_changed_at = now

    async def _fail_itinerary(
        self,
        session: AsyncSession,
        *,
        itinerary_id: UUID,
        now: datetime,
        code: str,
        message: str,
        retryable: bool,
        request_id: str,
    ) -> None:
        itinerary = await session.scalar(
            select(Itinerary).where(Itinerary.id == itinerary_id).with_for_update()
        )
        if itinerary is None:
            return
        target = ItineraryStatus.FAILED
        if itinerary.status in {
            ItineraryStatus.READY,
            ItineraryStatus.PARTIAL,
            ItineraryStatus.FAILED,
        }:
            return
        self._transition_itinerary(itinerary, target, now)
        itinerary.error_code = code
        itinerary.error_message = message
        itinerary.error_retryable = retryable
        itinerary.error_request_id = request_id
        itinerary.completed_at = now
