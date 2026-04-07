"""rename preferred_titles to preferred_title (singular string)

Revision ID: 012_preferred_title_singular
Revises: 011_drop_experience_level
Create Date: 2026-04-07

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "012_preferred_title_singular"
down_revision: Union[str, None] = "011_drop_experience_level"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("preferred_title", sa.String(200), nullable=True))

    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        op.execute(
            "UPDATE user_profiles SET preferred_title = json_extract(preferred_titles, '$[0]') "
            "WHERE preferred_titles IS NOT NULL"
        )
    else:
        op.execute(
            "UPDATE user_profiles SET preferred_title = preferred_titles::json->>0 "
            "WHERE preferred_titles IS NOT NULL"
        )

    op.drop_column("user_profiles", "preferred_titles")


def downgrade() -> None:
    op.add_column("user_profiles", sa.Column("preferred_titles", sa.Text(), nullable=True))

    op.execute(
        "UPDATE user_profiles SET preferred_titles = '[\"' || preferred_title || '\"]' "
        "WHERE preferred_title IS NOT NULL"
    )

    op.drop_column("user_profiles", "preferred_title")
