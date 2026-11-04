"""add turn assistance metadata

Revision ID: b7e4c1a92f10
Revises: a3156625594d
Create Date: 2026-11-04 12:45:00.000000

Additive only: nullable columns for Guided assistance tracking.
Does not alter or delete existing turn rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b7e4c1a92f10"
down_revision: str | Sequence[str] | None = "a3156625594d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "session_turns",
        sa.Column("assistance_level", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "session_turns",
        sa.Column("assistance_events", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "session_turns",
        sa.Column("assisted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("session_turns", "assisted")
    op.drop_column("session_turns", "assistance_events")
    op.drop_column("session_turns", "assistance_level")
