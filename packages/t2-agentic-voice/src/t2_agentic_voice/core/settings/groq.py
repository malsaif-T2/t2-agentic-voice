"""The `groq` group: the key and address of Groq, the provider of every model for now (D-004)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator

from t2_agentic_voice.core.settings.base import (
    PREFIX,
    Group,
    key,
    read_secret_file,
    setting_name,
    url,
)

KEY_SETTING = setting_name("groq", "api_key")
KEY_FILE_SETTING = setting_name("groq", "api_key_file")


class GroqSettings(Group):
    """Groq, the provider of every model for now (D-004). The library reads only these names,
    never GROQ_API_KEY or GROQ_BASE_URL. The SDKs under it read a few variables of their own
    whatever is passed: leave unset those the guide lists (docs/guide/README.md, "Variables to
    leave unset")."""

    api_key: SecretStr | None = Field(
        default=None,
        description="The API key, required by the Groq adapters; or give api_key_file instead.",
    )
    api_key_file: Path | None = Field(
        default=None,
        description=(
            "Or the full path of a file outside the repository that holds only the key, so the "
            "key can live outside .env."
        ),
    )
    base_url: str = Field(
        default="https://api.groq.com",
        description=(
            "Groq's API address, always passed to the SDK so it never falls back to "
            "GROQ_BASE_URL. HTTPS only, since the key travels with every request."
        ),
    )

    @field_validator("base_url")
    @classmethod
    def _https(cls, value: str) -> str:
        parts = urlsplit(url(value, frozenset({"https"})))
        if parts.query or parts.fragment:
            raise ValueError("must hold no query or fragment: the SDK adds its own path after it")
        return value

    def resolved_api_key(self, prefix: str = PREFIX) -> SecretStr | None:
        """The key: `api_key` when set, otherwise the contents of `api_key_file` (a byte-order
        mark dropped, as Notepad and Windows PowerShell 5.1 may write one), with the space around
        them removed; None when neither holds one (a blank value counts as unset). A key file
        that cannot be read, or a key holding a character no key holds, raises
        ConfigurationError naming the setting it came from under `prefix`, never its value or
        the file's path."""
        if self.api_key is not None and self.api_key.get_secret_value().strip():
            value = self.api_key.get_secret_value().strip()
            return key(value, setting_name("groq", "api_key", prefix=prefix))
        if self.api_key_file is None:
            return None
        setting = setting_name("groq", "api_key_file", prefix=prefix)
        text = read_secret_file(self.api_key_file, setting)
        return None if text is None else key(text, setting)
