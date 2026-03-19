"""Unit tests for the deterministic inter-agent verifier."""

import pytest

from app.engine.verifier import (
    AgentVerification,
    CheckResult,
    Verifier,
    VerificationError,
    VerificationStatus,
)


@pytest.fixture()
def verifier():
    return Verifier()


@pytest.fixture()
def verifier_with_policy(tmp_path):
    policy_dir = tmp_path / "policy"
    policy_dir.mkdir()
    (policy_dir / "budgets.yaml").write_text("global:\n  max_output_items: 10\n")
    (policy_dir / "boundaries.yaml").write_text(
        "agents:\n  goal_extractor:\n    inputs: [profile_targets]\n    outputs: [search_prompts]\n"
    )
    from app.engine.policy_engine import PolicyEngine

    pe = PolicyEngine(policy_dir)
    return Verifier(policy_engine=pe)


# ------------------------------------------------------------------
# GoalExtractor
# ------------------------------------------------------------------


class TestGoalExtractorVerification:
    def test_valid_output(self, verifier):
        output = {
            "search_prompts": {
                "job_prompt": "find jobs",
                "cert_prompt": "find certs",
                "event_prompt": "find events",
                "group_prompt": "find groups",
                "trend_prompt": "find trends",
            }
        }
        result = verifier.verify("goal_extractor", output)
        assert result.status == VerificationStatus.PASS

    def test_missing_keys(self, verifier):
        output = {"search_prompts": {"job_prompt": "find jobs"}}
        result = verifier.verify("goal_extractor", output)
        assert result.status == VerificationStatus.FAIL
        assert any("Missing prompt keys" in c.message for c in result.checks)

    def test_not_a_dict(self, verifier):
        output = {"search_prompts": "not a dict"}
        result = verifier.verify("goal_extractor", output)
        assert result.status == VerificationStatus.FAIL

    def test_empty_values(self, verifier):
        output = {
            "search_prompts": {
                "job_prompt": "",
                "cert_prompt": "find certs",
                "event_prompt": "find events",
                "group_prompt": "find groups",
                "trend_prompt": "find trends",
            }
        }
        result = verifier.verify("goal_extractor", output)
        assert result.status == VerificationStatus.PARTIAL

    def test_boundary_compliance_pass(self, verifier_with_policy):
        output = {
            "search_prompts": {
                "job_prompt": "find jobs",
                "cert_prompt": "find certs",
                "event_prompt": "find events",
                "group_prompt": "find groups",
                "trend_prompt": "find trends",
            }
        }
        result = verifier_with_policy.verify("goal_extractor", output)
        assert result.status == VerificationStatus.PASS
        assert any("comply with boundaries" in c.message for c in result.checks)

    def test_boundary_compliance_fail(self, verifier_with_policy):
        output = {
            "search_prompts": {
                "job_prompt": "find jobs",
                "cert_prompt": "find certs",
                "event_prompt": "find events",
                "group_prompt": "find groups",
                "trend_prompt": "find trends",
            },
            "forbidden_key": "should not be here",
        }
        result = verifier_with_policy.verify("goal_extractor", output)
        assert result.status == VerificationStatus.FAIL
        assert any("not in boundaries" in c.message for c in result.checks)


# ------------------------------------------------------------------
# WebScrapers
# ------------------------------------------------------------------


class TestWebScrapersVerification:
    def test_valid_output(self, verifier):
        output = {
            "raw_job_results": [
                {"title": "Job A", "url": "https://a.com"},
                {"title": "Job B", "url": "https://b.com"},
            ],
            "raw_cert_results": [{"title": "Cert A", "url": "https://c.com"}],
        }
        result = verifier.verify("web_scrapers", output)
        assert result.status == VerificationStatus.PASS

    def test_not_a_list(self, verifier):
        output = {"raw_job_results": "not a list"}
        result = verifier.verify("web_scrapers", output)
        assert result.status == VerificationStatus.FAIL

    def test_missing_title(self, verifier):
        output = {"raw_job_results": [{"url": "https://a.com"}]}
        result = verifier.verify("web_scrapers", output)
        assert result.status == VerificationStatus.PARTIAL

    def test_duplicate_urls(self, verifier):
        output = {
            "raw_job_results": [
                {"title": "Job A", "url": "https://a.com"},
                {"title": "Job B", "url": "https://a.com"},
            ]
        }
        result = verifier.verify("web_scrapers", output)
        assert result.status == VerificationStatus.PARTIAL

    def test_exceeds_limit(self, verifier_with_policy):
        # limit is 10; >10 is partial, >20 is fail
        items = [{"title": f"Job {i}", "url": f"https://{i}.com"} for i in range(15)]
        output = {"raw_job_results": items}
        result = verifier_with_policy.verify("web_scrapers", output)
        assert result.status == VerificationStatus.PARTIAL

    def test_exceeds_2x_limit(self, verifier_with_policy):
        items = [{"title": f"Job {i}", "url": f"https://{i}.com"} for i in range(25)]
        output = {"raw_job_results": items}
        result = verifier_with_policy.verify("web_scrapers", output)
        assert result.status == VerificationStatus.FAIL

    def test_item_not_dict(self, verifier):
        output = {"raw_job_results": ["not a dict"]}
        result = verifier.verify("web_scrapers", output)
        assert result.status == VerificationStatus.FAIL


