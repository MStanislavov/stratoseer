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
    goal_extractor_model: str = "gpt-5.4"
    web_scraper_model: str = "gpt-5.4"
    data_formatter_model: str = _DEFAULT_AGENT_MODEL
    ceo_model: str = _DEFAULT_AGENT_MODEL
    cfo_model: str = _DEFAULT_AGENT_MODEL
    cover_letter_model: str = _DEFAULT_AGENT_MODEL
    url_validator_model: str = _DEFAULT_AGENT_MODEL

    # Search
    search_max_results: int = 10
    search_fetch_top_n: int = 5

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
