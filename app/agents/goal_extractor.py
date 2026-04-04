"""GoalExtractor agent: converts profile targets + skills + CV into search prompts."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.agents.base import LLMAgent
from app.agents.schemas import GoalExtractorOutput


class GoalExtractorAgent(LLMAgent):
    """Converts profile targets, skills, and CV into category-specific search prompts."""

    agent_name = "goal_extractor"

    @staticmethod
    def _build_job_prompt(
        preferred_titles: list[str],
        experience_level: str = "",
        industries: list[str] | None = None,
        locations: list[str] | None = None,
        work_arrangement: str = "",
        constraints: list[str] | None = None,
    ) -> str:
        """Build a deterministic LinkedIn job search directive from structured profile fields."""
        parts: list[str] = ["Search LinkedIn for"]

        if work_arrangement:
            parts.append(work_arrangement)

        if experience_level:
            parts.append(experience_level)

        parts.append(" and ".join(preferred_titles))
        parts.append("job openings")

        if industries:
            parts.append(f"in {' and '.join(industries)}")

        if locations and work_arrangement != "remote":
            parts.append(f"in {', '.join(locations)}")

        if constraints:
            parts.append(f"with {', '.join(c.lower() for c in constraints)}")

        return " ".join(parts)

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """Generate search prompts for each category from the profile state."""
        targets = state.get("profile_targets", [])
        skills = state.get("profile_skills", [])
        constraints = state.get("profile_constraints", [])
        cv_summary = state.get("cv_summary", "")
        today = date.today().isoformat()

        # Structured fields
        preferred_titles = state.get("preferred_titles", [])
        experience_level = state.get("experience_level", "")
        industries = state.get("industries", [])
        locations = state.get("locations", [])
        work_arrangement = state.get("work_arrangement", "")
        event_attendance = state.get("event_attendance", "")
        target_certs = state.get("target_certifications", [])
        learning_budget = state.get("learning_budget", "")
        learning_format = state.get("learning_format", "")
        time_commitment = state.get("time_commitment", "")

        # Build job_prompt deterministically from structured fields
        job_prompt = self._build_job_prompt(
            preferred_titles=preferred_titles,
            experience_level=experience_level,
            industries=industries,
            locations=locations,
            work_arrangement=work_arrangement,
            constraints=constraints,
        )

        # Build LLM context for the remaining 5 prompts
        system_prompt = self._get_system_prompt(today=today)
        user_parts = [
            f"Today's date: {today}",
            f"Profile targets: {json.dumps(targets)}",
            f"Profile skills: {json.dumps(skills)}",
        ]
        if constraints:
            user_parts.append(f"Profile constraints: {json.dumps(constraints)}")
        if preferred_titles:
            user_parts.append(f"Preferred job titles: {json.dumps(preferred_titles)}")
        if experience_level:
            user_parts.append(f"Experience level: {experience_level}")
        if industries:
            user_parts.append(f"Target industries: {json.dumps(industries)}")
        if locations:
            user_parts.append(f"Preferred locations: {json.dumps(locations)}")
        if work_arrangement:
            user_parts.append(f"Work arrangement: {work_arrangement}")
        if event_attendance:
            user_parts.append(f"Event attendance: {event_attendance}")
        if target_certs:
            user_parts.append(f"Target certifications: {json.dumps(target_certs)}")
        if learning_budget:
            user_parts.append(f"Learning budget: {learning_budget}")
        if learning_format:
            user_parts.append(f"Learning format: {learning_format}")
        if time_commitment:
            user_parts.append(f"Time commitment for learning: {time_commitment}")
        if cv_summary:
            user_parts.append(f"CV summary:\n{cv_summary[:3000]}")

        user_content = "\n".join(user_parts)
        result = await self._invoke_structured(GoalExtractorOutput, system_prompt, user_content)

        return {
            "search_prompts": {
                "cert_prompt": result.cert_prompt,
                "course_prompt": result.course_prompt,
                "event_prompt": result.event_prompt,
                "group_prompt": result.group_prompt,
                "job_prompt": job_prompt,
                "trend_prompt": result.trend_prompt,
            },
        }