# ------------------------------------------------------------------
# DataFormatter
# ------------------------------------------------------------------


class TestDataFormatterVerification:
    def test_valid_output(self, verifier):
        output = {
            "formatted_jobs": [{"title": "Job A"}],
            "formatted_certifications": [{"title": "Cert A"}],
            "formatted_courses": [],
            "formatted_events": [],
            "formatted_groups": [],
            "formatted_trends": [{"title": "Trend A"}],
        }
        result = verifier.verify("data_formatter", output)
        assert result.status == VerificationStatus.PASS

    def test_missing_title_hard_fail(self, verifier):
        output = {"formatted_jobs": [{"company": "No Title Corp"}]}
        result = verifier.verify("data_formatter", output)
        assert result.status == VerificationStatus.FAIL

    def test_not_a_list(self, verifier):
        output = {"formatted_jobs": "not a list"}
        result = verifier.verify("data_formatter", output)
        assert result.status == VerificationStatus.FAIL

    def test_duplicate_titles(self, verifier):
        output = {
            "formatted_jobs": [
                {"title": "Same Title"},
                {"title": "Same Title"},
            ]
        }
        result = verifier.verify("data_formatter", output)
        assert result.status == VerificationStatus.PARTIAL

    def test_exceeds_2x_limit(self, verifier_with_policy):
        items = [{"title": f"Job {i}"} for i in range(25)]
        output = {"formatted_jobs": items}
        result = verifier_with_policy.verify("data_formatter", output)
        assert result.status == VerificationStatus.FAIL


# ------------------------------------------------------------------
# CEO
# ------------------------------------------------------------------


class TestCEOVerification:
    def test_valid_output(self, verifier):
        output = {
            "strategic_recommendations": [
                {"area": "Career", "recommendation": "Focus on cloud", "priority": "high"},
            ],
            "ceo_summary": "Strategic outlook is positive.",
        }
        result = verifier.verify("ceo", output)
        assert result.status == VerificationStatus.PASS

    def test_not_a_list(self, verifier):
        output = {"strategic_recommendations": "not a list", "ceo_summary": "ok"}
        result = verifier.verify("ceo", output)
        assert result.status == VerificationStatus.FAIL

    def test_missing_fields(self, verifier):
        output = {
            "strategic_recommendations": [{"area": "Career"}],
            "ceo_summary": "ok",
        }
        result = verifier.verify("ceo", output)
        assert result.status == VerificationStatus.PARTIAL

    def test_invalid_priority(self, verifier):
        output = {
            "strategic_recommendations": [
                {"area": "Career", "recommendation": "Do it", "priority": "urgent"},
            ],
            "ceo_summary": "ok",
        }
        result = verifier.verify("ceo", output)
        assert result.status == VerificationStatus.PARTIAL

    def test_empty_summary(self, verifier):
        output = {
            "strategic_recommendations": [],
            "ceo_summary": "",
        }
        result = verifier.verify("ceo", output)
        assert result.status == VerificationStatus.FAIL


# ------------------------------------------------------------------
# CFO
# ------------------------------------------------------------------


class TestCFOVerification:
    def test_valid_output(self, verifier):
        output = {
            "risk_assessments": [
                {"area": "Market", "risk_level": "medium"},
            ],
            "cfo_summary": "Investment is sound.",
        }
        result = verifier.verify("cfo", output)
        assert result.status == VerificationStatus.PASS

    def test_not_a_list(self, verifier):
        output = {"risk_assessments": "nope", "cfo_summary": "ok"}
        result = verifier.verify("cfo", output)
        assert result.status == VerificationStatus.FAIL

    def test_missing_fields(self, verifier):
        output = {
            "risk_assessments": [{"area": "Market"}],
            "cfo_summary": "ok",
        }
        result = verifier.verify("cfo", output)
        assert result.status == VerificationStatus.PARTIAL

    def test_empty_summary(self, verifier):
        output = {"risk_assessments": [], "cfo_summary": "  "}
        result = verifier.verify("cfo", output)
        assert result.status == VerificationStatus.FAIL


# ------------------------------------------------------------------
# CoverLetter
# ------------------------------------------------------------------


class TestCoverLetterVerification:
    def test_valid_output(self, verifier):
        output = {"cover_letter_content": "A" * 200}
        result = verifier.verify("cover_letter_agent", output)
        assert result.status == VerificationStatus.PASS

    def test_empty_content(self, verifier):
        output = {"cover_letter_content": ""}
        result = verifier.verify("cover_letter_agent", output)
        assert result.status == VerificationStatus.FAIL

    def test_missing_content(self, verifier):
        output = {}
        result = verifier.verify("cover_letter_agent", output)
        assert result.status == VerificationStatus.FAIL

    def test_short_content(self, verifier):
        output = {"cover_letter_content": "Too short"}
        result = verifier.verify("cover_letter_agent", output)
        assert result.status == VerificationStatus.PARTIAL

    def test_too_long_content(self, verifier):
        output = {"cover_letter_content": "A" * 10001}
        result = verifier.verify("cover_letter_agent", output)
        assert result.status == VerificationStatus.FAIL


