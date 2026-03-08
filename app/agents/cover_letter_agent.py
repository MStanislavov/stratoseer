"""Mock cover letter agent: generates a cover letter from CV + JD + extracted requirements."""

from __future__ import annotations

import hashlib
from typing import Any
from datetime import datetime, timezone


class CoverLetterAgent:
    """Phase-1 mock cover letter agent.

    Reads CV content, job description, and opportunity details.
    Produces a structured cover letter with evidence-backed claims.
    No network tools allowed (policy boundary).
    """

    agent_name = "cover_letter"

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        cv_content = state.get("cv_content", "")
        jd_text = state.get("jd_text", "")
        opportunity = state.get("opportunity", {})
        profile_id = state.get("profile_id", "unknown")

        opp_title = opportunity.get("title", "the position")
        opp_source = opportunity.get("source", "Unknown Company")
        opp_description = opportunity.get("description", jd_text)

        # Build evidence items from CV and JD
        now = datetime.now(timezone.utc).isoformat()
        ev_cv_id = f"ev-cv-{profile_id[:8]}"
        ev_jd_id = f"ev-jd-{hashlib.sha256(jd_text.encode()).hexdigest()[:8]}"

        evidence_items: list[dict[str, Any]] = [
            {
                "id": ev_cv_id,
                "type": "cv",
                "url": f"profile://{profile_id}/cv",
                "retrieved_at": now,
                "content_hash": hashlib.sha256(cv_content.encode()).hexdigest(),
                "snippet": cv_content[:200] if cv_content else "No CV provided",
                "metadata": {"source": "user_profile"},
            },
            {
                "id": ev_jd_id,
                "type": "job_description",
                "url": opportunity.get("url", "manual://jd-input"),
                "retrieved_at": now,
                "content_hash": hashlib.sha256(
                    (opp_description or "").encode()
                ).hexdigest(),
                "snippet": (opp_description or jd_text)[:200],
                "metadata": {"source": opp_source},
            },
        ]

        # Mock cover letter content
        cover_letter_content = (
            f"Dear Hiring Manager,\n\n"
            f"I am writing to express my strong interest in the {opp_title} "
            f"position at {opp_source}. Based on my review of the job "
            f"requirements and my professional background, I believe I am "
            f"well-suited for this role.\n\n"
            f"My experience aligns with the key requirements outlined in "
            f"the job description. I bring a combination of technical skills "
            f"and domain expertise that would enable me to make an immediate "
            f"impact in this position.\n\n"
            f"I am confident that my background and skills make me an "
            f"excellent candidate for this opportunity. I look forward to "
            f"discussing how I can contribute to your team.\n\n"
            f"Sincerely,\n"
            f"[Candidate]"
        )

        # Claims with evidence references
        claims: list[dict[str, Any]] = [
            {
                "claim_text": f"Candidate is qualified for {opp_title}",
                "requires_evidence": True,
                "evidence_ids": [ev_cv_id, ev_jd_id],
                "confidence": 0.80,
            },
            {
                "claim_text": (
                    f"Candidate's experience aligns with requirements at {opp_source}"
                ),
                "requires_evidence": True,
                "evidence_ids": [ev_cv_id, ev_jd_id],
                "confidence": 0.75,
            },
        ]

        return {
            "cover_letter_content": cover_letter_content,
            "claims": claims,
            "evidence_items": evidence_items,
            "errors": state.get("errors", []),
        }
