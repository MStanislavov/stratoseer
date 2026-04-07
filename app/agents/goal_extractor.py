"""GoalExtractor agent: converts profile targets + CV into search prompts."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.agents.base import LLMAgent
from app.agents.schemas import GoalExtractorOutput


class GoalExtractorAgent(LLMAgent):
    """Converts profile targets and CV into category-specific search prompts."""

    agent_name = "goal_extractor"

    @staticmethod
    def _build_job_prompt(
        preferred_titles: list[str],
        industries: list[str] | None = None,
        locations: list[str] | None = None,
        work_arrangement: str = "",
        constraints: list[str] | None = None,
    ) -> str:
        """Build a deterministic LinkedIn job search directive from structured profile fields."""
        parts: list[str] = ["Search LinkedIn for",
                            work_arrangement if work_arrangement else ""]

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
        constraints = state.get("profile_constraints", [])
        cv_summary = state.get("cv_summary", "")
        today = date.today().isoformat()

        # Structured fields
        preferred_titles = state.get("preferred_titles", [])
        industries = state.get("industries", [])
        locations = state.get("locations", [])
        work_arrangement = state.get("work_arrangement", "")
        event_attendance = state.get("event_attendance", "")
        event_topics = state.get("event_topics", [])
        target_certs = state.get("target_certifications", [])
        learning_format = state.get("learning_format", "")

        # Build job_prompt deterministically from structured fields
        job_prompt = self._build_job_prompt(
            preferred_titles=preferred_titles,
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
        ]
        if constraints:
            user_parts.append(f"Profile constraints: {json.dumps(constraints)}")
        if preferred_titles:
            user_parts.append(f"Preferred job titles: {json.dumps(preferred_titles)}")
        if industries:
            user_parts.append(f"Target industries: {json.dumps(industries)}")
        if locations:
            user_parts.append(f"Preferred locations: {json.dumps(locations)}")
        if work_arrangement:
            user_parts.append(f"Work arrangement: {work_arrangement}")
        if event_attendance:
            user_parts.append(f"Event attendance: {event_attendance}")
        if event_topics:
            user_parts.append(f"Event topics: {json.dumps(event_topics)}")
        if target_certs:
            user_parts.append(f"Target certifications: {json.dumps(target_certs)}")
        if learning_format:
            user_parts.append(f"Learning format: {learning_format}")
        if cv_summary:
            user_parts.append(f"CV summary:\n{cv_summary[:3000]}")

        user_content = "\n".join(user_parts)
        result, usage = await self._invoke_structured(GoalExtractorOutput, system_prompt, user_content)

        return {
            "search_prompts": {
                "cert_prompt": result.cert_prompt,
                "course_prompt": result.course_prompt,
                "event_prompt": result.event_prompt,
                "group_prompt": result.group_prompt,
                "job_prompt": job_prompt,
                "trend_prompt": result.trend_prompt,
            },
            "_token_usage": [usage] if usage else [],
        }
