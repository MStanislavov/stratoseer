"""Agent protocol and base class for LLM-powered agents."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable
from typing import Any, Protocol

from app.llm.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)


class AgentProtocol(Protocol):
    """All agents must be callable: (state) -> state or awaitable state."""

    agent_name: str

    def __call__(self, state: dict[str, Any]) -> dict[str, Any] | Awaitable[dict[str, Any]]: ...


def _extract_first_json(text: str, schema: type) -> Any | None:
    """Extract the first valid JSON object from text with trailing characters.

    Uses json.JSONDecoder.raw_decode to parse the first complete JSON object
    and ignore any trailing content that smaller models sometimes append.
    """
    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(text)
        return schema.model_validate(obj)
    except (json.JSONDecodeError, Exception):
        return None


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
    ) -> tuple[Any, dict | None]:
        """Invoke the LLM with structured output.

        Returns (parsed_result, usage_metadata_dict) where usage may be None
        if the provider does not report token counts.
        """
        structured_llm = self._llm.with_structured_output(schema, include_raw=True)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        result = await structured_llm.ainvoke(messages)
        raw = result.get("raw")
        parsed = result.get("parsed")
        parsing_error = result.get("parsing_error")

        if parsed is None and parsing_error is not None:
            content = getattr(raw, "content", "") if raw else ""
            if content:
                parsed = _extract_first_json(content.strip(), schema)
            if parsed is not None:
                logger.warning("Recovered structured output via raw_decode fallback")
            else:
                raise parsing_error

        usage = dict(raw.usage_metadata) if raw and getattr(raw, "usage_metadata", None) else None
        if usage is not None:
            usage["model_name"] = getattr(self._llm, "model_name", None) or getattr(self._llm, "model", "")
        return parsed, usage
