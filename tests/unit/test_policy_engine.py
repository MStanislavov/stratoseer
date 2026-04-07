"""Tests for the PolicyEngine."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.engine.policy_engine import Budget, PolicyEngine

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def policy_dir(tmp_path: Path) -> Path:
    """Create a minimal but complete set of policy YAML files."""
    tools = {
        "agents": {
            "goal_extractor": {
                "allowed_tools": ["llm_structured_output"],
                "denied_tools": ["web_search", "web_fetch"],
            },
            "web_scraper": {
                "allowed_tools": ["web_search", "web_fetch"],
                "denied_tools": [],
            },
            "data_formatter": {
                "allowed_tools": ["llm_structured_output"],
                "denied_tools": ["web_search", "web_fetch"],
            },
        }
    }
    budgets = {
        "agents": {
            "goal_extractor": {
                "max_steps": 3,
                "max_input_tokens": 4000,
                "max_output_tokens": 2000,
                "type": "llm",
            },
            "web_scraper": {
                "max_steps": 5,
                "max_input_tokens": 100000,
                "max_output_tokens": 16000,
                "type": "llm",
            },
            "audit_writer": {"max_steps": 5, "type": "deterministic"},
        },
        "global": {"max_output_items": 50},
    }
    boundaries = {
        "agents": {
            "goal_extractor": {
                "inputs": ["profile_targets"],
                "outputs": ["search_prompts"],
            },
            "data_formatter": {
                "inputs": [
                    "raw_job_results",
                    "raw_cert_results",
                    "raw_event_results",
                    "raw_trend_results",
                ],
                "outputs": [
                    "formatted_jobs",
                    "formatted_certifications",
                    "formatted_courses",
                    "formatted_events",
                    "formatted_groups",
                    "formatted_trends",
                ],
            },
        }
    }
    redaction = {
        "rules": [
            {
                "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                "replacement": "[REDACTED_EMAIL]",
                "applies_to": ["audit_log"],
            },
            {
                "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
                "replacement": "[REDACTED_SSN]",
                "applies_to": ["audit_log", "run_bundle"],
            },
        ]
    }

    for name, data in [
        ("tools", tools),
        ("budgets", budgets),
        ("boundaries", boundaries),
        ("redaction", redaction),
    ]:
        (tmp_path / f"{name}.yaml").write_text(yaml.dump(data), encoding="utf-8")

    return tmp_path


@pytest.fixture()
def engine(policy_dir: Path) -> PolicyEngine:
    """Create a PolicyEngine instance from the test policy directory.

    Args:
        policy_dir: Path to the temporary policy YAML files.

    Returns:
        PolicyEngine: An engine loaded with the test policies.
    """
    return PolicyEngine(policy_dir)


# ------------------------------------------------------------------
# Loading / introspection
# ------------------------------------------------------------------


class TestLoading:
    """Tests for policy file loading and introspection."""

    def test_list_policies(self, engine: PolicyEngine) -> None:
        names = engine.list_policies()
        assert set(names) == {"tools", "budgets", "boundaries", "redaction"}

    def test_get_policy_returns_dict(self, engine: PolicyEngine) -> None:
        tools = engine.get_policy("tools")
        assert "agents" in tools

    def test_get_policy_unknown_raises(self, engine: PolicyEngine) -> None:
        with pytest.raises(KeyError, match="not found"):
            engine.get_policy("nonexistent")

    def test_version_hash_is_stable(self, engine: PolicyEngine) -> None:
        h1 = engine.version.hash
        h2 = engine.version.hash
        assert h1 == h2

    def test_version_hash_changes_on_yaml_edit(self, policy_dir: Path) -> None:
        engine = PolicyEngine(policy_dir)
        h1 = engine.version.hash

        budgets_path = policy_dir / "budgets.yaml"
        data = yaml.safe_load(budgets_path.read_text(encoding="utf-8"))
        data["global"]["max_output_items"] = 999
        budgets_path.write_text(yaml.dump(data), encoding="utf-8")

        engine.reload()
        h2 = engine.version.hash
        assert h1 != h2

    def test_version_policies_snapshot(self, engine: PolicyEngine) -> None:
        pv = engine.version
        assert isinstance(pv.policies, dict)
        assert "tools" in pv.policies


# ------------------------------------------------------------------
# Tool enforcement
# ------------------------------------------------------------------


class TestToolAllowlist:
    """Tests for tool allowlist and denylist enforcement per agent."""

    def test_allowed_tool_returns_true(self, engine: PolicyEngine) -> None:
        assert engine.is_tool_allowed("web_scraper", "web_search") is True

    def test_denied_tool_returns_false(self, engine: PolicyEngine) -> None:
        assert engine.is_tool_allowed("goal_extractor", "web_search") is False

    def test_unlisted_tool_returns_false(self, engine: PolicyEngine) -> None:
        assert engine.is_tool_allowed("web_scraper", "nuclear_launch") is False

    def test_unknown_agent_returns_false(self, engine: PolicyEngine) -> None:
        assert engine.is_tool_allowed("unknown_agent", "web_search") is False

    def test_data_formatter_denied_retrieval(self, engine: PolicyEngine) -> None:
        for tool in ("web_search", "web_fetch"):
            assert engine.is_tool_allowed("data_formatter", tool) is False

    def test_data_formatter_allowed_llm(self, engine: PolicyEngine) -> None:
        assert engine.is_tool_allowed("data_formatter", "llm_structured_output") is True


# ------------------------------------------------------------------
# Budget queries
# ------------------------------------------------------------------


class TestBudgets:
    """Tests for per-agent budget queries (step limits, token limits)."""

    def test_get_budget_known_agent(self, engine: PolicyEngine) -> None:
        budget = engine.get_budget("goal_extractor")
        assert isinstance(budget, Budget)
        assert budget.max_steps == 3
        assert budget.max_input_tokens == 4000
        assert budget.max_output_tokens == 2000
        assert budget.agent_type == "llm"

    def test_get_budget_web_scraper(self, engine: PolicyEngine) -> None:
        budget = engine.get_budget("web_scraper")
        assert budget.max_steps == 5
        assert budget.max_input_tokens == 100000
        assert budget.max_output_tokens == 16000
        assert budget.agent_type == "llm"

    def test_get_budget_deterministic_agent(self, engine: PolicyEngine) -> None:
        budget = engine.get_budget("audit_writer")
        assert budget.max_steps == 5
        assert budget.max_input_tokens is None
        assert budget.max_output_tokens is None
        assert budget.agent_type == "deterministic"

    def test_get_budget_unknown_raises(self, engine: PolicyEngine) -> None:
        with pytest.raises(KeyError, match="No budget"):
            engine.get_budget("nonexistent_agent")


# ------------------------------------------------------------------
# Boundary queries
# ------------------------------------------------------------------


class TestBoundaries:
    """Tests for data boundary queries that define agent input/output fields."""

    def test_get_boundaries_known_agent(self, engine: PolicyEngine) -> None:
        b = engine.get_boundaries("goal_extractor")
        assert b["inputs"] == ["profile_targets"]
        assert b["outputs"] == ["search_prompts"]

    def test_get_boundaries_data_formatter(self, engine: PolicyEngine) -> None:
        b = engine.get_boundaries("data_formatter")
        assert "raw_job_results" in b["inputs"]
        assert "formatted_jobs" in b["outputs"]

    def test_get_boundaries_unknown_raises(self, engine: PolicyEngine) -> None:
        with pytest.raises(KeyError, match="No boundaries"):
            engine.get_boundaries("nonexistent_agent")


# ------------------------------------------------------------------
# Redaction
# ------------------------------------------------------------------


class TestRedaction:
    """Tests for PII redaction rule application."""

    def test_get_redaction_rules_returns_list(self, engine: PolicyEngine) -> None:
        rules = engine.get_redaction_rules()
        assert isinstance(rules, list)
        assert len(rules) >= 2

    def test_apply_redaction_email(self, engine: PolicyEngine) -> None:
        text = "Contact user@example.com for info"
        result = engine.apply_redaction(text, "audit_log")
        assert "[REDACTED_EMAIL]" in result
        assert "user@example.com" not in result

    def test_apply_redaction_ssn(self, engine: PolicyEngine) -> None:
        text = "SSN is 123-45-6789"
        result = engine.apply_redaction(text, "audit_log")
        assert "[REDACTED_SSN]" in result
        assert "123-45-6789" not in result

    def test_apply_redaction_ssn_in_bundle(self, engine: PolicyEngine) -> None:
        text = "SSN is 123-45-6789"
        result = engine.apply_redaction(text, "run_bundle")
        assert "[REDACTED_SSN]" in result

    def test_apply_redaction_email_not_in_bundle(self, engine: PolicyEngine) -> None:
        text = "Contact user@example.com"
        result = engine.apply_redaction(text, "run_bundle")
        assert "user@example.com" in result

    def test_apply_redaction_no_match(self, engine: PolicyEngine) -> None:
        text = "Nothing sensitive here"
        result = engine.apply_redaction(text, "audit_log")
        assert result == text


# ------------------------------------------------------------------
# Global config
# ------------------------------------------------------------------


class TestGlobalConfig:
    """Tests for global configuration values from the policy engine."""

    def test_get_global_config(self, engine: PolicyEngine) -> None:
        cfg = engine.get_global_config()
        assert cfg["max_output_items"] == 50
