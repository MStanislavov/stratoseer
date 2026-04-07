"""drop experience_level from user_profiles

Revision ID: 011_drop_experience_level
Revises: a68f0bc2edf8
Create Date: 2026-04-07

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011_drop_experience_level"
down_revision: Union[str, None] = "a68f0bc2edf8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("user_profiles", "experience_level")


def downgrade() -> None:
    op.add_column("user_profiles", sa.Column("experience_level", sa.String(20), nullable=True))
