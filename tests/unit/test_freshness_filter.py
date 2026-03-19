"""Unit tests for the post-search freshness filter."""

import pytest

from app.engine.freshness_filter import FreshnessFilter


@pytest.fixture()
def default_filter():
    return FreshnessFilter()


@pytest.fixture()
def custom_filter():
    return FreshnessFilter({"expiry_patterns": [r"custom expired"]})


class TestFreshnessFilter:
    def test_removes_expired_snippet(self, default_filter):
        results = [
            {"title": "Python Dev", "snippet": "Great role", "url": "https://a.com"},
            {"title": "Old Job", "snippet": "This job has expired", "url": "https://b.com"},
        ]
        kept, removed = default_filter.filter_results(results, "job")
        assert len(kept) == 1
        assert len(removed) == 1
        assert removed[0]["title"] == "Old Job"

    def test_removes_expired_title(self, default_filter):
        results = [
            {"title": "Position has been filled - Senior Dev", "snippet": "Was a good role", "url": "https://a.com"},
        ]
        kept, removed = default_filter.filter_results(results, "job")
        assert len(kept) == 0
        assert len(removed) == 1

    def test_keeps_valid_results(self, default_filter):
        results = [
            {"title": "Python Dev", "snippet": "Great role", "url": "https://a.com"},
            {"title": "Go Engineer", "snippet": "Build APIs", "url": "https://b.com"},
        ]
        kept, removed = default_filter.filter_results(results, "job")
        assert len(kept) == 2
        assert len(removed) == 0

    def test_skips_non_job_categories(self, default_filter):
        results = [
            {"title": "Expired Cert", "snippet": "This job has expired", "url": "https://a.com"},
        ]
        for category in ("cert", "event", "group", "trend"):
            kept, removed = default_filter.filter_results(results, category)
            assert len(kept) == 1
            assert len(removed) == 0

    def test_case_insensitive(self, default_filter):
        results = [
            {"title": "Dev Role", "snippet": "THIS JOB HAS EXPIRED", "url": "https://a.com"},
        ]
        kept, removed = default_filter.filter_results(results, "job")
        assert len(kept) == 0
        assert len(removed) == 1

    def test_custom_patterns(self, custom_filter):
        results = [
            {"title": "Job A", "snippet": "custom expired posting", "url": "https://a.com"},
            {"title": "Job B", "snippet": "This job has expired", "url": "https://b.com"},
        ]
        kept, removed = custom_filter.filter_results(results, "job")
        # "custom expired" matches Job A, but "This job has expired" does NOT match custom pattern
        assert len(kept) == 1
        assert len(removed) == 1
        assert removed[0]["title"] == "Job A"

    def test_returns_removed_for_audit(self, default_filter):
        results = [
            {"title": "Good Job", "snippet": "Apply now", "url": "https://a.com"},
            {"title": "Closed", "snippet": "No longer accepting applications", "url": "https://b.com"},
            {"title": "Filled", "snippet": "This listing has expired", "url": "https://c.com"},
        ]
        kept, removed = default_filter.filter_results(results, "job")
        assert len(kept) == 1
        assert len(removed) == 2

    def test_empty_results(self, default_filter):
        kept, removed = default_filter.filter_results([], "job")
        assert kept == []
        assert removed == []

    def test_applications_closed_regex(self, default_filter):
        """The pattern 'applications? closed' should match both singular and plural."""
        results = [
            {"title": "Job", "snippet": "Application closed for this role", "url": "https://a.com"},
            {"title": "Job 2", "snippet": "Applications closed since last week", "url": "https://b.com"},
        ]
        kept, removed = default_filter.filter_results(results, "job")
        assert len(kept) == 0
        assert len(removed) == 2

    def test_body_field_also_scanned(self, default_filter):
        """The filter should also check the 'body' field (DuckDuckGo raw format)."""
        results = [
            {"title": "Job", "snippet": "", "body": "This job has expired", "url": "https://a.com"},
        ]
        kept, removed = default_filter.filter_results(results, "job")
        assert len(kept) == 0
        assert len(removed) == 1

    def test_default_config_none(self):
        """Passing None config uses default patterns."""
        f = FreshnessFilter(None)
        results = [{"title": "Job", "snippet": "This job has expired", "url": "https://a.com"}]
        kept, removed = f.filter_results(results, "job")
        assert len(removed) == 1
