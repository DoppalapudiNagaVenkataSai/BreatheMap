"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """BreatheMap typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: Literal["development", "production", "test"] = "development"
    APP_SECRET: str = Field(default="dev-secret-key-at-least-32-chars-long-here")
    LOG_LEVEL: str = "INFO"
    STORE_BACKEND: Literal["memory", "firestore"] = "memory"
    DEMO_MODE: Literal["off", "allow", "force"] = "allow"

    NOMINATIM_CONTACT_EMAIL: str = "contact@example.com"
    ORS_API_KEY: str | None = None

    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_ENABLED: bool = False
    GEMINI_DAILY_LIMIT: int = 18
    GEMINI_RPM_LIMIT: int = 4
    ASSISTANT_AI_PER_IP_PER_DAY: int = 5

    FIREBASE_PROJECT_ID: str | None = None
    FIRESTORE_CREDENTIALS_B64: str | None = None

    ADMIN_TOKEN: str | None = None

    @field_validator("APP_SECRET")
    @classmethod
    def validate_app_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("APP_SECRET must be at least 32 characters long")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
