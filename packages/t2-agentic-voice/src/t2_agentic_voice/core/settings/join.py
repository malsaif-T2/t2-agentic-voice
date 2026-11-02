"""The `join` group: the keys that sign and verify join tokens, and their lifetime (the design's
6.5). Any listed key verifies and `current_kid` signs, so a key rotates by adding a new one,
switching `current_kid`, then removing the old one.

The key map is given inline (`T2V_JOIN__KEYS`) or in a file (`T2V_JOIN__KEYS_FILE`); both hold
the same form, one JSON object from key ID to secret: `{"2026-11": "<at least 32 bytes>"}`. Each
secret is at least 32 bytes, checked as the settings load for an inline map and as the file is
read for a file's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import (
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.base import (
    PREFIX,
    Group,
    prefix_of,
    read_secret_file,
    secret,
    setting_name,
)

# A key ID travels in each token's `kid` header, which the caller can read: a short name.
KeyId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._-]{1,64}$")]
# A join token lives 120 s at most (the design's 6.5).
MAX_TTL_S = 120
_KEY_MAP = TypeAdapter(dict[KeyId, str], config=ConfigDict(hide_input_in_errors=True))


class JoinSettings(Group):
    """Join tokens: the keys that sign and verify them, and how long one lives."""

    keys: dict[KeyId, SecretStr] = Field(
        default_factory=dict,
        description=(
            "The keys that verify join tokens, as a JSON object from key ID to secret, each "
            "secret at least 32 bytes. Or give keys_file instead."
        ),
    )
    keys_file: Path | None = Field(
        default=None,
        description=(
            "Or the full path of a file that holds the key map, the same JSON object as keys."
        ),
    )
    current_kid: KeyId | None = Field(
        default=None,
        description="The ID of the key that signs new tokens; one of the map's.",
    )
    ttl_s: int = Field(
        default=60,
        gt=0,
        le=MAX_TTL_S,
        description="How long a join token lives, at most 120.",
    )
    max_clock_skew_s: int = Field(
        default=30,
        ge=0,
        description="How far a token's times may be off this machine's clock and still verify.",
    )

    @field_validator("keys")
    @classmethod
    def _long_enough(
        cls, value: dict[str, SecretStr], info: ValidationInfo
    ) -> dict[str, SecretStr]:
        setting = setting_name("join", "keys", prefix=prefix_of(info))
        return {kid: secret(s.get_secret_value().strip(), setting) for kid, s in value.items()}

    @model_validator(mode="after")
    def _current_is_listed(self, info: ValidationInfo) -> JoinSettings:
        if self.keys:
            _check_current(self.current_kid, self.keys, prefix_of(info))
        return self

    def resolved_keys(self, prefix: str = PREFIX) -> dict[str, SecretStr]:
        """The key map: `keys` when it holds any, otherwise the file's (empty when neither
        holds one). A file that cannot be read, that holds no such JSON object, or whose secret
        is shorter than 32 bytes, and a `current_kid` the map does not list, raise
        ConfigurationError naming the setting under `prefix`, never a value or the path."""
        if self.keys or self.keys_file is None:
            return dict(self.keys)
        setting = setting_name("join", "keys_file", prefix=prefix)
        text = read_secret_file(self.keys_file, setting)
        if text is None:
            return {}
        try:
            parsed = _KEY_MAP.validate_json(text)
        except ValidationError:
            parsed = None  # its errors hold the file's text: not chained
        if parsed is None:
            raise ConfigurationError(
                f"{setting} does not hold one JSON object from key ID to secret. FIX: write the "
                'file as {"<key ID>": "<secret>"}, each key ID letters, digits, ".", "_" or "-".',
                details={"setting": setting},
            )
        keys = {kid: secret(value.strip(), setting) for kid, value in parsed.items()}
        _check_current(self.current_kid, keys, prefix)
        return keys


def _check_current(current: str | None, keys: dict[str, SecretStr], prefix: str) -> None:
    """ConfigurationError when `current` names a key `keys` does not list."""
    if current is not None and current not in keys:
        setting = setting_name("join", "current_kid", prefix=prefix)
        raise ConfigurationError(
            f"{setting} names no key of the join key map. FIX: give the ID of one of its keys.",
            details={"setting": setting},
        )
