"""Store natural-language requests and public place links.

Revision ID: 20260829_0002
Revises: 20260829_0001
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0002"
down_revision: str | None = "20260829_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "itineraries",
        "requested_city",
        new_column_name="request_text",
        existing_type=sa.String(length=120),
        type_=sa.String(length=1000),
        existing_nullable=False,
    )
    op.drop_index("ix_itineraries_normalized_city", table_name="itineraries")
    op.alter_column(
        "itineraries",
        "normalized_city",
        new_column_name="destination",
        existing_type=sa.String(length=360),
        type_=sa.String(length=200),
        nullable=True,
    )
    op.create_index("ix_itineraries_destination", "itineraries", ["destination"])
    op.add_column("itineraries", sa.Column("planned_date", sa.Date(), nullable=True))
    op.add_column(
        "itineraries",
        sa.Column("destination_timezone", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "stops",
        sa.Column(
            "links",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
    )
    op.alter_column("stops", "links", server_default=None)
    op.add_column(
        "generation_runs",
        sa.Column("checkpoint_data", sa.JSON(), nullable=True),
    )
    op.create_index(
        "uq_media_assets_itinerary_hero",
        "media_assets",
        ["itinerary_id"],
        unique=True,
        postgresql_where=sa.text("role = 'hero' AND stop_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_media_assets_itinerary_hero", table_name="media_assets")
    op.drop_column("generation_runs", "checkpoint_data")
    op.drop_column("stops", "links")
    op.drop_column("itineraries", "destination_timezone")
    op.drop_column("itineraries", "planned_date")
    op.drop_index("ix_itineraries_destination", table_name="itineraries")
    op.execute(
        "UPDATE itineraries "
        "SET destination = left(lower(request_text), 200) "
        "WHERE destination IS NULL"
    )
    op.alter_column(
        "itineraries",
        "destination",
        new_column_name="normalized_city",
        existing_type=sa.String(length=200),
        type_=sa.String(length=360),
        nullable=False,
    )
    op.create_index(
        "ix_itineraries_normalized_city",
        "itineraries",
        ["normalized_city"],
    )
    op.alter_column(
        "itineraries",
        "request_text",
        new_column_name="requested_city",
        existing_type=sa.String(length=1000),
        type_=sa.String(length=120),
        existing_nullable=False,
        postgresql_using="left(request_text, 120)",
    )
