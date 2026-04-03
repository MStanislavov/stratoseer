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

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """Generate search prompts for each category from the profile state."""
        targets = state.get("profile_targets", [])
        skills = state.get("profile_skills", [])
        constraints = state.get("profile_constraints", [])
        cv_summary = state.get("cv_summary", "")
        today = date.today().isoformat()

        system_prompt = self._get_system_prompt(today=today)
        user_parts = [
            f"Today's date: {today}",
            f"Profile targets: {json.dumps(targets)}",
            f"Profile skills: {json.dumps(skills)}",
        ]
        if constraints:
            user_parts.append(f"Profile constraints: {json.dumps(constraints)}")
        if cv_summary:
            user_parts.append(f"CV summary:\n{cv_summary[:3000]}")

        user_content = "\n".join(user_parts)
        result = await self._invoke_structured(GoalExtractorOutput, system_prompt, user_content)
        return {
            "search_prompts": {
                "cert_prompt": result.cert_prompt,
                "event_prompt": result.event_prompt,
                "group_prompt": result.group_prompt,
                "job_prompt": result.job_prompt,
                "trend_prompt": result.trend_prompt,
            },
        }
