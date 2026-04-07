"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-19

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# Foreign key target constants
_FK_USER_PROFILES_ID = "user_profiles.id"
_FK_RUNS_ID = "runs.id"

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("targets", sa.Text(), nullable=True),
        sa.Column("constraints", sa.Text(), nullable=True),
        sa.Column("skills", sa.Text(), nullable=True),
        sa.Column("cv_path", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey(_FK_USER_PROFILES_ID),
            nullable=False,
        ),
        sa.Column("mode", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("verifier_status", sa.String(50), nullable=True),
        sa.Column("audit_path", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "job_opportunities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey(_FK_USER_PROFILES_ID),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(36), sa.ForeignKey(_FK_RUNS_ID), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company", sa.String(500), nullable=True),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("salary_range", sa.String(200), nullable=True),
        sa.Column("source_query", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_job_opportunities_profile_run",
        "job_opportunities",
        ["profile_id", "run_id"],
    )

    op.create_table(
        "certifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey(_FK_USER_PROFILES_ID),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(36), sa.ForeignKey(_FK_RUNS_ID), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("provider", sa.String(500), nullable=True),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cost", sa.String(200), nullable=True),
        sa.Column("duration", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_certifications_profile_run",
        "certifications",
        ["profile_id", "run_id"],
    )

    op.create_table(
        "courses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey(_FK_USER_PROFILES_ID),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(36), sa.ForeignKey(_FK_RUNS_ID), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("platform", sa.String(500), nullable=True),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cost", sa.String(200), nullable=True),
        sa.Column("duration", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_courses_profile_run", "courses", ["profile_id", "run_id"])

    op.create_table(
        "events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey(_FK_USER_PROFILES_ID),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(36), sa.ForeignKey(_FK_RUNS_ID), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("organizer", sa.String(500), nullable=True),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_date", sa.String(200), nullable=True),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_events_profile_run", "events", ["profile_id", "run_id"])

    op.create_table(
        "groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey(_FK_USER_PROFILES_ID),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(36), sa.ForeignKey(_FK_RUNS_ID), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("platform", sa.String(500), nullable=True),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("member_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_groups_profile_run", "groups", ["profile_id", "run_id"])

    op.create_table(
        "trends",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey(_FK_USER_PROFILES_ID),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(36), sa.ForeignKey(_FK_RUNS_ID), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("category", sa.String(500), nullable=True),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("relevance", sa.String(500), nullable=True),
        sa.Column("source", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_trends_profile_run", "trends", ["profile_id", "run_id"])

    op.create_table(
        "cover_letters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey(_FK_USER_PROFILES_ID),
            nullable=False,
        ),
        sa.Column(
            "job_opportunity_id",
            sa.String(36),
            sa.ForeignKey("job_opportunities.id"),
            nullable=True,
        ),
        sa.Column("run_id", sa.String(36), sa.ForeignKey(_FK_RUNS_ID), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("cover_letters")
    op.drop_index("ix_trends_profile_run", table_name="trends")
    op.drop_table("trends")
    op.drop_index("ix_groups_profile_run", table_name="groups")
    op.drop_table("groups")
    op.drop_index("ix_events_profile_run", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_courses_profile_run", table_name="courses")
    op.drop_table("courses")
    op.drop_index("ix_certifications_profile_run", table_name="certifications")
    op.drop_table("certifications")
    op.drop_index("ix_job_opportunities_profile_run", table_name="job_opportunities")
    op.drop_table("job_opportunities")
    op.drop_table("runs")
    op.drop_table("user_profiles")