# ------------------------------------------------------------------
# Job Freshness
# ------------------------------------------------------------------


class TestJobFreshnessVerification:
    def test_clean_results_pass(self, verifier):
        output = {
            "raw_job_results": [
                {"title": "Python Dev", "snippet": "Great role", "url": "https://a.com"},
                {"title": "Go Engineer", "snippet": "Build APIs", "url": "https://b.com"},
            ],
        }
        result = verifier.verify("web_scrapers", output)
        freshness_checks = [c for c in result.checks if c.check_name == "job_freshness"]
        assert len(freshness_checks) == 1
        assert freshness_checks[0].status == VerificationStatus.PASS

    def test_expired_snippets_produce_partial(self, verifier):
        output = {
            "raw_job_results": [
                {"title": "Python Dev", "snippet": "Great role", "url": "https://a.com"},
                {"title": "Old Job", "snippet": "This job has expired", "url": "https://b.com"},
            ],
        }
        result = verifier.verify("web_scrapers", output)
        freshness_checks = [c for c in result.checks if c.check_name == "job_freshness"]
        assert len(freshness_checks) == 1
        assert freshness_checks[0].status == VerificationStatus.PARTIAL
        assert result.status == VerificationStatus.PARTIAL

    def test_expired_title_flagged(self, verifier):
        output = {
            "raw_job_results": [
                {"title": "No longer accepting applications", "snippet": "Old posting", "url": "https://a.com"},
            ],
        }
        result = verifier.verify("web_scrapers", output)
        freshness_checks = [c for c in result.checks if c.check_name == "job_freshness"]
        assert freshness_checks[0].status == VerificationStatus.PARTIAL
        assert freshness_checks[0].details["flagged_indices"] == [0]

    def test_no_job_results_no_freshness_check(self, verifier):
        output = {
            "raw_cert_results": [{"title": "AWS Cert", "url": "https://a.com"}],
        }
        result = verifier.verify("web_scrapers", output)
        freshness_checks = [c for c in result.checks if c.check_name == "job_freshness"]
        assert len(freshness_checks) == 0


# ------------------------------------------------------------------
# Unknown agent
# ------------------------------------------------------------------


class TestUnknownAgent:
    def test_unknown_agent_passes(self, verifier):
        result = verifier.verify("unknown_agent", {"any": "data"})
        assert result.status == VerificationStatus.PASS


# ------------------------------------------------------------------
# build_report
# ------------------------------------------------------------------


class TestBuildReport:
    def test_all_pass(self, verifier):
        v1 = AgentVerification(
            agent_name="a", status=VerificationStatus.PASS,
            checks=[CheckResult("c1", VerificationStatus.PASS, "ok")],
        )
        report = verifier.build_report([v1])
        assert report["overall_status"] == "pass"
        assert report["total_checks"] == 1
        assert report["passed"] == 1
        assert report["warnings"] == 0
        assert report["failures"] == 0

    def test_partial_overall(self, verifier):
        v1 = AgentVerification(
            agent_name="a", status=VerificationStatus.PARTIAL,
            checks=[
                CheckResult("c1", VerificationStatus.PASS, "ok"),
                CheckResult("c2", VerificationStatus.PARTIAL, "warn"),
            ],
        )
        report = verifier.build_report([v1])
        assert report["overall_status"] == "partial"
        assert report["warnings"] == 1

    def test_fail_overall(self, verifier):
        v1 = AgentVerification(
            agent_name="a", status=VerificationStatus.PASS,
            checks=[CheckResult("c1", VerificationStatus.PASS, "ok")],
        )
        v2 = AgentVerification(
            agent_name="b", status=VerificationStatus.FAIL,
            checks=[CheckResult("c2", VerificationStatus.FAIL, "bad")],
        )
        report = verifier.build_report([v1, v2])
        assert report["overall_status"] == "fail"
        assert report["failures"] == 1

    def test_report_structure(self, verifier):
        v1 = AgentVerification(
            agent_name="a", status=VerificationStatus.PASS,
            checks=[CheckResult("c1", VerificationStatus.PASS, "ok")],
        )
        report = verifier.build_report([v1])
        assert "agent_results" in report
        assert "timestamp" in report
        assert len(report["agent_results"]) == 1
        agent_result = report["agent_results"][0]
        assert agent_result["agent_name"] == "a"
        assert len(agent_result["checks"]) == 1


# ------------------------------------------------------------------
# VerificationError
# ------------------------------------------------------------------


class TestVerificationError:
    def test_error_message(self):
        v = AgentVerification(
            agent_name="test", status=VerificationStatus.FAIL,
            checks=[
                CheckResult("c1", VerificationStatus.FAIL, "something broke"),
                CheckResult("c2", VerificationStatus.PASS, "this is fine"),
            ],
        )
        err = VerificationError(v)
        assert "test" in str(err)
        assert "something broke" in str(err)
        assert "this is fine" not in str(err)
        assert err.verification is v
