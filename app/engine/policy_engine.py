"""Policy engine: loads YAML policies and enforces tool/source/budget/boundary rules."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Budget:
    """Step and token budget for a single agent."""

    max_steps: int
    max_tokens: int


@dataclass
class PolicyVersion:
    """Snapshot of all loaded policies with a content-hash for versioning."""

    hash: str
    policies: dict[str, Any]


class PolicyEngine:
    """Loads ``policy/*.yaml`` files and provides query/enforcement helpers.

    The engine is intentionally stateless beyond the cached policy dict and
    version hash.  Call :meth:`reload` after editing YAML on disk.
    """

    def __init__(self, policy_dir: Path | str = "policy") -> None:
        self._policy_dir = Path(policy_dir)
        self._policies: dict[str, Any] = {}
        self._version_hash: str = ""
        self.reload()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """(Re-)read every ``*.yaml`` file under the policy directory."""
        self._policies = {}
        hash_input = b""
        for yaml_file in sorted(self._policy_dir.glob("*.yaml")):
            content = yaml_file.read_bytes()
            hash_input += content
            self._policies[yaml_file.stem] = yaml.safe_load(content) or {}
        self._version_hash = hashlib.sha256(hash_input).hexdigest()

    # ------------------------------------------------------------------
    # Version / introspection
    # ------------------------------------------------------------------

    @property
    def version(self) -> PolicyVersion:
        return PolicyVersion(hash=self._version_hash, policies=dict(self._policies))

    def get_policy(self, name: str) -> dict[str, Any]:
        if name not in self._policies:
            raise KeyError(f"Policy '{name}' not found")
        return self._policies[name]

    def list_policies(self) -> list[str]:
        return list(self._policies.keys())

    # ------------------------------------------------------------------
    # Tool enforcement
    # ------------------------------------------------------------------

    def is_tool_allowed(self, agent: str, tool: str) -> bool:
        """Return *True* only if *tool* is on the agent's allow-list and
        **not** on its deny-list.  Unknown agents are denied by default."""
        tools_policy = self._policies.get("tools", {})
        agent_config = tools_policy.get("agents", {}).get(agent)
        if agent_config is None:
            return False  # unknown agent -> deny
        denied = agent_config.get("denied_tools", [])
        if tool in denied:
            return False
        allowed = agent_config.get("allowed_tools", [])
        return tool in allowed

    # ------------------------------------------------------------------
    # Source enforcement
    # ------------------------------------------------------------------

    def is_source_allowed(self, scout: str, source: str) -> bool:
        """Return *True* only if *source* matches the scout's allow-list and
        does **not** match any deny pattern."""
        sources_policy = self._policies.get("sources", {})
        scout_config = sources_policy.get("scouts", {}).get(scout)
        if scout_config is None:
            return False
        denied = scout_config.get("denied_sources", [])
        for pattern in denied:
            if self._match_source_pattern(pattern, source):
                return False
        allowed = scout_config.get("allowed_sources", [])
        for pattern in allowed:
            if self._match_source_pattern(pattern, source):
                return True
        return False

    @staticmethod
    def _match_source_pattern(pattern: str, source: str) -> bool:
        """Simple wildcard matching: ``*.onion`` matches any source ending
        with ``.onion``; otherwise a substring check is performed."""
        if pattern.startswith("*."):
            return source.endswith(pattern[1:])
        return pattern in source

    # ------------------------------------------------------------------
    # Budget queries
    # ------------------------------------------------------------------

    def get_budget(self, agent: str) -> Budget:
        budgets_policy = self._policies.get("budgets", {})
        agent_config = budgets_policy.get("agents", {}).get(agent)
        if agent_config is None:
            raise KeyError(f"No budget for agent '{agent}'")
        return Budget(
            max_steps=agent_config["max_steps"],
            max_tokens=agent_config["max_tokens"],
        )

    # ------------------------------------------------------------------
    # Data-boundary queries
    # ------------------------------------------------------------------

    def get_boundaries(self, agent: str) -> dict[str, list[str]]:
        boundaries_policy = self._policies.get("boundaries", {})
        agent_config = boundaries_policy.get("agents", {}).get(agent)
        if agent_config is None:
            raise KeyError(f"No boundaries for agent '{agent}'")
        return {"inputs": list(agent_config["inputs"]), "outputs": list(agent_config["outputs"])}

    # ------------------------------------------------------------------
    # Redaction helpers
    # ------------------------------------------------------------------

    def get_redaction_rules(self) -> list[dict[str, Any]]:
        redaction_policy = self._policies.get("redaction", {})
        return redaction_policy.get("rules", [])

    def apply_redaction(self, text: str, context: str = "audit_log") -> str:
        """Apply all redaction rules whose ``applies_to`` includes *context*."""
        for rule in self.get_redaction_rules():
            if context in rule.get("applies_to", []):
                text = re.sub(rule["pattern"], rule["replacement"], text)
        return text

    # ------------------------------------------------------------------
    # Global config
    # ------------------------------------------------------------------

    def get_global_config(self) -> dict[str, Any]:
        budgets_policy = self._policies.get("budgets", {})
        return budgets_policy.get("global", {})
