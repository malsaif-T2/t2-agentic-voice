"""The library's settings, `VoiceSettings` (the design's 7): the only module that reads the
environment (ARCH-ENV).

Built in code, `VoiceSettings(env=..., ...)` takes its defaults and the arguments given, and
nothing else: no environment variable and no `.env` (the design's 7.2). `VoiceSettings.from_env`
reads the environment variables under a prefix (`T2V_` unless `prefix=` gives another), and a
`.env` file only when `env_file=` names one; the environment wins over the file, and the code
arguments given to `from_env` win over both, a group given as a dict key by key and a group
object whole. There is no settings singleton: a module receives a `VoiceSettings`, and never
touches `os.environ`. A group's settings nest with `__`: `T2V_GROQ__API_KEY` is
`settings.groq.api_key` (the groups are in core/settings/, one module each). A list or a map is
given as JSON. A blank value counts as unset, and `.env.example` leaves every key blank with its
default in a comment, so a `.env` copied from it with only the key filled in keeps every other
default, one changed later included.

`env` has no default: dev, test, staging or prod. Outside dev the dev page and logged call
content are refused, and staging and prod refuse DEBUG: staging holds every check prod holds
(the design's 7.4). A variable that carries the prefix but names no setting is an error naming
the variable, never its value, so a misspelt name never falls back to a default: the prefix
must belong to the library's settings alone (`unknown="warn"` logs it instead).

No provider's own variable (`GROQ_API_KEY`, `OTEL_*`) is ever read here: `from_env` notes only
whether GROQ_API_KEY is set, its name and never its value, so the Groq adapter's error can say
which name to set instead (the design's 7.3); and `foreign_set` tells `voice` which of the
variables it refuses (`PIPECAT_SETUP_FILES`) are set, by name. The adapters pass every value
that keeps their SDKs from reading one. The few an SDK reads whatever is passed are kept out or
recorded as debt: `GROQ_CUSTOM_HEADERS` by the Groq adapter's request hook, `GROQ_LOG` by how
the adapter imports the SDK (TD-003), and three `OTEL_*` ones (TD-005,
`core/tracing_export.py`); the proxy and CA variables both clients trust are debt too (TD-004,
TD-015). The guide's "Variables to leave unset" lists them all.

Every failure is a ConfigurationError naming each setting that cannot load and never the value
it rejected (the design's 7.4), whether the settings are built in code (their constructor,
`model_validate` and `model_validate_json`) or loaded by `from_env`; a group built on its own
raises pydantic's ValidationError instead (core/settings/base.py).

When you add a field, give it a `description` and run `uv run poe settings-ref`, which writes
docs/generated/settings.md and .env.example from the model (their freshness tests fail until
you do). A secret is a `SecretStr` field, so it never shows in a repr or a log; each one also
takes a `_file` setting whose file holds the value.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    PrivateAttr,
    ValidationError,
    ValidationInfo,
    model_validator,
)
from pydantic_settings import BaseSettings, DotEnvSettingsSource, SettingsConfigDict

from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.base import PREFIX, prefix_of, setting_name
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.join import JoinSettings
from t2_agentic_voice.core.settings.limits import LimitSettings
from t2_agentic_voice.core.settings.logs import LoggingSettings
from t2_agentic_voice.core.settings.names import Problem, gathered, leaf
from t2_agentic_voice.core.settings.privacy import PrivacySettings
from t2_agentic_voice.core.settings.server import ServerSettings
from t2_agentic_voice.core.settings.session import SessionSettings
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.core.settings.tracing import TracingSettings
from t2_agentic_voice.core.settings.tts import TtsSettings
from t2_agentic_voice.core.settings.turns import TurnSettings

Environment = Literal["dev", "test", "staging", "prod"]
Unknown = Literal["error", "warn"]
# What a prefix is: letters, digits and `_`, from a letter to a final `_` (the design's 7.3).
_PREFIX_RULE = re.compile(r"[A-Za-z][A-Za-z0-9_]*_")
# A provider's variable the library never reads: `from_env` notes whether it is set, by its name
# alone, so the error for the setting to set instead (`groq.api_key`) can say so.
_UNREAD = ("GROQ_API_KEY",)
# Names the settings had before the design's groups, under the prefix, by where each is now, so
# a `.env` written for them says what to rename rather than only that the name is unknown.
_MOVED = {
    "VAR_DIR": ("storage", "var_dir"),
    "LOG_LEVEL": ("logging", "level"),
    "LOG_FORMAT": ("logging", "format"),
}
# What the validation context holds when `from_env` loads the settings, so a failure's FIX line
# says where its values came from.
_LOADED = "from_env"
_FIX_LOADED = "FIX: correct each one in the environment or the .env file."
_FIX_CODE = "FIX: correct each one in the code that builds the settings."

log = get_logger(__name__)


class VoiceSettings(BaseModel):
    """All the library's tunable settings: how it runs in this deployment (the design's 7.1),
    `env` and a group for each part. Built in code or loaded by `from_env`, any setting that
    cannot load is one ConfigurationError naming each one under the prefix (the library's
    `T2V_` in code), with a FIX line and never the value it rejected; nothing chains it to the
    ValidationError, whose `errors()` would still return that value."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    env: Environment = Field(
        description=(
            "Where the library runs: dev, test, staging or prod; required, with no default. "
            "Outside dev the dev page and logged call content are refused, and staging and "
            "prod refuse DEBUG."
        ),
    )
    groq: GroqSettings = Field(default_factory=GroqSettings)
    stt: SttSettings = Field(default_factory=SttSettings)
    tts: TtsSettings = Field(default_factory=TtsSettings)
    turns: TurnSettings = Field(default_factory=TurnSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    join: JoinSettings = Field(default_factory=JoinSettings)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    tracing: TracingSettings = Field(default_factory=TracingSettings)
    limits: LimitSettings = Field(default_factory=LimitSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)

    # What `from_env` learned as it loaded: the prefix, and the provider variables it saw set.
    # A copy (`model_copy`) keeps them; settings rebuilt from a dump take the defaults.
    _prefix: str = PrivateAttr(default=PREFIX)
    _seen: frozenset[str] = PrivateAttr(default=frozenset())

    @model_validator(mode="wrap")
    @classmethod
    def _loaded(
        cls, data: object, handler: ModelWrapValidatorHandler[VoiceSettings], info: ValidationInfo
    ) -> VoiceSettings:
        """The settings `data` gives, then the checks `env` makes; or one ConfigurationError
        naming every setting that cannot load, raised after the handler, so no exception chain
        leads back to the ValidationError."""
        prefix = prefix_of(info)
        try:
            settings = handler(data)
        except ValidationError as error:
            problems = [
                (_named(leaf(cls, problem["loc"]), prefix), problem["msg"])
                for problem in error.errors(include_input=False, include_url=False)
            ]
        else:
            settings.check_environment(prefix)
            return settings
        loaded = isinstance(info.context, dict) and info.context.get(_LOADED) is True
        raise _cannot_load(problems, _FIX_LOADED if loaded else _FIX_CODE)

    @property
    def prefix(self) -> str:
        """The prefix of the environment names these settings were loaded under."""
        return self._prefix

    def env_name(self, *location: str | int) -> str:
        """The variable the setting at `location` is read from, under these settings' prefix:
        `T2V_GROQ__API_KEY` for ("groq", "api_key")."""
        return setting_name(*location, prefix=self._prefix)

    def saw(self, name: str) -> bool:
        """Whether `from_env` found the variable `name` set, one the library never reads
        (GROQ_API_KEY): its name only, never its value."""
        return name in self._seen

    def check_environment(self, prefix: str | None = None) -> None:
        """ConfigurationError naming a setting `env` refuses, under `prefix` (these settings'
        own by default): outside dev, the dev page and logged call content; in staging and
        prod, DEBUG (the design's 7.4). Every load runs it; `status` and `VoiceRuntime`'s
        construction run it again, for settings copied with a change, which skips validation."""
        prefix = self._prefix if prefix is None else prefix
        problem = _refused(self)
        if problem is None:
            return
        location, why, fix = problem
        name = setting_name(*location, prefix=prefix)
        raise ConfigurationError(
            f"{name} {why}, which env={self.env} refuses. FIX: {fix}",
            details={"setting": name, "env": self.env},
        )

    @classmethod
    def from_env(
        cls,
        prefix: str = PREFIX,
        env_file: Path | None = None,
        unknown: Unknown = "error",
        **values: object,
    ) -> VoiceSettings:
        """The settings from the environment variables under `prefix`, and from `env_file`, a
        `.env`, only when one is given (the environment wins over it), with `values`, code
        arguments, over both. A group given as a dict merges into what the environment and the
        file gave for that group, key by key (`server={"dev_page": True}` keeps
        `T2V_SERVER__PUBLIC_URL`), while a group given as its object (`ServerSettings(...)`)
        replaces the group whole, since an object holds every key; a map setting given inside
        either replaces the whole map. A variable under the prefix that names no setting is a
        ConfigurationError naming it, never its value, or with `unknown="warn"` a warning, the
        variable left out. An `env_file` given that is no file, or that cannot be read as UTF-8
        text, is a ConfigurationError, so a mistyped path never runs on the defaults (GP-06).
        Any setting that cannot load is a ConfigurationError naming each one
        (`T2V_GROQ__BASE_URL`) and why, with a FIX line, never the value it rejected (the
        design's 7.4)."""
        if not _PREFIX_RULE.fullmatch(prefix):
            raise ConfigurationError(
                "The prefix given cannot start an environment name. FIX: give letters, digits "
                "and _, from a letter to a final _, such as HELPDESK_VOICE_.",
                details={"setting": "prefix"},
            )
        if env_file is not None and not env_file.expanduser().is_file():
            raise ConfigurationError(
                "The env file given cannot be read. FIX: pass the path of an existing .env file.",
                details={"setting": "env_file"},
            )
        marked = prefix.upper()
        sources = [] if env_file is None else [_dotenv(env_file.expanduser(), marked)]
        sources.append({n: os.environ[n] for n in os.environ if n.upper().startswith(marked)})
        data, strangers, problems = gathered(cls, sources, prefix)
        _refuse_strangers(strangers, prefix, unknown)
        if problems:
            raise _cannot_load(problems, _FIX_LOADED)
        for name, value in values.items():
            given = data.get(name)
            if isinstance(value, Mapping) and isinstance(given, dict):
                value = given | dict(value)  # a group's dict: key by key
            data[name] = value
        settings = cls.model_validate(data, context={"prefix": prefix, _LOADED: True})
        settings._prefix = prefix
        settings._seen = foreign_set(_UNREAD)
        return settings


def foreign_set(names: Iterable[str]) -> frozenset[str]:
    """Which of `names`, variables the library never reads as settings (a provider's own, or one
    a package reads whatever is passed, such as `PIPECAT_SETUP_FILES`), are set to a value in
    this process's environment now, matched in any case; each as given, never its value. It
    answers however the settings were built, so `voice`, which reads no variable (ARCH-ENV),
    asks it which ones to refuse at start. An empty value counts as unset."""
    wanted = {name.upper(): name for name in names}
    found = [name.upper() for name, value in os.environ.items() if value]
    return frozenset(wanted[name] for name in found if name in wanted)


def _named(location: tuple[str, ...], prefix: str) -> str:
    """The variable of the setting at `location`, or "the settings" for a failure of the whole
    (data that is no mapping)."""
    return setting_name(*location, prefix=prefix) if location else "the settings"


def _cannot_load(problems: list[Problem], fix: str) -> ConfigurationError:
    """The one error for the settings that cannot load, each named with why, never a value."""
    return ConfigurationError(
        "These settings cannot load: "
        + "; ".join(f"{name} ({why})" for name, why in problems)
        + f". {fix}",
        details={"settings": [{"setting": name, "problem": why} for name, why in problems]},
    )


def _refused(settings: VoiceSettings) -> tuple[tuple[str, str], str, str] | None:
    """The first setting `settings.env` refuses: its location, what it holds, and the fix."""
    if settings.env != "dev" and settings.server.dev_page:
        fix = "turn it off; the dev page is for one machine, under env=dev."
        return ("server", "dev_page"), "is on", fix
    if settings.env != "dev" and settings.logging.content:
        fix = "turn it off; log lines hold what was said only under env=dev."
        return ("logging", "content"), "is on", fix
    if settings.env in ("staging", "prod") and settings.logging.level == "DEBUG":
        fix = "give INFO or above; DEBUG lines may carry data that should not be kept."
        return ("logging", "level"), "is DEBUG", fix
    return None


class _DotEnv(BaseSettings):
    """No settings: only its `.env` reader is used, so a file is read as pydantic-settings
    reads one (quotes, `export`, comments)."""

    model_config = SettingsConfigDict(extra="ignore")


def _dotenv(path: Path, marked: str) -> dict[str, str | None]:
    """The variables of the `.env` file `path` whose names start with `marked`, in any case,
    as written (a byte-order mark dropped, as Notepad may write one). A file that cannot be read
    as UTF-8 text (Windows PowerShell 5.1's `>` writes UTF-16) is a ConfigurationError that holds
    none of its bytes: a decode error holds the whole file, keys and all, so it is not
    chained."""
    try:
        reader = DotEnvSettingsSource(
            _DotEnv, env_file=path, env_file_encoding="utf-8-sig", case_sensitive=True
        )
    except (OSError, UnicodeDecodeError) as error:
        failure = type(error).__name__
    else:
        return {n: v for n, v in reader.env_vars.items() if n.upper().startswith(marked)}
    raise ConfigurationError(
        f"The env file given cannot be read ({failure}). FIX: save it as UTF-8 text.",
        details={"setting": "env_file"},
    )


def _refuse_strangers(strangers: list[str], prefix: str, unknown: Unknown) -> None:
    """Each variable under the prefix that names no setting: a ConfigurationError naming them
    all, never a value, or with `unknown="warn"` a warning each (the design's 7.4)."""
    if not strangers:
        return
    fix = (
        f"FIX: correct each name, or unset it: every variable under {prefix} is the library's, "
        "since the prefix belongs to its settings alone (a team's own settings take another; "
        "from_env(prefix=...) picks the library's)."
    )
    if unknown == "warn":
        for name in strangers:
            log.warning("setting_unknown", variable=name, fix=fix)
        return
    moved = {name: _MOVED.get(name[len(prefix) :].upper()) for name in strangers}
    hints = [f"; {n} is {setting_name(*to, prefix=prefix)} now" for n, to in moved.items() if to]
    raise ConfigurationError(
        f"{', '.join(sorted(strangers))} names no setting{''.join(sorted(hints))}. {fix}",
        details={
            "settings": [{"setting": n, "problem": "names no setting"} for n in sorted(strangers)]
        },
    )
