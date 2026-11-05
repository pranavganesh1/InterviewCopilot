"""add session duration

Revision ID: fffdf1674ed0
Revises: e2b4c6d8f0a1
Create Date: 2026-11-05 00:06:49.290200

Additive: existing rows get duration_minutes=60 (default interview length).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "fffdf1674ed0"
down_revision: str | Sequence[str] | None = "e2b4c6d8f0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interview_sessions",
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
    )
    op.execute("UPDATE interview_sessions SET duration_minutes = 60 WHERE duration_minutes IS NULL")
    op.alter_column(
        "interview_sessions",
        "duration_minutes",
        existing_type=sa.Integer(),
        nullable=False,
        server_default="60",
    )


def downgrade() -> None:
    op.drop_column("interview_sessions", "duration_minutes")
