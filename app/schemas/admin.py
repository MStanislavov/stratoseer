from datetime import datetime

from pydantic import BaseModel


class AdminUserRead(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    role: str
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None = None
    profile_count: int = 0
    run_count: int = 0


class PaginatedUsers(BaseModel):
    users: list[AdminUserRead]
    total: int
    page: int
    page_size: int
