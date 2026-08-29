"""Use authoritative per-city journal-entry inventories.

Revision ID: 20260829_0006
Revises: 20260829_0005
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0006"
down_revision: str | None = "20260829_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "preference_items",
        "image_link",
        existing_type=sa.String(length=2000),
        nullable=True,
    )
    op.add_column("preference_items", sa.Column("cala_entity_id", sa.String(200)))
    op.add_column("preference_items", sa.Column("cala_entity_type", sa.String(80)))
    # Category names changed with the authoritative inventory. Rebuild from durable
    # responses on the next feedback/completion transaction instead of translating
    # probabilistic evidence between different arms.
    op.execute("UPDATE preference_learning_sessions SET algorithm_state = NULL")


def downgrade() -> None:
    # Old schemas cannot represent text-only entries. Remove their complete issued
    # pages (and cascading items/responses) before restoring the NOT NULL contract.
    op.execute(
        "DELETE FROM preference_pages WHERE id IN "
        "(SELECT DISTINCT page_id FROM preference_items WHERE image_link IS NULL)"
    )
    op.drop_column("preference_items", "cala_entity_type")
    op.drop_column("preference_items", "cala_entity_id")
    op.alter_column(
        "preference_items",
        "image_link",
        existing_type=sa.String(length=2000),
        nullable=False,
    )
    op.execute("UPDATE preference_learning_sessions SET algorithm_state = NULL")
