"""Admin-facing schemas for user management and paginated listings."""

from datetime import datetime

from pydantic import BaseModel


class AdminUserRead(BaseModel):
    """Read-only admin view of a user account with usage statistics.

    Use this schema when returning user records to admin endpoints that
    need visibility into profile and run counts alongside standard user fields.
    """

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
    """Paginated container for admin user listings.

    Use this schema as the response model for paginated user queries,
    wrapping a list of AdminUserRead items with pagination metadata.
    """

    users: list[AdminUserRead]
    total: int
    page: int
    page_size: int
