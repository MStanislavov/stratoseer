"""Agent protocol and base class for LLM-powered agents."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import Any, Protocol

from app.llm.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)


class AgentProtocol(Protocol):
    """All agents must be callable: (state) -> state or awaitable state."""

    agent_name: str

    def __call__(self, state: dict[str, Any]) -> dict[str, Any] | Awaitable[dict[str, Any]]: ...


class LLMAgent:
    """Base class for agents that use ChatOpenAI with structured output."""

    agent_name: str = ""

    def __init__(
        self,
        llm: Any,
        prompt_loader: PromptLoader | None = None,
    ):
        self._llm = llm
        self._prompt_loader = prompt_loader

    def _get_system_prompt(self, **kwargs: str) -> str:
        if self._prompt_loader is None:
            return f"You are a helpful {self.agent_name} agent."
        return self._prompt_loader.load(self.agent_name, **kwargs)

    async def _invoke_structured(
        self,
        schema: type,
        system_prompt: str,
        user_content: str,
    ) -> Any:
        """Invoke the LLM with structured output. Returns the parsed schema instance."""
        structured_llm = self._llm.with_structured_output(schema)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        return await structured_llm.ainvoke(messages)
