"""Token usage tracking for pipeline runs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentTokenUsage:
    """Accumulated token usage for a single agent within a run."""

    agent_name: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the agent token usage to a dictionary.

        Returns:
            Dictionary containing agent name, model, token counts, and call count.
        """
        return {
            "agent_name": self.agent_name,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "call_count": self.call_count,
        }


class RunTokenTracker:
    """Accumulates per-agent token usage for a single pipeline run.

    Thread-safe via asyncio.Lock. Create one per run, pass it through
    the graph, and serialize at the end for audit logging.
    """

    def __init__(self, run_id: str) -> None:
        """Initialize a token tracker for the given pipeline run.

        Args:
            run_id: Unique identifier of the run to track token usage for.
        """
        self.run_id = run_id
        self._usage: dict[str, AgentTokenUsage] = {}
        self._lock = asyncio.Lock()

    async def record(
        self,
        agent_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record a single LLM invocation's token usage for an agent."""
        async with self._lock:
            if agent_name not in self._usage:
                self._usage[agent_name] = AgentTokenUsage(
                    agent_name=agent_name,
                    model=model,
                )
            usage = self._usage[agent_name]
            usage.input_tokens += input_tokens
            usage.output_tokens += output_tokens
            usage.total_tokens += input_tokens + output_tokens
            usage.call_count += 1
            if model:
                usage.model = model

    def get_agent_usage(self, agent_name: str) -> AgentTokenUsage | None:
        """Return accumulated usage for a specific agent, or None."""
        return self._usage.get(agent_name)

    def get_total(self) -> dict[str, int]:
        """Return aggregate totals across all agents."""
        total_input = sum(u.input_tokens for u in self._usage.values())
        total_output = sum(u.output_tokens for u in self._usage.values())
        return {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_calls": sum(u.call_count for u in self._usage.values()),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize for audit logging and API responses."""
        return {
            "run_id": self.run_id,
            "agents": {name: usage.to_dict() for name, usage in self._usage.items()},
            "totals": self.get_total(),
        }
