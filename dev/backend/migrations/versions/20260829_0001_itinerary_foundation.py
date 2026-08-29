"""Create itinerary persistence and generation queue state.

Revision ID: 20260829_0001
Revises:
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

itinerary_status = sa.Enum(
    "queued",
    "researching",
    "planning",
    "illustrating",
    "ready",
    "partial",
    "failed",
    name="itinerary_status",
    native_enum=False,
    create_constraint=True,
    length=16,
)
media_role = sa.Enum(
    "hero",
    "stop_illustration",
    name="media_role",
    native_enum=False,
    create_constraint=True,
    length=24,
)
media_status = sa.Enum(
    "pending",
    "queued",
    "generating",
    "ready",
    "failed",
    name="media_status",
    native_enum=False,
    create_constraint=True,
    length=16,
)
generation_stage = sa.Enum(
    "orchestration",
    "research",
    "planning",
    "illustration",
    name="generation_stage",
    native_enum=False,
    create_constraint=True,
    length=24,
)
generation_run_status = sa.Enum(
    "queued",
    "running",
    "retry_wait",
    "succeeded",
    "failed",
    name="generation_run_status",
    native_enum=False,
    create_constraint=True,
    length=16,
)


def upgrade() -> None:
    op.create_table(
        "itineraries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requested_city", sa.String(length=120), nullable=False),
        sa.Column("normalized_city", sa.String(length=360), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=True),
        sa.Column("status", itinerary_status, server_default="queued", nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("error_retryable", sa.Boolean(), nullable=True),
        sa.Column("error_request_id", sa.String(length=80), nullable=True),
        sa.Column("state_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state_version >= 0",
            name="ck_itineraries_state_version_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key_hash",
            name="uq_itineraries_idempotency_key_hash",
        ),
    )
    op.create_index(
        "ix_itineraries_normalized_city",
        "itineraries",
        ["normalized_city"],
        unique=False,
    )
    op.create_index(
        "ix_itineraries_status_created_at",
        "itineraries",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "stops",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("itinerary_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reason_to_visit", sa.Text(), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("cala_entity_id", sa.String(length=200), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("evidence_retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL)",
            name="ck_stops_coordinates_together",
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_stops_latitude_range",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_stops_longitude_range",
        ),
        sa.CheckConstraint(
            "position > 0 AND position <= 10",
            name="ck_stops_position_range",
        ),
        sa.CheckConstraint("start_time < end_time", name="ck_stops_time_window"),
        sa.ForeignKeyConstraint(["itinerary_id"], ["itineraries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "itinerary_id",
            "id",
            name="uq_stops_itinerary_id_id",
        ),
        sa.UniqueConstraint(
            "itinerary_id",
            "position",
            name="uq_stops_itinerary_position",
        ),
    )
    op.create_index("ix_stops_itinerary_id", "stops", ["itinerary_id"], unique=False)

    op.create_table(
        "media_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("itinerary_id", sa.Uuid(), nullable=False),
        sa.Column("stop_id", sa.Uuid(), nullable=True),
        sa.Column("role", media_role, nullable=False),
        sa.Column("status", media_status, server_default="pending", nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("provider_request_id", sa.String(length=200), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(length=500), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("alt_text", sa.String(length=500), nullable=True),
        sa.Column("model_id", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_media_assets_attempt_nonnegative",
        ),
        sa.CheckConstraint(
            "height IS NULL OR height > 0",
            name="ck_media_assets_height_positive",
        ),
        sa.CheckConstraint(
            "width IS NULL OR width > 0",
            name="ck_media_assets_width_positive",
        ),
        sa.ForeignKeyConstraint(
            ["itinerary_id", "stop_id"],
            ["stops.itinerary_id", "stops.id"],
            name="fk_media_assets_itinerary_stop",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["itinerary_id"], ["itineraries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "itinerary_id",
            "id",
            name="uq_media_assets_itinerary_id_id",
        ),
    )
    op.create_index(
        "ix_media_assets_itinerary_id",
        "media_assets",
        ["itinerary_id"],
        unique=False,
    )
    op.create_index("ix_media_assets_stop_id", "media_assets", ["stop_id"], unique=False)

    op.create_table(
        "generation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("itinerary_id", sa.Uuid(), nullable=False),
        sa.Column("media_asset_id", sa.Uuid(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column(
            "stage",
            generation_stage,
            server_default="orchestration",
            nullable=False,
        ),
        sa.Column("status", generation_run_status, server_default="queued", nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=200), nullable=True),
        sa.Column("lease_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_request_id", sa.String(length=200), nullable=True),
        sa.Column("model_id", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("schema_version", sa.String(length=80), nullable=True),
        sa.Column("usage_data", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("error_retryable", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_generation_runs_attempt_nonnegative",
        ),
        sa.CheckConstraint(
            "lease_version >= 0",
            name="ck_generation_runs_lease_version_nonnegative",
        ),
        sa.CheckConstraint(
            "max_attempts > 0",
            name="ck_generation_runs_max_attempts_positive",
        ),
        sa.ForeignKeyConstraint(["itinerary_id"], ["itineraries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["itinerary_id", "media_asset_id"],
            ["media_assets.itinerary_id", "media_assets.id"],
            name="fk_generation_runs_itinerary_media_asset",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_generation_runs_dedupe_key"),
    )
    op.create_index(
        "ix_generation_runs_claimable",
        "generation_runs",
        ["status", "available_at", "queued_at"],
        unique=False,
    )
    op.create_index(
        "ix_generation_runs_itinerary_id",
        "generation_runs",
        ["itinerary_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_generation_runs_itinerary_id", table_name="generation_runs")
    op.drop_index("ix_generation_runs_claimable", table_name="generation_runs")
    op.drop_table("generation_runs")
    op.drop_index("ix_media_assets_stop_id", table_name="media_assets")
    op.drop_index("ix_media_assets_itinerary_id", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_index("ix_stops_itinerary_id", table_name="stops")
    op.drop_table("stops")
    op.drop_index("ix_itineraries_status_created_at", table_name="itineraries")
    op.drop_index("ix_itineraries_normalized_city", table_name="itineraries")
    op.drop_table("itineraries")
