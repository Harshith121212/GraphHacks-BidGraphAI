from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from TENDERSCRAPE_* variables and .env."""

    model_config = SettingsConfigDict(
        env_prefix="TENDERSCRAPE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    output_dir: Path = Path("./data")
    output_filename: str = "tenders.jsonl"
    request_delay: float = Field(default=1.5, ge=1.0)
    request_timeout_seconds: float = Field(default=30.0, gt=0)
    global_timeout_seconds: float = Field(default=21600.0, gt=0)
    max_retries: int = Field(default=3, ge=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["text", "json"] = "text"
    enable_cppp: bool = True
    enable_cpwd: bool = True
    enable_gem: bool = True
    enable_ireps: bool = True
    http_proxy: SecretStr | None = None
    user_agent: str = "TenderScrape/0.1 (+public listing collector)"
    lock_stale_hours: float = Field(default=2.0, gt=0)
    gem_max_pages: int | None = Field(default=None, ge=1)

    @field_validator("output_filename")
    @classmethod
    def filename_only(cls, value: str) -> str:
        candidate = Path(value)
        if not value.strip() or candidate.name != value or value in {".", ".."}:
            raise ValueError("OUTPUT_FILENAME must be a filename, not a path")
        return value

    @field_validator("http_proxy", mode="before")
    @classmethod
    def empty_proxy_is_unset(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def proxy_url(self) -> str | None:
        return self.http_proxy.get_secret_value() if self.http_proxy else None

    @property
    def output_path(self) -> Path:
        return self.output_dir / self.output_filename

    def portal_enabled(self, portal: str) -> bool:
        return bool(getattr(self, f"enable_{portal}"))
