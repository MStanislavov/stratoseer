"""Admin endpoints: user management."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.db import get_db
from app.models.profile import UserProfile
from app.models.run import Run
from app.models.user import User
from app.schemas.admin import AdminUserRead, PaginatedUsers

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=PaginatedUsers)
async def list_users(
    _user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """List all users with profile counts (admin only)."""
    # Total count
    total_result = await db.execute(select(func.count()).select_from(User))
    total = total_result.scalar() or 0

    # Users with profile and run counts
    profile_count_sub = (
        select(
            UserProfile.owner_id,
            func.count().label("profile_count"),
        )
        .group_by(UserProfile.owner_id)
        .subquery()
    )

    run_count_sub = (
        select(
            UserProfile.owner_id,
            func.count().label("run_count"),
        )
        .join(Run, Run.profile_id == UserProfile.id)
        .group_by(UserProfile.owner_id)
        .subquery()
    )

    query = (
        select(
            User,
            func.coalesce(profile_count_sub.c.profile_count, 0).label("profile_count"),
            func.coalesce(run_count_sub.c.run_count, 0).label("run_count"),
        )
        .outerjoin(profile_count_sub, User.id == profile_count_sub.c.owner_id)
        .outerjoin(run_count_sub, User.id == run_count_sub.c.owner_id)
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(query)
    rows = result.all()

    users = [
        AdminUserRead(
            id=row.User.id,
            first_name=row.User.first_name,
            last_name=row.User.last_name,
            email=row.User.email,
            role=row.User.role,
            email_verified=row.User.email_verified,
            created_at=row.User.created_at,
            last_login_at=row.User.last_login_at,
            profile_count=row.profile_count,
            run_count=row.run_count,
        )
        for row in rows
    ]

    return PaginatedUsers(users=users, total=total, page=page, page_size=page_size)
