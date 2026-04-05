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


def _get_raw_json_content(raw: Any) -> str:
    """Extract the JSON string from an AIMessage regardless of structured output method.

    Checks multiple locations because the JSON lives in different places
    depending on the method used by with_structured_output:
    - json_mode / json_schema: raw.content
    - function_calling: raw.additional_kwargs.tool_calls[0].function.arguments
    - legacy function_calling: raw.additional_kwargs.function_call.arguments
    """
    if not raw:
        return ""
    content = getattr(raw, "content", "") or ""
    if content:
        return content
    additional = getattr(raw, "additional_kwargs", {}) or {}
    tool_calls = additional.get("tool_calls") or []
    if tool_calls:
        args = (tool_calls[0].get("function") or {}).get("arguments", "")
        if args:
            return args
    func_call = additional.get("function_call") or {}
    return func_call.get("arguments", "")


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
        # Try up to three structured output methods, from strictest to most lenient
        methods = [
            (None, "json_schema"),            # default (strictest)
            ("function_calling", "function_calling"),
            ("json_mode", "json_mode"),        # most lenient
        ]
        result = None
        last_exc = None
        for method_arg, method_label in methods:
            try:
                if method_arg is None:
                    s_llm = structured_llm
                else:
                    s_llm = self._llm.with_structured_output(
                        schema, include_raw=True, method=method_arg,
                    )
                result = await s_llm.ainvoke(messages)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Structured output (%s) failed: %s. %s",
                    method_label, exc,
                    "Trying next method." if method_arg != "json_mode" else "All methods exhausted.",
                )

        if result is None:
            if last_exc is not None:
                raise last_exc
            raise ValueError("Structured output returned None from all methods")

        raw = result.get("raw")
        parsed = result.get("parsed")
        parsing_error = result.get("parsing_error")

        if parsed is None and parsing_error is not None:
            content = _get_raw_json_content(raw)
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
