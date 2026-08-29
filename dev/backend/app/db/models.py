from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.domain.itineraries import (
    GenerationRunStatus,
    GenerationStage,
    ItineraryStatus,
    MediaRole,
    MediaStatus,
)
from app.domain.preferences import (
    PreferenceDecision,
    PreferenceLearningStatus,
    PreferencePageLayout,
    PreferencePageSource,
)


def _enum_type(enum_type: type[StrEnum], name: str, length: int) -> SqlEnum:
    return SqlEnum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=False,
        validate_strings=True,
        length=length,
        values_callable=lambda members: [member.value for member in members],
    )


class Itinerary(TimestampMixin, Base):
    __tablename__ = "itineraries"
    __table_args__ = (
        UniqueConstraint("idempotency_key_hash", name="uq_itineraries_idempotency_key_hash"),
        CheckConstraint("state_version >= 0", name="ck_itineraries_state_version_nonnegative"),
        CheckConstraint(
            "status IN ('learning_preferences', 'queued', 'researching', "
            "'planning', 'illustrating', "
            "'ready', 'partial', 'failed')",
            name="itinerary_status",
        ),
        Index("ix_itineraries_status_created_at", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    city: Mapped[str] = mapped_column(String(160), nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    destination: Mapped[str | None] = mapped_column(String(200), index=True)
    planned_date: Mapped[date | None] = mapped_column()
    destination_timezone: Mapped[str | None] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[ItineraryStatus] = mapped_column(
        _enum_type(ItineraryStatus, "itinerary_status", 24),
        nullable=False,
        default=ItineraryStatus.LEARNING_PREFERENCES,
        server_default=ItineraryStatus.LEARNING_PREFERENCES.value,
    )
    title: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(500))
    error_retryable: Mapped[bool | None] = mapped_column(Boolean)
    error_request_id: Mapped[str | None] = mapped_column(String(80))
    state_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    stops: Mapped[list[Stop]] = relationship(
        back_populates="itinerary",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Stop.position",
        lazy="selectin",
    )
    media_assets: Mapped[list[MediaAsset]] = relationship(
        back_populates="itinerary",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MediaAsset.created_at",
        lazy="selectin",
    )
    generation_runs: Mapped[list[GenerationRun]] = relationship(
        back_populates="itinerary",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="GenerationRun.created_at",
        lazy="raise",
    )
    preference_learning: Mapped[PreferenceLearningSession] = relationship(
        back_populates="itinerary",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
        lazy="raise",
    )


class PreferenceLearningSession(TimestampMixin, Base):
    __tablename__ = "preference_learning_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('collecting', 'completed')",
            name="preference_learning_status",
        ),
    )

    itinerary_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("itineraries.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[PreferenceLearningStatus] = mapped_column(
        _enum_type(PreferenceLearningStatus, "preference_learning_status", 16),
        nullable=False,
        default=PreferenceLearningStatus.COLLECTING,
        server_default=PreferenceLearningStatus.COLLECTING.value,
    )
    algorithm_version: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    itinerary: Mapped[Itinerary] = relationship(back_populates="preference_learning")
    pages: Mapped[list[PreferencePage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PreferencePage.position",
        lazy="selectin",
    )


class PreferencePage(TimestampMixin, Base):
    __tablename__ = "preference_pages"
    __table_args__ = (
        UniqueConstraint(
            "itinerary_id",
            "position",
            name="uq_preference_pages_itinerary_position",
        ),
        UniqueConstraint("itinerary_id", "id", name="uq_preference_pages_itinerary_id_id"),
        CheckConstraint("position > 0", name="ck_preference_pages_position_positive"),
        CheckConstraint("layout IN ('single', 'pair')", name="preference_page_layout"),
        CheckConstraint("source IN ('initial', 'adaptive')", name="preference_page_source"),
        Index("ix_preference_pages_itinerary_id", "itinerary_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    itinerary_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("preference_learning_sessions.itinerary_id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    layout: Mapped[PreferencePageLayout] = mapped_column(
        _enum_type(PreferencePageLayout, "preference_page_layout", 8),
        nullable=False,
    )
    source: Mapped[PreferencePageSource] = mapped_column(
        _enum_type(PreferencePageSource, "preference_page_source", 8),
        nullable=False,
    )

    session: Mapped[PreferenceLearningSession] = relationship(back_populates="pages")
    entries: Mapped[list[PreferenceItem]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PreferenceItem.position",
        lazy="selectin",
    )


class PreferenceItem(TimestampMixin, Base):
    __tablename__ = "preference_items"
    __table_args__ = (
        UniqueConstraint("itinerary_id", "id", name="uq_preference_items_itinerary_id_id"),
        UniqueConstraint("page_id", "position", name="uq_preference_items_page_position"),
        CheckConstraint("position IN (1, 2)", name="ck_preference_items_position_range"),
        ForeignKeyConstraint(
            ["itinerary_id", "page_id"],
            ["preference_pages.itinerary_id", "preference_pages.id"],
            name="fk_preference_items_itinerary_page",
            ondelete="CASCADE",
        ),
        Index("ix_preference_items_itinerary_id", "itinerary_id"),
        Index("ix_preference_items_page_id", "page_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    itinerary_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    page_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(600), nullable=False)
    image_link: Mapped[str] = mapped_column(String(2000), nullable=False)

    page: Mapped[PreferencePage] = relationship(back_populates="entries")
    response: Mapped[PreferenceResponse | None] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
        lazy="selectin",
    )


class PreferenceResponse(TimestampMixin, Base):
    __tablename__ = "preference_responses"
    __table_args__ = (
        UniqueConstraint(
            "itinerary_id",
            "item_id",
            name="uq_preference_responses_itinerary_item",
        ),
        CheckConstraint("decision IN ('like', 'dislike')", name="preference_decision"),
        ForeignKeyConstraint(
            ["itinerary_id", "item_id"],
            ["preference_items.itinerary_id", "preference_items.id"],
            name="fk_preference_responses_itinerary_item",
            ondelete="CASCADE",
        ),
        Index("ix_preference_responses_itinerary_id", "itinerary_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    itinerary_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    item_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    decision: Mapped[PreferenceDecision] = mapped_column(
        _enum_type(PreferenceDecision, "preference_decision", 8),
        nullable=False,
    )

    item: Mapped[PreferenceItem] = relationship(back_populates="response")


class Stop(TimestampMixin, Base):
    __tablename__ = "stops"
    __table_args__ = (
        UniqueConstraint("itinerary_id", "position", name="uq_stops_itinerary_position"),
        UniqueConstraint("itinerary_id", "id", name="uq_stops_itinerary_id_id"),
        CheckConstraint("position > 0 AND position <= 10", name="ck_stops_position_range"),
        CheckConstraint("start_time < end_time", name="ck_stops_time_window"),
        CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL)",
            name="ck_stops_coordinates_together",
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_stops_latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_stops_longitude_range",
        ),
        Index("ix_stops_itinerary_id", "itinerary_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    itinerary_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("itineraries.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reason_to_visit: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str | None] = mapped_column(String(300))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    cala_entity_id: Mapped[str | None] = mapped_column(String(200))
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    links: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
    evidence_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_confidence: Mapped[float | None] = mapped_column(Float)

    itinerary: Mapped[Itinerary] = relationship(back_populates="stops")


class MediaAsset(TimestampMixin, Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="ck_media_assets_attempt_nonnegative"),
        CheckConstraint("width IS NULL OR width > 0", name="ck_media_assets_width_positive"),
        CheckConstraint("height IS NULL OR height > 0", name="ck_media_assets_height_positive"),
        CheckConstraint("role IN ('hero', 'stop_illustration')", name="media_role"),
        CheckConstraint(
            "status IN ('pending', 'queued', 'generating', 'ready', 'failed')",
            name="media_status",
        ),
        ForeignKeyConstraint(
            ["itinerary_id", "stop_id"],
            ["stops.itinerary_id", "stops.id"],
            name="fk_media_assets_itinerary_stop",
            ondelete="CASCADE",
        ),
        UniqueConstraint("itinerary_id", "id", name="uq_media_assets_itinerary_id_id"),
        Index(
            "uq_media_assets_itinerary_hero",
            "itinerary_id",
            unique=True,
            postgresql_where=text("role = 'hero' AND stop_id IS NULL"),
        ),
        Index("ix_media_assets_itinerary_id", "itinerary_id"),
        Index("ix_media_assets_stop_id", "stop_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    itinerary_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("itineraries.id", ondelete="CASCADE"),
        nullable=False,
    )
    stop_id: Mapped[UUID | None] = mapped_column(Uuid)
    role: Mapped[MediaRole] = mapped_column(
        _enum_type(MediaRole, "media_role", 24),
        nullable=False,
    )
    status: Mapped[MediaStatus] = mapped_column(
        _enum_type(MediaStatus, "media_status", 16),
        nullable=False,
        default=MediaStatus.PENDING,
        server_default=MediaStatus.PENDING.value,
    )
    provider: Mapped[str | None] = mapped_column(String(40))
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    url: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(100))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    alt_text: Mapped[str | None] = mapped_column(String(500))
    model_id: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(500))

    itinerary: Mapped[Itinerary] = relationship(back_populates="media_assets")


class GenerationRun(TimestampMixin, Base):
    __tablename__ = "generation_runs"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_generation_runs_dedupe_key"),
        CheckConstraint("attempt_count >= 0", name="ck_generation_runs_attempt_nonnegative"),
        CheckConstraint("max_attempts > 0", name="ck_generation_runs_max_attempts_positive"),
        CheckConstraint("lease_version >= 0", name="ck_generation_runs_lease_version_nonnegative"),
        CheckConstraint(
            "stage IN ('orchestration', 'research', 'planning', 'illustration')",
            name="generation_stage",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'retry_wait', 'succeeded', 'failed')",
            name="generation_run_status",
        ),
        ForeignKeyConstraint(
            ["itinerary_id", "media_asset_id"],
            ["media_assets.itinerary_id", "media_assets.id"],
            name="fk_generation_runs_itinerary_media_asset",
            ondelete="CASCADE",
        ),
        Index(
            "ix_generation_runs_claimable",
            "status",
            "available_at",
            "queued_at",
        ),
        Index("ix_generation_runs_itinerary_id", "itinerary_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    itinerary_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("itineraries.id", ondelete="CASCADE"),
        nullable=False,
    )
    media_asset_id: Mapped[UUID | None] = mapped_column(Uuid)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    stage: Mapped[GenerationStage] = mapped_column(
        _enum_type(GenerationStage, "generation_stage", 24),
        nullable=False,
        default=GenerationStage.ORCHESTRATION,
        server_default=GenerationStage.ORCHESTRATION.value,
    )
    status: Mapped[GenerationRunStatus] = mapped_column(
        _enum_type(GenerationRunStatus, "generation_run_status", 16),
        nullable=False,
        default=GenerationRunStatus.QUEUED,
        server_default=GenerationRunStatus.QUEUED.value,
    )
    provider: Mapped[str | None] = mapped_column(String(40))
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    model_id: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    schema_version: Mapped[str | None] = mapped_column(String(80))
    usage_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    checkpoint_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(500))
    error_retryable: Mapped[bool | None] = mapped_column(Boolean)

    itinerary: Mapped[Itinerary] = relationship(back_populates="generation_runs")
