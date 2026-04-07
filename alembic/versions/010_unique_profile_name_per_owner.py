"""Add unique constraint on (owner_id, name) for user_profiles.

Revision ID: 010_uq_profile_name
Revises: f1b31de28cff
Create Date: 2026-04-06

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010_uq_profile_name"
down_revision: Union[str, None] = "f1b31de28cff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_profile_owner_name", "user_profiles", ["owner_id", "name"])


def downgrade() -> None:
    op.drop_constraint("uq_profile_owner_name", "user_profiles", type_="unique")
