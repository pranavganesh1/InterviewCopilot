"""add evaluation_detail jsonb on session_turns

Revision ID: c8f2a91d4e30
Revises: b7e4c1a92f10
Create Date: 2026-11-04 13:20:00.000000

Additive only: stores post-submit evaluation extras (explanation, complexity, code).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c8f2a91d4e30"
down_revision: str | Sequence[str] | None = "b7e4c1a92f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "session_turns",
        sa.Column("evaluation_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session_turns", "evaluation_detail")
