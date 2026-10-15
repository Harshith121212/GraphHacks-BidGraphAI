from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    input_path: Path = Path("./data/tenders.jsonl")
    output_path: Path = Path("./data/tenders_enriched.jsonl")
    seed: int = 42
    log_level: str = "INFO"
    log_format: str = "text"
    default_value_min: Decimal = Decimal("500000")
    default_value_max: Decimal = Decimal("50000000")

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        if self.log_format.lower() not in {"text", "json"}:
            raise ValueError("LOG_FORMAT must be text or json")
        if self.log_level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        if self.default_value_min <= 0 or self.default_value_max < self.default_value_min:
            raise ValueError("DEFAULT_VALUE_MIN/MAX must define a positive ascending range")
        if self.default_value_max > Decimal("50000000"):
            raise ValueError("DEFAULT_VALUE_MAX cannot exceed INR 50,000,000 (5 crore)")
        return self
