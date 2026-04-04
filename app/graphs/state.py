"""LangGraph state definitions for all pipeline modes."""

from __future__ import annotations

from typing import Any, TypedDict


class DailyState(TypedDict, total=False):
    """Shared state for the daily pipeline graph execution."""

    # Input
    profile_id: str
    profile_targets: list[str]
    profile_skills: list[str]
    profile_constraints: list[str]
    cv_summary: str
    run_id: str

    # Structured profile fields (all optional)
    preferred_titles: list[str]
    experience_level: str
    industries: list[str]
    locations: list[str]
    work_arrangement: str
    event_attendance: str
    target_certifications: list[str]
    learning_budget: str
    learning_format: str
    time_commitment: str

    # GoalExtractor output
    search_prompts: dict[str, str]

    # WebScraper raw results
    raw_cert_results: list[dict[str, Any]]
    raw_course_results: list[dict[str, Any]]
    raw_event_results: list[dict[str, Any]]
    raw_group_results: list[dict[str, Any]]
    raw_job_results: list[dict[str, Any]]
    raw_trend_results: list[dict[str, Any]]

    # DataFormatter output
    formatted_jobs: list[dict[str, Any]]
    formatted_certifications: list[dict[str, Any]]
    formatted_courses: list[dict[str, Any]]
    formatted_events: list[dict[str, Any]]
    formatted_groups: list[dict[str, Any]]
    formatted_trends: list[dict[str, Any]]

    # WebScraper filtered URLs (audit context)
    filtered_job_urls: list[dict[str, Any]]
    filtered_cert_urls: list[dict[str, Any]]
    filtered_course_urls: list[dict[str, Any]]
    filtered_event_urls: list[dict[str, Any]]
    filtered_group_urls: list[dict[str, Any]]
    filtered_trend_urls: list[dict[str, Any]]

    # URL Validator output
    url_validation_results: list[dict[str, Any]]

    # Verification
    verifier_results: list[dict[str, Any]]

    # Audit
    audit_events: list[dict[str, Any]]

    # Error tracking
    errors: list[str]
    safe_degradation: bool


class WeeklyState(TypedDict, total=False):
    """Shared state for the weekly pipeline graph execution."""

    # Input
    profile_id: str
    profile_targets: list[str]
    profile_skills: list[str]
    profile_constraints: list[str]
    cv_summary: str
    run_id: str

    # Structured profile fields (all optional)
    preferred_titles: list[str]
    experience_level: str
    industries: list[str]
    locations: list[str]
    work_arrangement: str
    event_attendance: str
    target_certifications: list[str]
    learning_budget: str
    learning_format: str
    time_commitment: str

    # GoalExtractor output
    search_prompts: dict[str, str]

    # WebScraper raw results
    raw_cert_results: list[dict[str, Any]]
    raw_course_results: list[dict[str, Any]]
    raw_event_results: list[dict[str, Any]]
    raw_group_results: list[dict[str, Any]]
    raw_job_results: list[dict[str, Any]]
    raw_trend_results: list[dict[str, Any]]

    # DataFormatter output
    formatted_jobs: list[dict[str, Any]]
    formatted_certifications: list[dict[str, Any]]
    formatted_courses: list[dict[str, Any]]
    formatted_events: list[dict[str, Any]]
    formatted_groups: list[dict[str, Any]]
    formatted_trends: list[dict[str, Any]]

    # WebScraper filtered URLs (audit context)
    filtered_job_urls: list[dict[str, Any]]
    filtered_cert_urls: list[dict[str, Any]]
    filtered_course_urls: list[dict[str, Any]]
    filtered_event_urls: list[dict[str, Any]]
    filtered_group_urls: list[dict[str, Any]]
    filtered_trend_urls: list[dict[str, Any]]

    # URL Validator output
    url_validation_results: list[dict[str, Any]]

    # CEO/CFO outputs
    strategic_recommendations: list[dict[str, Any]]
    ceo_summary: str
    risk_assessments: list[dict[str, Any]]
    cfo_summary: str

    # Verification
    verifier_results: list[dict[str, Any]]

    # Audit
    audit_events: list[dict[str, Any]]

    # Error tracking
    errors: list[str]
    safe_degradation: bool


class CoverLetterState(TypedDict, total=False):
    """Shared state for the cover letter pipeline graph execution."""

    # Input
    profile_id: str
    profile_name: str
    profile_targets: list[str]
    profile_skills: list[str]
    profile_constraints: list[str]
    cv_content: str
    jd_text: str
    job_opportunity: dict[str, Any]
    run_id: str

    # Cover letter output
    cover_letter_content: str

    # Verification
    verifier_results: list[dict[str, Any]]

    # Audit
    audit_events: list[dict[str, Any]]

    # Error tracking
    errors: list[str]
