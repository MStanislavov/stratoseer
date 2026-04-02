"""Pydantic schemas for LLM structured output from agents."""

from pydantic import BaseModel, Field


# -- URLValidator output --

class URLValidationItem(BaseModel):
    """Validation result for a single URL."""

    url: str = Field(description="The URL that was validated")
    valid: bool = Field(description="True if the content is still active and relevant")
    reason: str = Field(default="", description="Brief reason if invalid")


class URLValidationOutput(BaseModel):
    """Structured output from the URL validator with per-URL validity flags."""

    results: list[URLValidationItem] = Field(default_factory=list)


# -- GoalExtractor output --

class GoalExtractorOutput(BaseModel):
    """Structured output from the GoalExtractor agent containing search prompts per category."""

    cert_prompt: str = Field(description="Full directive sentence to find certifications and courses, e.g. 'Search for AWS certifications and architecture courses for a Java developer'")
    event_prompt: str = Field(description="Full directive sentence to find events and conferences, e.g. 'Find 2026 software architecture and AI conferences in Europe'")
    group_prompt: str = Field(description="Full directive sentence to find professional communities and groups, e.g. 'Search Discord, Reddit, and LinkedIn for Java and cloud computing communities'")
    job_prompt: str = Field(description="Full directive sentence to find job openings, e.g. 'Search for senior Java and Python developer job openings'")
    trend_prompt: str = Field(description="Full directive sentence to find trends, e.g. 'Find emerging trends in cloud-native architecture and AI engineering'")


# -- WebScraper output --

class WebScraperResult(BaseModel):
    """A single web search result with title, URL, snippet, and source."""

    title: str = Field(description="Title of the search result")
    url: str = Field(default="", description="URL of the search result")
    snippet: str = Field(default="", description="Brief excerpt or description")
    source: str = Field(default="", description="Source website or domain")


class WebScraperOutput(BaseModel):
    """Structured output from the WebScraper agent containing a list of search results."""

    results: list[WebScraperResult] = Field(default_factory=list)


# -- DataFormatter sub-models --

class FormattedJob(BaseModel):
    """A job posting normalized into a consistent structure."""

    title: str
    company: str | None = None
    url: str | None = None
    description: str | None = None
    location: str | None = None
    salary_range: str | None = None

class FormattedCertification(BaseModel):
    """A certification opportunity normalized into a consistent structure."""

    title: str
    provider: str | None = None
    url: str | None = None
    description: str | None = None
    cost: str | None = None
    duration: str | None = None

class FormattedCourse(BaseModel):
    """A course or training program normalized into a consistent structure."""

    title: str
    platform: str | None = None
    url: str | None = None
    description: str | None = None
    cost: str | None = None
    duration: str | None = None

class FormattedEvent(BaseModel):
    """A conference or event normalized into a consistent structure."""

    title: str
    organizer: str | None = None
    url: str | None = None
    description: str | None = None
    event_date: str | None = None
    location: str | None = None

class FormattedGroup(BaseModel):
    """A professional community or group normalized into a consistent structure."""

    title: str
    platform: str | None = None
    url: str | None = None
    description: str | None = None
    member_count: int | None = None

class FormattedTrend(BaseModel):
    """An industry trend or market development normalized into a consistent structure."""

    title: str
    category: str | None = None
    url: str | None = None
    description: str | None = None
    relevance: str | None = None
    source: str | None = None

class DataFormatterOutput(BaseModel):
    """Structured output from the DataFormatter agent with all formatted categories."""

    jobs: list[FormattedJob] = Field(default_factory=list)
    certifications: list[FormattedCertification] = Field(default_factory=list)
    courses: list[FormattedCourse] = Field(default_factory=list)
    events: list[FormattedEvent] = Field(default_factory=list)
    groups: list[FormattedGroup] = Field(default_factory=list)
    trends: list[FormattedTrend] = Field(default_factory=list)


# -- CEO output --

class StrategicRecommendation(BaseModel):
    """A single strategic recommendation from the CEO agent."""

    area: str = Field(description="Area of recommendation (e.g. 'career move', 'skill gap')")
    recommendation: str = Field(description="Actionable recommendation")
    priority: str = Field(description="high, medium, or low")

class CEOOutput(BaseModel):
    """Structured output from the CEO agent with strategic recommendations and summary."""

    strategic_recommendations: list[StrategicRecommendation] = Field(default_factory=list)
    ceo_summary: str = Field(description="Executive summary of strategic outlook")


# -- CFO output --

class RiskAssessment(BaseModel):
    """A single risk assessment from the CFO agent."""

    area: str = Field(description="Area being assessed")
    risk_level: str = Field(description="low, medium, or high")
    time_investment: str = Field(description="Estimated time commitment")
    roi_estimate: str = Field(description="low, medium, or high")

class CFOOutput(BaseModel):
    """Structured output from the CFO agent with risk assessments and summary."""

    risk_assessments: list[RiskAssessment] = Field(default_factory=list)
    cfo_summary: str = Field(description="Financial/risk summary")
