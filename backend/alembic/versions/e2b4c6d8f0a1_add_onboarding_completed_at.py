"""add onboarding_completed_at on users

Revision ID: e2b4c6d8f0a1
Revises: d1a3b5c7e9f0
Create Date: 2026-11-04 14:30:00.000000

Additive only: records when the user finished onboarding (Tracks unlock).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2b4c6d8f0a1"
down_revision: str | Sequence[str] | None = "d1a3b5c7e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")
