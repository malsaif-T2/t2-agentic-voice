"""The `join` group: the keys that sign and verify join tokens, and their lifetime (the design's
6.5). Any listed key verifies and `current_kid` signs, so a key rotates by adding a new one,
switching `current_kid`, then removing the old one.

The key map is given inline (`T2V_JOIN__KEYS`) or in a file (`T2V_JOIN__KEYS_FILE`); both hold
the same form, one JSON object from key ID to secret: `{"2026-11": "<at least 32 bytes>"}`. Each
secret is at least 32 bytes, checked as the settings load for an inline map and as the file is
read for a file's.

A token verifies until its `exp` plus `max_clock_skew_s`, so its lifetime has a bound only while
the skew has one: at most `MAX_CLOCK_SKEW_S`. The used-token store keeps a token's ID until its
`exp` plus `MAX_CLOCK_SKEW_S`, the latest any allowance lets it verify, so a restart with a
larger allowance finds every token it could take again (domain/ports/identity.py).
"""

from __future__ import annotations

from collections.abc import Mapping
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
)

from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.base import (
    FROZEN,
    PLAIN,
    PREFIX,
    Group,
    read_only,
    read_secret_file,
    secret,
    setting_name,
    shared_secret,
)

# A key ID travels in each token's `kid` header, which the caller can read: a short name.
KeyId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._-]{1,64}$")]
# A join token lives 120 s at most (the design's 6.5).
MAX_TTL_S = 120
# How far a token's times may be off this machine's clock, at most: the verifier takes a token
# until its `exp` plus the skew, so a 120 s token is usable for at most 120 + 2 x 60 s; and the
# used-token store keeps each token's ID until its `exp` plus this bound, whatever the skew.
MAX_CLOCK_SKEW_S = 60
_KEY_MAP = TypeAdapter(dict[KeyId, str], config=ConfigDict(hide_input_in_errors=True))


class JoinSettings(Group):
    """Join tokens: the keys that sign and verify them, and how long one lives."""

    keys: Annotated[Mapping[KeyId, SecretStr], FROZEN, PLAIN] = Field(
        default_factory=dict,
        validate_default=True,
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
        le=MAX_CLOCK_SKEW_S,
        description=(
            "How far a token's times may be off this machine's clock and still verify, at most "
            "60: a token verifies until its expiry plus this."
        ),
    )

    @field_validator("keys")
    @classmethod
    def _long_enough(cls, value: Mapping[str, SecretStr]) -> Mapping[str, SecretStr]:
        return read_only({k: shared_secret(s.get_secret_value().strip()) for k, s in value.items()})

    @field_validator("current_kid")
    @classmethod
    def _listed(cls, value: str | None, info: ValidationInfo) -> str | None:
        keys = info.data.get("keys")  # absent when the map itself failed
        if value is not None and keys and value not in keys:
            raise ValueError("names no key of the join key map; give the ID of one of its keys")
        return value

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
        if self.current_kid is not None and self.current_kid not in keys:
            current = setting_name("join", "current_kid", prefix=prefix)
            raise ConfigurationError(
                f"{current} names no key of the join key map. FIX: give the ID of one of its keys.",
                details={"setting": current},
            )
        return keys
