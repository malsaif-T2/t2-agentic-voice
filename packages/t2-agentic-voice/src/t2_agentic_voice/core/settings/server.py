"""The `server` group: how calls are served (the design's 5.5, 11): the public address, the
pages allowed to call it, the ICE servers and the TURN secret, the dev page, and which peers'
proxy headers are trusted."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationInfo, field_validator

from t2_agentic_voice.core.settings.base import (
    PREFIX,
    Group,
    prefix_of,
    read_secret_file,
    secret,
    setting_name,
    url,
)

# A TURN credential lasts at most a day (coturn's REST scheme: the secret signs an expiry).
MAX_TURN_TTL_S = 86_400
_ICE_SCHEMES = ("stun:", "turn:", "turns:")


class ServerSettings(Group):
    """Serving: the backend's address, the pages that may call it, how media finds a path, and
    the dev page."""

    public_url: str | None = Field(
        default=None,
        description="The address callers reach the backend at, such as https://voice.example.",
    )
    allowed_origins: tuple[str, ...] = Field(
        default=(),
        description=(
            "The pages allowed to call the backend from a browser, as a JSON list of origins "
            '(scheme, host and port only), such as ["https://www.example.com"]. Unset: none.'
        ),
    )
    ice_servers: tuple[str, ...] = Field(
        default=(),
        description=(
            "The STUN and TURN servers a call is given, as a JSON list of stun:, turn: or "
            "turns: URLs with no credentials (TURN's are minted per call from turn_secret)."
        ),
    )
    turn_secret: SecretStr | None = Field(
        default=None,
        description=(
            "The secret shared with the TURN server, which signs each call's credentials: at "
            "least 32 bytes. Or give turn_secret_file instead."
        ),
    )
    turn_secret_file: Path | None = Field(
        default=None,
        description="Or the full path of a file that holds only the TURN secret.",
    )
    turn_ttl_s: int = Field(
        default=3600,
        gt=0,
        le=MAX_TURN_TTL_S,
        description="How long each call's TURN credentials last, at most 86400 (a day).",
    )
    dev_page: bool = Field(
        default=False,
        description="Whether the router serves its /dev page, to loopback clients; dev only.",
    )
    forwarded_allow_ips: tuple[str, ...] = Field(
        default=(),
        description=(
            "The proxies whose X-Forwarded-For headers are trusted, as a JSON list of IP "
            'addresses or networks, such as ["127.0.0.1"]; "*" is refused. Unset: none.'
        ),
    )

    @field_validator("public_url")
    @classmethod
    def _public(cls, value: str | None) -> str | None:
        return None if value is None else url(value, frozenset({"http", "https"}))

    @field_validator("allowed_origins")
    @classmethod
    def _origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, origin in enumerate(value):
            try:
                parts = urlsplit(url(origin, frozenset({"http", "https"})))
            except ValueError:
                parts = None
            if parts is None or parts.path or parts.query or parts.fragment:
                raise ValueError(f"origin {index} must be a scheme, a host and a port only")
        return value

    @field_validator("ice_servers")
    @classmethod
    def _ice(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, server in enumerate(value):
            host = server.partition(":")[2]
            if not server.startswith(_ICE_SCHEMES) or not host or "@" in host or not _plain(host):
                raise ValueError(
                    f"server {index} must be a stun:, turn: or turns: URL with no credentials"
                )
        return value

    @field_validator("turn_secret")
    @classmethod
    def _long_enough(cls, value: SecretStr | None, info: ValidationInfo) -> SecretStr | None:
        if value is None or not value.get_secret_value().strip():
            return None  # a blank value counts as unset
        setting = setting_name("server", "turn_secret", prefix=prefix_of(info))
        return secret(value.get_secret_value().strip(), setting)

    @field_validator("forwarded_allow_ips")
    @classmethod
    def _proxies(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, entry in enumerate(value):
            if entry.strip() == "*":
                raise ValueError(
                    "must not hold *, which trusts every peer's X-Forwarded-For; name each proxy"
                )
            if not _network(entry):
                raise ValueError(f"entry {index} is not an IP address or network")
        return value

    def resolved_turn_secret(self, prefix: str = PREFIX) -> SecretStr | None:
        """The TURN secret: `turn_secret` when set, otherwise the contents of `turn_secret_file`;
        None when neither holds one. A file that cannot be read, or a secret shorter than 32
        bytes or holding a character no key holds, raises ConfigurationError naming the
        setting it came from under `prefix`, never its value or the file's path."""
        if self.turn_secret is not None:
            return self.turn_secret
        if self.turn_secret_file is None:
            return None
        setting = setting_name("server", "turn_secret_file", prefix=prefix)
        text = read_secret_file(self.turn_secret_file, setting)
        return None if text is None else secret(text, setting)


def _network(text: str) -> bool:
    """Whether `text` is an IP address or network. Checked apart from the error it raises,
    since ipaddress's own error repeats the value, and a chained one is still reachable."""
    try:
        ipaddress.ip_network(text, strict=False)
    except ValueError:
        return False
    return True


def _plain(text: str) -> bool:
    """Whether `text` holds only printable ASCII with no space."""
    return text.isascii() and text.isprintable() and not any(c.isspace() for c in text)
