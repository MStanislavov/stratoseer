"""Add users and refresh_tokens tables, add owner_id to user_profiles

Revision ID: 008_add_users_auth
Revises: 3229cb27c095
Create Date: 2026-04-06

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "008_add_users_auth"
down_revision: Union[str, None] = "3229cb27c095"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("google_id", sa.String(255), nullable=True),
        sa.Column("email_verified", sa.Boolean(), server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)

    # 2. Create refresh_tokens table
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)

    # 3. Add owner_id to user_profiles (nullable first for data migration)
    op.add_column("user_profiles", sa.Column("owner_id", sa.String(36), nullable=True))

    # 4. Create a bootstrap admin user and assign existing profiles
    admin_id = str(uuid.uuid4())
    op.execute(
        sa.text(
            "INSERT INTO users (id, first_name, last_name, email, password_hash, role, email_verified, created_at) "
            "VALUES (:id, :first, :last, :email, :pw_hash, :role, true, now())"
        ).bindparams(
            id=admin_id,
            first="Admin",
            last="User",
            email="admin@stratoseer.local",
            pw_hash="$2b$12$placeholder.hash.will.require.password.reset",
            role="admin",
        )
    )

    # Assign all existing profiles to the bootstrap admin
    op.execute(
        sa.text("UPDATE user_profiles SET owner_id = :admin_id").bindparams(admin_id=admin_id)
    )

    # 5. Make owner_id NOT NULL and add FK constraint
    op.alter_column("user_profiles", "owner_id", nullable=False)
    op.create_foreign_key(
        "fk_user_profiles_owner_id",
        "user_profiles",
        "users",
        ["owner_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_user_profiles_owner_id", "user_profiles", type_="foreignkey")
    op.drop_column("user_profiles", "owner_id")
    op.drop_table("refresh_tokens")
    # Delete bootstrap admin user
    op.execute(sa.text("DELETE FROM users WHERE email = 'admin@stratoseer.local'"))
    op.drop_table("users")
