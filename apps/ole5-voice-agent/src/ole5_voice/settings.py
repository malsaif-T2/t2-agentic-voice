"""The Ole5 app's settings (the design's 7.3): its own under `OLE5_VOICE_`, and the library's
under `T2V_`, both read from the environment and, only when one is given, a `.env` file; the
environment wins over the file. This is the only module of the app that reads the environment.

The app's own, for its server (server.py) and its token route (the library's, server.py):
- `OLE5_VOICE_ACCESS_CODE`, required: the code the owner types in the widget to get a join
  token (plan 003, Q4), at least 16 characters, made with `GENERATOR`;
- `OLE5_VOICE_WEBSITE_ORIGIN`: the website allowed to frame the widget's page
  (`frame-ancestors`), an origin as a browser sends it; unset, no page may frame it.

And for its mock ticket system (plan 007, tickets/):
- `OLE5_VOICE_DEMO_CUSTOMER_EMAIL`: the customer every join token names (Q3), whose tickets a
  call makes and reads (customer.py), `DEMO_CUSTOMER_EMAIL` unless set; nothing said in a call
  changes it. Under `env` dev, and only then, `load` also names that customer the library's
  `server.dev_caller`, so a call the test console starts is theirs, as a widget's call is;
- `OLE5_VOICE_TICKETS_MODE`: how the mock answers each write, `answer` unless set, or
  `refuse`, `timeout` or `late` for a demo of each (tickets/mock.py);
- `OLE5_VOICE_TICKETS_LOOKUP`: whether the mock finds a write by its request ID, true unless
  set, false to behave as the real system is thought to;
- `OLE5_VOICE_TICKETS_DIR`: the folder its tickets are kept in, unless set the app's own under
  the library's `storage.var_dir` (`tickets_folder`).

And for its knowledge base (plan 006, Q4), which the talker searches through T2's embedding
service and T2's Qdrant behind T2's sign-in gateway. That service is T2's, shared by every team,
so its settings are read under the general names the owner set, with no prefix (the owner, on
2026-11-06: "Ole5 naming is not general enough"): `QDRANT_URL`, and the account the app signs in
with, `QDRANT_LOGIN_EMAIL` and `QDRANT_LOGIN_PASSWORD`; and, each with T2's default,
`QDRANT_LOGIN_URL` and `EMBEDDING_URL`. Only the tenant, Ole5's own, keeps the prefix
(`OLE5_VOICE_KB_TENANT`). The access is all or none (`knowledge_access`): with none of the three
set the app still starts, its agent the echo; with all three, its agent is the talker, which
searches the knowledge base; with only some, it refuses to start, naming the ones missing.

A measurement run reads the knowledge base's access alone (`KnowledgeSettings`,
`load_knowledge`), with no access code or widget setting. A blank value counts as unset, as the
library's do. The library's settings are
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

from ole5_voice.customer import demo_caller
from ole5_voice.tickets.mock import Mode

# The app's prefix (the design's 7.3): one the library's settings never use.
PREFIX: Final = "OLE5_VOICE_"
# The demo customer every join token names unless the owner sets another (plan 007's Q3): the
# prototype's Ole5 test customer (Ole5-chatbot/sheets/customers.xlsx).
DEMO_CUSTOMER_EMAIL: Final = "ole5.test@example.com"
# The app's own folder under the library's `storage.var_dir`, and its tickets' folder in it.
APP_FOLDER: Final = "ole5"
TICKETS_FOLDER: Final = "tickets"
# The fewest characters an access code holds (Q4), and the command that makes one of 32.
MIN_ACCESS_CODE_CHARS: Final = 16
GENERATOR: Final = 'python -c "import secrets; print(secrets.token_urlsafe(24))"'
# The settings read under a general name with no prefix: T2's knowledge-base service's, which
# every team shares (the owner's names).
UNPREFIXED: Final = (
    "QDRANT_URL",
    "QDRANT_LOGIN_EMAIL",
    "QDRANT_LOGIN_PASSWORD",
    "QDRANT_LOGIN_URL",
    "EMBEDDING_URL",
)
# The settings the knowledge base's access needs, all three or none: where, and the account.
ACCESS: Final = ("QDRANT_URL", "QDRANT_LOGIN_EMAIL", "QDRANT_LOGIN_PASSWORD")
_FIX: Final = (
    "FIX: set each one in the environment or the .env file given; make an access code with "
    f"{GENERATOR}."
)


class KnowledgeSettings(BaseSettings):
    """The knowledge base's access, read-only once loaded: all a measurement run needs of the
    app's settings (`load_knowledge`), with no access code or widget setting."""

    model_config = SettingsConfigDict(
        env_prefix=PREFIX,
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    qdrant_url: str | None = Field(
        default=None,
        validation_alias="QDRANT_URL",
        description="T2's Qdrant behind its sign-in gateway, over HTTPS. Unset: no knowledge base.",
    )
    qdrant_login_email: str | None = Field(
        default=None,
        validation_alias="QDRANT_LOGIN_EMAIL",
        max_length=254,
        description="The account the app signs in to T2's gateway with.",
    )
    qdrant_login_password: SecretStr | None = Field(
        default=None,
        validation_alias="QDRANT_LOGIN_PASSWORD",
        description="That account's password.",
    )
    qdrant_login_url: str = Field(
        default="https://ds.t2.sa/ole5_agent/api/login",
        validation_alias="QDRANT_LOGIN_URL",
        description="Where the app signs in to T2's gateway, over HTTPS.",
    )
    embedding_url: str = Field(
        default="https://ds.t2.sa/text_embed",
        validation_alias="EMBEDDING_URL",
        description="T2's embedding service, which embeds each question, over HTTPS.",
    )
    kb_tenant: str = Field(
        default="ole5",
        pattern=r"^[A-Za-z0-9_.-]{1,64}$",
        description="The tenant whose points the search reads: Ole5's own.",
    )

    @field_validator("qdrant_login_email")
    @classmethod
    def _an_email(cls, value: str | None) -> str | None:
        return None if value is None else _email(value)

    @field_validator("qdrant_url", "qdrant_login_url", "embedding_url")
    @classmethod
    def _https(cls, value: str | None) -> str | None:
        if value is None:
            return None
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


class AppSettings(KnowledgeSettings):
    """The Ole5 app's own settings, the knowledge base's access among them, read-only once
    loaded."""

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
    demo_customer_email: str = Field(
        default=DEMO_CUSTOMER_EMAIL,
        max_length=254,
        description=(
            "The customer every join token names, whose tickets a call makes and reads. "
            "Nothing said in a call changes it."
        ),
    )
    tickets_mode: Mode = Field(
        default="answer",
        description=(
            "How the mock ticket system answers each write: answer, refuse, timeout (no reply, "
            "nothing done) or late (done, the reply late)."
        ),
    )
    tickets_lookup: bool = Field(
        default=True,
        description="Whether the mock ticket system finds a write by its request ID.",
    )
    tickets_dir: Path | None = Field(
        default=None,
        description=(
            "The folder the mock ticket system keeps its tickets in. Unset: ole5/tickets under "
            "the library's storage.var_dir."
        ),
    )

    @field_validator("demo_customer_email")
    @classmethod
    def _a_customer(cls, value: str) -> str:
        return _email(value)

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


@dataclass(frozen=True, kw_only=True)
class KnowledgeAccess:
    """What the knowledge base is reached with (knowledge_base.py): Qdrant's URL, the gateway's
    sign-in URL and the account, the embedding service's URL, and the tenant whose points a
    search reads. The password is kept a secret: no repr shows it."""

    qdrant_url: str
    login_url: str
    login_email: str
    login_password: SecretStr
    embedding_url: str
    tenant: str


def knowledge_access(app: KnowledgeSettings) -> KnowledgeAccess | None:
    """The knowledge base's access when `app` sets all three of `ACCESS`, None when it sets
    none (the agent is then the echo); a ConfigurationError naming the ones missing when it
    sets only some, never a value."""
    url, email, password = app.qdrant_url, app.qdrant_login_email, app.qdrant_login_password
    given = (url, email, password)
    missing = [name for name, value in zip(ACCESS, given, strict=True) if value is None]
    if len(missing) == len(ACCESS):
        return None
    if url is None or email is None or password is None:
        *rest, last = missing
        listed = f"{', '.join(rest)} and {last}" if rest else last
        verb = "are" if rest else "is"
        raise ConfigurationError(
            f"The knowledge base's access is set only in part: {listed} {verb} not set. FIX: set "
            "all three of QDRANT_URL, QDRANT_LOGIN_EMAIL and QDRANT_LOGIN_PASSWORD for the "
            "talker, which searches it, or none of them for the echo.",
            details={"settings": [*missing]},
        )
    return KnowledgeAccess(
        qdrant_url=url,
        login_url=app.qdrant_login_url,
        login_email=email,
        login_password=password,
        embedding_url=app.embedding_url,
        tenant=app.kb_tenant,
    )


@dataclass(frozen=True)
class Settings:
    """What the app runs with: its own settings, and the library's."""

    app: AppSettings
    voice: VoiceSettings


def load(env_file: Path | None = None) -> Settings:
    """The app's settings and the library's, from the environment and `env_file` when given,
    the demo customer the test console's dev caller under `env` dev (`with_dev_caller`);
    ConfigurationError naming each setting that cannot load, or the knowledge base's access
    set only in part (`knowledge_access`)."""
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
    knowledge_access(app)  # all three or none, refused here before anything is built
    return Settings(app=app, voice=with_dev_caller(voice, app.demo_customer_email))


def with_dev_caller(voice: VoiceSettings, email: str) -> VoiceSettings:
    """Under `env` dev alone, `voice` with the demo customer `email` as the test console's dev
    caller (`server.dev_caller`), every other setting as it was; `voice` itself under any other
    `env`, so the console mints no token outside dev."""
    if voice.env != "dev":
        return voice
    server = ServerSettings.model_validate(
        voice.server.model_dump() | {"dev_caller": demo_caller(email)}
    )
    return voice.model_copy(update={"server": server})


def load_knowledge(env_file: Path | None = None) -> KnowledgeAccess:
    """The knowledge base's access alone, from the environment and `env_file` when given (a
    measurement run's, which needs no access code); a ConfigurationError naming each setting
    that cannot load, or that is not set, never a value."""
    refused: ConfigurationError | None = None
    try:
        loaded = KnowledgeSettings(_env_file=env_file, _env_file_encoding="utf-8")
    except ValidationError as error:
        refused = _cannot_load(error)
    if refused is not None:  # raised here, so no chain leads back to the values refused
        raise refused
    access = knowledge_access(loaded)
    if access is None:
        raise ConfigurationError(
            "The knowledge base's access is not set. FIX: set QDRANT_URL, QDRANT_LOGIN_EMAIL "
            "and QDRANT_LOGIN_PASSWORD in the environment or the .env file given.",
            details={"settings": list(ACCESS)},
        )
    return access


def tickets_folder(settings: Settings) -> Path:
    """The folder the mock ticket system keeps its tickets in: `OLE5_VOICE_TICKETS_DIR`, or the
    app's own under the library's `storage.var_dir`."""
    given = settings.app.tickets_dir
    return given or settings.voice.storage.var_dir / APP_FOLDER / TICKETS_FOLDER


def _email(value: str) -> str:
    """`value`, stripped, when it is an email address: a name, an @ and a host with a dot, and
    no space; the error never repeats it."""
    name, at, host = value.strip().rpartition("@")
    if not (name and at and "." in host) or any(c.isspace() for c in value.strip()):
        raise ValueError("is not an email address: a name, an @ and a host")
    return value.strip()


def _cannot_load(error: ValidationError) -> ConfigurationError:
    """One error naming each setting of the app's that cannot load, never its value."""
    named = []
    for problem in error.errors(include_input=False, include_url=False):
        name = "__".join(str(part).upper() for part in problem["loc"])
        name = name if name in UNPREFIXED else PREFIX + name
        why = problem["msg"].removeprefix("Value error, ")
        named.append((name, "is not set" if problem["type"] == "missing" else why))
    listed = "; ".join(f"{name} {why}" for name, why in named)
    return ConfigurationError(
        f"The Ole5 app's settings cannot load: {listed}. {_FIX}",
        details={"settings": [name for name, _ in named]},
    )
