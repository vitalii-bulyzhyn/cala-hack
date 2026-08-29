"""Replace natural request text with city and tags.

Revision ID: 20260829_0003
Revises: 20260829_0002
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260829_0003"
down_revision: str | None = "20260829_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("itineraries", sa.Column("city", sa.String(length=160), nullable=True))
    op.add_column(
        "itineraries",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE itineraries "
        "SET city = left(COALESCE(destination, request_text), 160) "
        "WHERE city IS NULL"
    )
    op.alter_column("itineraries", "city", existing_type=sa.String(length=160), nullable=False)
    op.alter_column("itineraries", "tags", server_default=None)
    op.drop_column("itineraries", "request_text")


def downgrade() -> None:
    op.add_column(
        "itineraries",
        sa.Column("request_text", sa.String(length=1000), nullable=True),
    )
    op.execute("UPDATE itineraries SET request_text = city WHERE request_text IS NULL")
    op.alter_column(
        "itineraries",
        "request_text",
        existing_type=sa.String(length=1000),
        nullable=False,
    )
    op.drop_column("itineraries", "tags")
    op.drop_column("itineraries", "city")
