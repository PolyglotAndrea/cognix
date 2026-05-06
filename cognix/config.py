"""Application configuration using Pydantic Settings."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    url: str = Field(
        default="sqlite+aiosqlite:///./cognix.db",
        description="Database connection URL",
    )
    echo: bool = Field(default=False, description="Log SQL statements")


class SchedulerSettings(BaseSettings):
    jobstores: dict[str, str] = Field(default_factory=dict)
    coalesce: bool = Field(default=True, description="Coalesce missed runs")
    max_instances: int = Field(default=3, description="Max concurrent instances per job")
    misfire_grace_time: int = Field(
        default=60, description="Seconds after misfire to still execute"
    )


class RPCSettings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = Field(default=8001, description="JSON-RPC port")
    transport: Literal["http", "websocket", "unix"] = "http"
    unix_socket: str | None = None


class SkillsSettings(BaseSettings):
    local_dir: Path = Field(
        default_factory=lambda: Path.home() / ".cognix" / "skills",
        description="Local skills directory",
    )
    registry_url: str = Field(
        default="https://registry.cognix.dev",
        description="Remote skills marketplace URL",
    )
    sandbox_enabled: bool = Field(default=True, description="Run remote skills in sandbox")


class ServerSettings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    workers: int = 1


class AuthSettings(BaseSettings):
    secret_key: str = Field(
        default="change-me-in-production",
        description="JWT signing secret key",
    )
    token_expire_hours: int = Field(default=24, description="JWT token expiry in hours")
    google_client_id: str | None = None
    google_client_secret: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None


class BillingSettings(BaseSettings):
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_starter: str | None = None
    stripe_price_pro: str | None = None


class Settings(BaseSettings):
    """Root settings for the Cognix platform."""

    model_config = {"env_prefix": "COGNIX_", "env_nested_delimiter": "__"}

    # General
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".cognix",
        description="Root data directory",
    )

    # Sub-systems
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    rpc: RPCSettings = Field(default_factory=RPCSettings)
    skills: SkillsSettings = Field(default_factory=SkillsSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    billing: BillingSettings = Field(default_factory=BillingSettings)

    # LLM defaults
    default_model: str = "gpt-4o"
    llm_api_key: str | None = None
    llm_base_url: str | None = None

    def ensure_dirs(self) -> None:
        """Create required directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.skills.local_dir.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings
