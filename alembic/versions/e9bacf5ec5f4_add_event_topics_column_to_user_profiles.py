"""add event_topics column to user_profiles

Revision ID: e9bacf5ec5f4
Revises: 005
Create Date: 2026-04-05 13:36:18.302109

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9bacf5ec5f4"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("event_topics", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "event_topics")
