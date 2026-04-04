"""add structured profile fields

Revision ID: 002
Revises: 001
Create Date: 2026-04-04

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Career & Job fields
    op.add_column("user_profiles", sa.Column("preferred_titles", sa.Text(), nullable=True))
    op.add_column("user_profiles", sa.Column("experience_level", sa.String(20), nullable=True))
    op.add_column("user_profiles", sa.Column("industries", sa.Text(), nullable=True))
    op.add_column("user_profiles", sa.Column("locations", sa.Text(), nullable=True))
    op.add_column("user_profiles", sa.Column("work_arrangement", sa.String(20), nullable=True))
    # Learning & Certification fields
    op.add_column("user_profiles", sa.Column("target_certifications", sa.Text(), nullable=True))
    op.add_column("user_profiles", sa.Column("learning_budget", sa.String(50), nullable=True))
    op.add_column("user_profiles", sa.Column("learning_format", sa.String(20), nullable=True))
    op.add_column("user_profiles", sa.Column("time_commitment", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "time_commitment")
    op.drop_column("user_profiles", "learning_format")
    op.drop_column("user_profiles", "learning_budget")
    op.drop_column("user_profiles", "target_certifications")
    op.drop_column("user_profiles", "work_arrangement")
    op.drop_column("user_profiles", "locations")
    op.drop_column("user_profiles", "industries")
    op.drop_column("user_profiles", "experience_level")
    op.drop_column("user_profiles", "preferred_titles")
