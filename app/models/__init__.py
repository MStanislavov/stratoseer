"""SQLAlchemy model package for all persistent database entities.

Importing this package ensures every model is registered with
``Base.metadata`` so that ``create_all`` and Alembic migrations pick up
all tables automatically.
"""

# Import all models so Base.metadata is populated for create_all / migrations.
from app.models.audit_event import AuditEventRecord  # noqa: F401
from app.models.certification import Certification  # noqa: F401
from app.models.course import Course  # noqa: F401
from app.models.cover_letter import CoverLetter  # noqa: F401
from app.models.event import Event  # noqa: F401
from app.models.group import Group  # noqa: F401
from app.models.job_opportunity import JobOpportunity  # noqa: F401
from app.models.profile import UserProfile  # noqa: F401
from app.models.refresh_token import RefreshToken  # noqa: F401
from app.models.run import Run  # noqa: F401
from app.models.run_bundle import RunBundle  # noqa: F401
from app.models.trend import Trend  # noqa: F401
from app.models.user import User  # noqa: F401
