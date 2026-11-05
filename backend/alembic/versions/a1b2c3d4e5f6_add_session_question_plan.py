"""add question_plan on interview_sessions

Revision ID: a1b2c3d4e5f6
Revises: 06b147513730
Create Date: 2026-11-05 12:30:00.000000

Additive only: nullable JSONB plan of per-turn topic/objective/difficulty slots.
Existing sessions keep NULL and keep today's interviewer behaviour.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "06b147513730"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interview_sessions",
        sa.Column("question_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_sessions", "question_plan")
