"""move audit logs and bundles from disk to postgres

Revision ID: a68f0bc2edf8
Revises: 010_uq_profile_name
Create Date: 2026-04-07 00:32:53.864447

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a68f0bc2edf8"
down_revision: Union[str, None] = "010_uq_profile_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_run_id"), "audit_events", ["run_id"], unique=False)

    op.create_table(
        "run_bundles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_run_bundles_run_id"), "run_bundles", ["run_id"], unique=True)

    op.drop_column("runs", "audit_path")


def downgrade() -> None:
    op.add_column("runs", sa.Column("audit_path", sa.VARCHAR(length=500), nullable=True))
    op.drop_index(op.f("ix_run_bundles_run_id"), table_name="run_bundles")
    op.drop_table("run_bundles")
    op.drop_index(op.f("ix_audit_events_run_id"), table_name="audit_events")
    op.drop_table("audit_events")
