"""drop learning_budget and time_commitment fields

Revision ID: 004
Revises: 003
Create Date: 2026-04-04

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("user_profiles", "learning_budget")
    op.drop_column("user_profiles", "time_commitment")


def downgrade() -> None:
    op.add_column("user_profiles", sa.Column("time_commitment", sa.String(50), nullable=True))
    op.add_column("user_profiles", sa.Column("learning_budget", sa.String(50), nullable=True))
