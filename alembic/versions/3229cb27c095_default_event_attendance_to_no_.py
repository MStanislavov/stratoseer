"""default event_attendance to no preference

Revision ID: 3229cb27c095
Revises: e9bacf5ec5f4
Create Date: 2026-04-05 18:32:32.939702

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3229cb27c095"
down_revision: Union[str, None] = "e9bacf5ec5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Set server default for new rows
    op.alter_column(
        "user_profiles",
        "event_attendance",
        existing_type=sa.String(20),
        server_default="no preference",
        existing_nullable=True,
    )
    # Backfill existing NULL rows
    op.execute(
        "UPDATE user_profiles SET event_attendance = 'no preference' WHERE event_attendance IS NULL"
    )


def downgrade() -> None:
    op.alter_column(
        "user_profiles",
        "event_attendance",
        existing_type=sa.String(20),
        server_default=None,
        existing_nullable=True,
    )
