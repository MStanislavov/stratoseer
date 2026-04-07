"""store CV data in database instead of filesystem

Revision ID: 005
Revises: 004
Create Date: 2026-04-05

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("cv_data", sa.LargeBinary(), nullable=True))
    op.add_column("user_profiles", sa.Column("cv_filename", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "cv_filename")
    op.drop_column("user_profiles", "cv_data")
