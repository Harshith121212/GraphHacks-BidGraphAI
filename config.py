"""Configuration module for Tender Intelligence System."""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    FALKORDB_INSTANCE_ID: Optional[str] = None
    FALKORDB_HOST: str = "localhost"
    FALKORDB_PORT: int = 6379
    FALKORDB_USERNAME: Optional[str] = None
    FALKORDB_PASSWORD: Optional[str] = None
    FALKORDB_SSL: bool = False
    FALKORDB_URL: Optional[str] = None
    FALKORDB_GRAPH_NAME: str = "tender_intel_graph"

    OPENAI_API_KEY: Optional[str] = None
    HF_TOKEN: Optional[str] = None
    HUGGINGFACE_API_KEY: Optional[str] = None
    NVIDIA_API_KEY: Optional[str] = None

    OPENROUTER_MODEL: str = "nvidia/nemotron-3.5-super-vl:free"
    OPENROUTER_API_KEY_ALPHA: Optional[str] = None
    OPENROUTER_API_KEY_BETA: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None

    @property
    def hf_token(self) -> Optional[str]:
        return self.HF_TOKEN or self.HUGGINGFACE_API_KEY

    @property
    def gemini_api_key(self) -> Optional[str]:
        return self.GEMINI_API_KEY or self.GOOGLE_API_KEY

    @property
    def openrouter_api_key(self) -> Optional[str]:
        return self.OPENROUTER_API_KEY or self.OPENROUTER_API_KEY_ALPHA or self.OPENROUTER_API_KEY_BETA


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings instance loaded from environment / .env."""
    return Settings()
