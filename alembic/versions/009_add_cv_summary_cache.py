"""Add cv_summary and cv_summary_hash to user_profiles

Revision ID: 009_add_cv_summary_cache
Revises: 008_add_users_auth
Create Date: 2026-04-06

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "009_add_cv_summary_cache"
down_revision: Union[str, None] = "008_add_users_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("cv_summary", sa.Text(), nullable=True))
    op.add_column("user_profiles", sa.Column("cv_summary_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "cv_summary_hash")
    op.drop_column("user_profiles", "cv_summary")
