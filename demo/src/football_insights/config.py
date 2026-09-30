"""Settings, read from environment variables (and a local .env on the host).

Every setting is listed with a description in the repository's .env.example.
Empty values fall back to the defaults below, so a blank .env line is harmless.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    # Data
    football_data_dir: Path = Path("data")
    curated_dir: Path = Path(".local/curated")
    curated_source: Literal["local", "blob"] = "local"
    storage_account_url: str = ""
    raw_container: str = "raw"
    curated_container: str = "curated"

    # Services
    insights_url: str = "http://localhost:8081"
    web_port: int = 8080
    insights_port: int = 8081
    web_rate_limit_per_minute: int = 60
    ask_rate_limit_per_minute: int = 6
    log_level: str = "INFO"

    # Microsoft Foundry
    foundry_project_endpoint: str = ""
    ai_model_deployment: str = "gpt-6-astra"
    ai_allowed_deployments: str = "gpt-6-astra,gpt-6-sol"
    ai_reasoning_effort: str = "low"
    ai_narrative_mode: Literal["live", "cached", "off"] | None = None
    ai_max_tool_calls: int = 6
    ai_max_output_tokens: int = 1200
    ai_timeout_seconds: float = 45.0
    question_max_chars: int = 300
    narrative_cache_dir: Path = Path(".local/narratives")

    # Identity
    azure_client_id: str = ""
    azure_token_file: str = ""

    # Telemetry
    applicationinsights_connection_string: str = ""
    otel_service_name: str = ""
    local_trace_dir: Path = Path(".local/traces")

    # Environment badge, injected by deployment configuration
    platform_name: str = "Local"
    platform_region: str = ""
    image_digest: str = ""

    # Evidence written by operator commands
    evidence_dir: Path = Path(".local/evidence")

    @property
    def narrative_mode(self) -> Literal["live", "cached", "off"]:
        if self.ai_narrative_mode:
            return self.ai_narrative_mode
        return "live" if self.foundry_project_endpoint else "off"

    @property
    def allowed_deployments(self) -> list[str]:
        return [d.strip() for d in self.ai_allowed_deployments.split(",") if d.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
