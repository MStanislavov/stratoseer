"""Agent protocol: all agents must be callable (state) -> state."""

from __future__ import annotations

from typing import Any, Protocol


class AgentProtocol(Protocol):
    """All agents must be callable: (state) -> state."""

    agent_name: str

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]: ...
