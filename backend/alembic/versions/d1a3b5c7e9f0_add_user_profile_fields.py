"""add optional professional profile fields on users

Revision ID: d1a3b5c7e9f0
Revises: c8f2a91d4e30
Create Date: 2026-11-04 14:00:00.000000

Additive only: title, introduction, skills (JSONB), education.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d1a3b5c7e9f0"
down_revision: str | Sequence[str] | None = "c8f2a91d4e30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("professional_title", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("introduction", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "skills",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("users", sa.Column("education", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "education")
    op.drop_column("users", "skills")
    op.drop_column("users", "introduction")
    op.drop_column("users", "professional_title")
