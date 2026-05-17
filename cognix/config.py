"""Application configuration using Pydantic Settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

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
    dispatcher_poll_interval: float = Field(
        default=5.0, description="Distributed dispatcher poll interval",
    )
    dispatcher_batch_size: int = Field(
        default=10, description="Max tasks claimed per dispatcher poll",
    )
    dispatcher_max_concurrent: int = Field(
        default=3, description="Max concurrent distributed task runs per node",
    )
    dispatcher_lease_ttl_seconds: int = Field(default=120, description="Distributed task lease TTL")
    retry_base_seconds: int = Field(default=30, description="Initial distributed task retry delay")
    retry_max_seconds: int = Field(default=3600, description="Maximum distributed task retry delay")


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
    frontend_url: str = Field(
        default="http://localhost:5173",
        description="Frontend base URL used for OAuth callback redirects",
    )

    def model_post_init(self, __context: Any) -> None:
        import os

        if (
            self.secret_key == "change-me-in-production"
            and not os.environ.get("COGNIX_DEBUG")
        ):
            raise ValueError(
                "COGNIX_AUTH__SECRET_KEY must be set to a secure value. "
                "The default 'change-me-in-production' is not allowed in production."
            )


class BillingSettings(BaseSettings):
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_starter: str | None = None
    stripe_price_pro: str | None = None


class ConnectorSettings(BaseSettings):
    encryption_key: str | None = Field(
        default=None,
        description="Fernet key for connector tokens. Falls back to auth.secret_key.",
    )
    x_client_id: str | None = None
    x_client_secret: str | None = None
    instagram_client_id: str | None = None
    instagram_client_secret: str | None = None


class MemorySettings(BaseSettings):
    compress_model: str = Field(
        default="gpt-4o-mini",
        description="Model used for memory compression summarization",
    )
    compress_older_than_days: int = Field(
        default=7,
        description="Compress cold memories older than this many days",
    )
    compress_batch_size: int = Field(
        default=5,
        description="Number of memories to summarize per LLM call",
    )
    auto_compress_enabled: bool = Field(
        default=False,
        description="Enable automatic periodic memory compression",
    )
    auto_compress_interval_hours: int = Field(
        default=24,
        description="Hours between automatic compression runs",
    )


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
    connectors: ConnectorSettings = Field(default_factory=ConnectorSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)

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
