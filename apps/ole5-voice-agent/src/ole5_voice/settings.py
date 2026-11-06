"""The Ole5 app's settings (the design's 7.3): its own under `OLE5_VOICE_`, and the library's
under `T2V_`, both read from the environment and, only when one is given, a `.env` file; the
environment wins over the file. This is the only module of the app that reads the environment.

The app's own, for its server (server.py) and its token route (token_route.py):
- `OLE5_VOICE_ACCESS_CODE`, required: the code the owner types in the widget to get a join
  token (plan 003, Q4), at least 16 characters, made with `GENERATOR`;
- `OLE5_VOICE_WEBSITE_ORIGIN`: the website allowed to frame the widget's page
  (`frame-ancestors`), an origin as a browser sends it; unset, no page may frame it.

And for its knowledge base (plan 006, Q4), which the talker searches through T2's embedding
gateway and T2's Qdrant: the account it logs in with (`OLE5_VOICE_KB_LOGIN_EMAIL` and
`OLE5_VOICE_KB_LOGIN_PASSWORD`) and the key (`OLE5_VOICE_KB_API_KEY`), all optional, the owner's
to copy into `.env`; and the addresses and the tenant, each with T2's default
(`OLE5_VOICE_KB_QDRANT_URL`, `OLE5_VOICE_KB_LOGIN_URL`, `OLE5_VOICE_KB_EMBEDDING_URL`,
`OLE5_VOICE_KB_TENANT`). With none of them set the app still starts, its agent the echo.

A blank value counts as unset, as the library's do. The library's settings are
`VoiceSettings.from_env`'s, and the token route signs every token with the join key
`T2V_JOIN__CURRENT_KID` names, so that one is required too. Every failure is one
ConfigurationError naming each setting that cannot load, never its value, with a FIX line.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from t2_agentic_voice import ConfigurationError, ServerSettings, VoiceSettings

# The app's prefix (the design's 7.3): one the library's settings never use.
PREFIX: Final = "OLE5_VOICE_"
# The fewest characters an access code holds (Q4), and the command that makes one of 32.
MIN_ACCESS_CODE_CHARS: Final = 16
GENERATOR: Final = 'python -c "import secrets; print(secrets.token_urlsafe(24))"'
_FIX: Final = (
    "FIX: set each one in the environment or the .env file given; make an access code with "
    f"{GENERATOR}."
)


class AppSettings(BaseSettings):
    """The Ole5 app's own settings, read-only once loaded."""

    model_config = SettingsConfigDict(
        env_prefix=PREFIX,
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    access_code: SecretStr = Field(
        description=(
            "The code the owner types in the widget to get a join token, at least 16 characters."
        ),
    )
    website_origin: str | None = Field(
        default=None,
        description=(
            "The website allowed to frame the widget's page, an origin as a browser sends it "
            "(https://www.example.com). Unset: no page may frame it."
        ),
    )

    kb_login_email: str | None = Field(
        default=None,
        max_length=254,
        description="The account the app logs in to the knowledge base's service with.",
    )
    kb_login_password: SecretStr | None = Field(
        default=None, description="That account's password."
    )
    kb_api_key: SecretStr | None = Field(
        default=None, description="The key the knowledge base's service takes with a request."
    )
    kb_qdrant_url: str = Field(
        default="https://ds.t2.sa:443/ole5_agent/qdrant",
        description="T2's Qdrant, which holds Ole5's points, over HTTPS.",
    )
    kb_login_url: str = Field(
        default="https://ds.t2.sa/ole5_agent/api/login",
        description="Where the app logs in to the knowledge base's service, over HTTPS.",
    )
    kb_embedding_url: str = Field(
        default="https://ds.t2.sa/text_embed",
        description="T2's embedding gateway, which embeds each question, over HTTPS.",
    )
    kb_tenant: str = Field(
        default="ole5",
        pattern=r"^[A-Za-z0-9_.-]{1,64}$",
        description="The tenant whose points the search reads.",
    )

    @field_validator("kb_login_email")
    @classmethod
    def _an_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name, at, host = value.strip().rpartition("@")
        if not (name and at and "." in host) or any(c.isspace() for c in value.strip()):
            raise ValueError("is not an email address: a name, an @ and a host")
        return value.strip()

    @field_validator("kb_qdrant_url", "kb_login_url", "kb_embedding_url")
    @classmethod
    def _https(cls, value: str) -> str:
        try:
            parts = urlsplit(value)
            port = parts.port  # read, so urllib checks it
        except ValueError:  # its error repeats the value: not chained
            parts, port = None, None
        if parts is None or parts.scheme != "https" or not parts.hostname or port == 0:
            raise ValueError("must be an https:// URL with a host")
        if parts.username is not None or parts.password is not None:
            raise ValueError("must hold no user name or password; they have settings of their own")
        return value

    @field_validator("access_code")
    @classmethod
    def _long_enough(cls, value: SecretStr) -> SecretStr:
        code = value.get_secret_value().strip()
        if len(code) < MIN_ACCESS_CODE_CHARS:
            raise ValueError(f"holds fewer than {MIN_ACCESS_CODE_CHARS} characters")
        return SecretStr(code)

    @field_validator("website_origin")
    @classmethod
    def _an_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ServerSettings(allowed_origins=(value,))  # the library's rule for an origin
        except ValidationError:
            pass  # its errors hold the value: not chained
        else:
            return value
        raise ValueError(
            "is not an origin as a browser sends it: a lowercase scheme and host, and a port "
            "only when it is not the scheme's own"
        )


@dataclass(frozen=True)
class Settings:
    """What the app runs with: its own settings, and the library's."""

    app: AppSettings
    voice: VoiceSettings


def load(env_file: Path | None = None) -> Settings:
    """The app's settings and the library's, from the environment and `env_file` when given;
    ConfigurationError naming each setting that cannot load."""
    voice = VoiceSettings.from_env(env_file=env_file)
    refused: ConfigurationError | None = None
    try:
        app = AppSettings(_env_file=env_file, _env_file_encoding="utf-8")
    except ValidationError as error:
        refused = _cannot_load(error)
    if refused is not None:  # raised here, so no chain leads back to the values refused
        raise refused
    if voice.join.current_kid is None:
        name = voice.env_name("join", "current_kid")
        raise ConfigurationError(
            f"{name} is not set, and the token route signs every join token with that key. "
            f"FIX: set it to the ID of a key in {voice.env_name('join', 'keys')}.",
            details={"settings": [name]},
        )
    return Settings(app=app, voice=voice)


def _cannot_load(error: ValidationError) -> ConfigurationError:
    """One error naming each setting of the app's that cannot load, never its value."""
    named = []
    for problem in error.errors(include_input=False, include_url=False):
        name = PREFIX + "__".join(str(part).upper() for part in problem["loc"])
        why = problem["msg"].removeprefix("Value error, ")
        named.append((name, "is not set" if problem["type"] == "missing" else why))
    listed = "; ".join(f"{name} {why}" for name, why in named)
    return ConfigurationError(
        f"The Ole5 app's settings cannot load: {listed}. {_FIX}",
        details={"settings": [name for name, _ in named]},
    )
