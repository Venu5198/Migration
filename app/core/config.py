from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MIGRATION_", extra="ignore")

    env: str = "development"
    mongodb_uri: str | None = None
    upload_dir: Path = Path("data/uploads")
    report_dir: Path = Path("data/reports")
    max_upload_bytes: int = 50 * 1024 * 1024
    allow_xlsm: bool = False
    cors_origins: str = ""
    auth_required: bool = False
    auth_tokens: str = ""
    max_job_attempts: int = 3

    enforce_separation_of_duties: bool = True

    def is_production(self) -> bool:
        return self.env.lower() in {"production", "prod"}

    def require_auth(self) -> bool:
        if self.is_production() and not self.auth_tokens:
            raise ValueError("MIGRATION_AUTH_TOKENS is required in production")
        return self.auth_required or self.is_production()

    def validate_production(self) -> None:
        if self.is_production():
            if not self.auth_tokens:
                raise ValueError("MIGRATION_AUTH_TOKENS is required in production")
            if not self.mongodb_uri or not self.mongodb_uri.strip():
                raise ValueError(
                    "MIGRATION_MONGODB_URI is required in production "
                    "(ephemeral in-memory persistence is forbidden)"
                )


settings = Settings()
