# Import all models so Base.metadata is populated for create_all / migrations.
from app.models.profile import UserProfile  # noqa: F401
from app.models.run import Run, Artifact  # noqa: F401
from app.models.evidence import EvidenceItem, Claim  # noqa: F401
from app.models.opportunity import Opportunity  # noqa: F401
from app.models.cover_letter import CoverLetter  # noqa: F401
