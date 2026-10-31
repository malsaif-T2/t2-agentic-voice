"""Application settings: the only module that reads the environment (ARCH-ENV).

Every configurable value is a field on `Settings`, loaded from environment variables with this
project's prefix, or from a local `.env` file (environment variables win). Other modules call
`get_settings()` or receive a `Settings` instance; they never touch `os.environ`.

When you add a field, add it to `.env.example` too (tests/core/test_config.py fails otherwise).
A secret is a `SecretStr` field, so it never shows in a repr or a log.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["console", "json"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OLE5_VOICE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = "dev"
    log_level: LogLevel = "INFO"
    # console (human-readable) or json (machine-queryable)
    log_format: LogFormat = "console"
    # Local runtime data (git-ignored): databases, run outputs, caches. Every path under it
    # comes from here, so one setting moves a whole run, a test session included.
    var_dir: Path = Path("var")


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings, loaded once. Tests construct `Settings` directly instead."""
    return Settings()
