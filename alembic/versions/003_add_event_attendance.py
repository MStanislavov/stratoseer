"""add event attendance field

Revision ID: 003
Revises: 002
Create Date: 2026-04-04

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("event_attendance", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "event_attendance")
