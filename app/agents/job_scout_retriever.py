"""Mock job scout retriever: returns realistic stub job listings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class JobScoutRetriever:
    """Phase-1 mock retriever. Returns hard-coded job listings.

    Swappable for a real LLM-backed retriever later.
    """

    agent_name = "job_scout_retriever"

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        raw_listings = [
            {
                "title": "Senior Software Engineer",
                "company": "Acme Corp",
                "url": "https://linkedin.com/jobs/senior-swe-acme",
                "description": "Build distributed systems with Python and Go. "
                "Experience with Kubernetes required.",
                "source": "linkedin.com/jobs",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "title": "Cloud Architect",
                "company": "TechStart Inc",
                "url": "https://indeed.com/job/cloud-architect-techstart",
                "description": "Design cloud infrastructure on AWS/GCP. "
                "Lead migration projects for enterprise clients.",
                "source": "indeed.com",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "title": "Staff Engineer - Platform",
                "company": "BigTech Ltd",
                "url": "https://linkedin.com/jobs/staff-eng-bigtech",
                "description": "Lead platform engineering team. "
                "Build internal developer tools and CI/CD pipelines.",
                "source": "linkedin.com/jobs",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        return {"raw_job_listings": raw_listings, "errors": state.get("errors", [])}
