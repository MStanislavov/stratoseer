from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    postgres_user: str = "assistant"
    postgres_password: str = "assistant"
    postgres_db: str = "assistant"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Server
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_reload: bool = True

    # Paths
    policy_dir: Path = Path("policy")
    artifacts_dir: Path = Path("artifacts")

    # Logging
    log_level: str = "INFO"
    db_echo: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
