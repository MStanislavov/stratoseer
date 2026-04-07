from pathlib import Path

from pydantic_settings import BaseSettings

# Project root: two levels up from app/config.py
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_AGENT_MODEL = "gpt-5.4-mini"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # Database
    postgres_user: str = "assistant"
    postgres_password: str = "assistant"
    postgres_db: str = "assistant"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Server
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_reload: bool = False

    # Paths (resolved relative to project root)
    policy_dir: Path = _PROJECT_ROOT / "policy"
    artifacts_dir: Path = _PROJECT_ROOT / "artifacts"
    prompts_dir: Path = _PROJECT_ROOT / "prompts"

    def model_post_init(self, __context: object) -> None:
        """Resolve relative paths against the project root."""
        for field in ("policy_dir", "artifacts_dir", "prompts_dir"):
            path = getattr(self, field)
            if not path.is_absolute():
                object.__setattr__(self, field, _PROJECT_ROOT / path)

    # Logging
    log_level: str = "DEBUG"
    db_echo: bool = False

    # LLM
    api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.3

    # Per-agent model overrides (blank = use llm_model default)
    goal_extractor_model: str = _DEFAULT_AGENT_MODEL
    web_scraper_model: str = _DEFAULT_AGENT_MODEL
    data_formatter_model: str = _DEFAULT_AGENT_MODEL
    ceo_model: str = _DEFAULT_AGENT_MODEL
    cfo_model: str = _DEFAULT_AGENT_MODEL
    cover_letter_model: str = _DEFAULT_AGENT_MODEL

    # LangSmith tracing (dev only -- disable in production to avoid costs)
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "ai-executive-assistant"

    # Search
    search_max_results: int = 10
    search_fetch_top_n: int = 5

    # BYOK (Bring Your Own Key)
    api_key_encryption_secret: str = "change-me-to-a-long-random-string-for-encryption"
    free_run_limit: int = 1

    # Auth
    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_access_expiry_minutes: int = 30
    jwt_refresh_expiry_days: int = 7

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # Email (SMTP)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""

    # App
    app_base_url: str = "http://localhost:8000"
    cors_origins: str = ""  # comma-separated extra origins, e.g. "https://myapp.onrender.com,https://custom.domain"
    admin_email: str = ""

    model_config = {
        "env_file": Path(__file__).resolve().parent.parent / ".env",
        "extra": "ignore",
    }

    @property
    def database_url(self) -> str:
        """Return the async PostgreSQL connection URL (asyncpg driver)."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Return the synchronous PostgreSQL connection URL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
