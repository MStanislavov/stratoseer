"""add_user_api_key_and_free_runs_used

Revision ID: f1b31de28cff
Revises: 009_add_cv_summary_cache
Create Date: 2026-04-06 18:45:12.358149

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1b31de28cff"
down_revision: Union[str, None] = "009_add_cv_summary_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("encrypted_api_key", sa.Text(), nullable=True))
    op.add_column(
        "users", sa.Column("free_runs_used", sa.Integer(), server_default="0", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("users", "free_runs_used")
    op.drop_column("users", "encrypted_api_key")
