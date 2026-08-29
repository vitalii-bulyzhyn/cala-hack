"""Add preference-learning pages, items, and responses.

Revision ID: 20260829_0004
Revises: 20260829_0003
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0004"
down_revision: str | None = "20260829_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("itinerary_status", "itineraries", type_="check")
    op.alter_column(
        "itineraries",
        "status",
        existing_type=sa.String(length=16),
        type_=sa.String(length=24),
        existing_nullable=False,
        server_default="learning_preferences",
    )
    op.create_check_constraint(
        "itinerary_status",
        "itineraries",
        "status IN ('learning_preferences', 'queued', 'researching', 'planning', "
        "'illustrating', 'ready', 'partial', 'failed')",
    )

    op.create_table(
        "preference_learning_sessions",
        sa.Column("itinerary_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="collecting", nullable=False),
        sa.Column("algorithm_version", sa.String(length=80), nullable=True),
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
            "status IN ('collecting', 'completed')",
            name="preference_learning_status",
        ),
        sa.ForeignKeyConstraint(["itinerary_id"], ["itineraries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("itinerary_id"),
    )
    op.create_table(
        "preference_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("itinerary_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("layout", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
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
        sa.CheckConstraint("layout IN ('single', 'pair')", name="preference_page_layout"),
        sa.CheckConstraint("position > 0", name="ck_preference_pages_position_positive"),
        sa.CheckConstraint("source IN ('initial', 'adaptive')", name="preference_page_source"),
        sa.ForeignKeyConstraint(
            ["itinerary_id"],
            ["preference_learning_sessions.itinerary_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "itinerary_id",
            "id",
            name="uq_preference_pages_itinerary_id_id",
        ),
        sa.UniqueConstraint(
            "itinerary_id",
            "position",
            name="uq_preference_pages_itinerary_position",
        ),
    )
    op.create_index(
        "ix_preference_pages_itinerary_id",
        "preference_pages",
        ["itinerary_id"],
    )
    op.create_table(
        "preference_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("itinerary_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=600), nullable=False),
        sa.Column("image_link", sa.String(length=2000), nullable=False),
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
        sa.CheckConstraint("position IN (1, 2)", name="ck_preference_items_position_range"),
        sa.ForeignKeyConstraint(
            ["itinerary_id", "page_id"],
            ["preference_pages.itinerary_id", "preference_pages.id"],
            name="fk_preference_items_itinerary_page",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "itinerary_id",
            "id",
            name="uq_preference_items_itinerary_id_id",
        ),
        sa.UniqueConstraint("page_id", "position", name="uq_preference_items_page_position"),
    )
    op.create_index(
        "ix_preference_items_itinerary_id",
        "preference_items",
        ["itinerary_id"],
    )
    op.create_index("ix_preference_items_page_id", "preference_items", ["page_id"])
    op.create_table(
        "preference_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("itinerary_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=8), nullable=False),
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
        sa.CheckConstraint("decision IN ('like', 'dislike')", name="preference_decision"),
        sa.ForeignKeyConstraint(
            ["itinerary_id", "item_id"],
            ["preference_items.itinerary_id", "preference_items.id"],
            name="fk_preference_responses_itinerary_item",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "itinerary_id",
            "item_id",
            name="uq_preference_responses_itinerary_item",
        ),
    )
    op.create_index(
        "ix_preference_responses_itinerary_id",
        "preference_responses",
        ["itinerary_id"],
    )

    op.execute(
        "INSERT INTO preference_learning_sessions "
        "(itinerary_id, status, algorithm_version, completed_at) "
        "SELECT id, 'completed', 'legacy-preference-bypass', "
        "COALESCE(completed_at, updated_at) FROM itineraries"
    )


def downgrade() -> None:
    op.drop_index("ix_preference_responses_itinerary_id", table_name="preference_responses")
    op.drop_table("preference_responses")
    op.drop_index("ix_preference_items_page_id", table_name="preference_items")
    op.drop_index("ix_preference_items_itinerary_id", table_name="preference_items")
    op.drop_table("preference_items")
    op.drop_index("ix_preference_pages_itinerary_id", table_name="preference_pages")
    op.drop_table("preference_pages")
    op.drop_table("preference_learning_sessions")

    op.drop_constraint("itinerary_status", "itineraries", type_="check")
    op.execute("UPDATE itineraries SET status = 'queued' WHERE status = 'learning_preferences'")
    op.alter_column(
        "itineraries",
        "status",
        existing_type=sa.String(length=24),
        type_=sa.String(length=16),
        existing_nullable=False,
        server_default="queued",
    )
    op.create_check_constraint(
        "itinerary_status",
        "itineraries",
        "status IN ('queued', 'researching', 'planning', 'illustrating', "
        "'ready', 'partial', 'failed')",
    )
