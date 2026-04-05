"""Cover letter agent: generates a cover letter from CV + JD."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agents.base import LLMAgent


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting so text reads as plain prose."""
    # Remove headers (### Title -> Title)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    # Remove bullet prefixes
    text = re.sub(r"^[\-\*]\s+", "", text, flags=re.MULTILINE)
    # Collapse multiple newlines into a single space
    text = re.sub(r"\n+", " ", text)
    # Collapse multiple spaces
    text = re.sub(r"  +", " ", text)
    return text.strip()


# Section headers that should NOT be treated as a person's name
_SECTION_HEADERS = frozenset({
    "professional summary", "summary", "experience", "education",
    "skills", "certifications", "projects", "contact", "objective",
    "work experience", "technical skills", "profile", "about",
    "about me", "references", "languages", "interests", "hobbies",
})


def _extract_name_from_cv(cv_text: str) -> str | None:
    """Try to extract the person's name from the first line of CV text.

    CVs typically start with the person's name before any section header.
    Returns None if no plausible name is found.
    """
    if not cv_text or not cv_text.strip():
        return None
    for line in cv_text.strip().splitlines():
        line = re.sub(r"^#{1,6}\s+", "", line).strip()
        line = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", line).strip()
        if not line:
            continue
        normalized = line.lower()
        if normalized in _SECTION_HEADERS:
            continue
        # A name is typically 2-4 short words, all alphabetic
        words = line.split()
        if 2 <= len(words) <= 4 and all(w.isalpha() for w in words):
            return line
        # If the first non-empty, non-header line isn't a name, stop looking
        break
    return None


class CoverLetterAgent(LLMAgent):
    """Generates a tailored cover letter from CV content, job description, and profile data."""

    agent_name = "cover_letter"

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """Generate a cover letter from the CV, JD, and profile information in state."""
        cv_content = state.get("cv_content", "")
        jd_text = state.get("jd_text", "")
        job_opportunity = state.get("job_opportunity", {})
        profile_name = state.get("profile_name", "")
        profile_targets = state.get("profile_targets", [])
        profile_skills = state.get("profile_skills", [])
        profile_constraints = state.get("profile_constraints", [])

        system_prompt = self._get_system_prompt()

        sections = []
        if profile_name:
            sections.append(f"## Candidate Name\n{profile_name}")
        if profile_targets:
            sections.append(
                f"## Career Targets\n{', '.join(profile_targets)}"
            )
        if profile_skills:
            sections.append(f"## Key Skills\n{', '.join(profile_skills)}")
        if profile_constraints:
            sections.append(
                f"## Constraints/Preferences\n{', '.join(profile_constraints)}"
            )
        sections.append(f"## CV Summary\n{cv_content}")
        sections.append(f"## Job Description\n{jd_text}")
        if job_opportunity:
            sections.append(
                f"## Opportunity Details\n{json.dumps(job_opportunity)}"
            )

        user_content = "\n\n".join(sections)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        response = await self._llm.ainvoke(messages)
        usage = dict(response.usage_metadata) if getattr(response, "usage_metadata", None) else None
        if usage is not None:
            usage["model_name"] = getattr(self._llm, "model_name", None) or getattr(self._llm, "model", "")
        content = response.content.replace("\u2014", ",").replace("\u2013", ",")
        return {
            "cover_letter_content": content,
            "_token_usage": [usage] if usage else [],
        }

