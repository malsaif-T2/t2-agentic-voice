"""How `VoiceSettings` loads (core/config.py): the one error for settings that cannot load,
the setting `env` refuses, the `.env` file's reader, and the refusal of a variable under the
prefix that names no setting. None of it reads the environment, which core/config.py alone does
(ARCH-ENV); `from_env` hands each its part."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic_settings import BaseSettings, DotEnvSettingsSource, SettingsConfigDict

from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.base import NOT_UTF8, UNREADABLE, setting_name
from t2_agentic_voice.core.settings.names import Problem

if TYPE_CHECKING:
    from t2_agentic_voice.core.config import VoiceSettings

Unknown = Literal["error", "warn"]
# Names the settings had before the design's groups, under the prefix, by where each is now, so
# a `.env` written for them says what to rename rather than only that the name is unknown.
_MOVED = {
    "VAR_DIR": ("storage", "var_dir"),
    "LOG_LEVEL": ("logging", "level"),
    "LOG_FORMAT": ("logging", "format"),
}

log = get_logger(__name__)


def named(location: tuple[str, ...], prefix: str) -> str:
    """The variable of the setting at `location`, or "the settings" for a failure of the whole
    (data that is no mapping)."""
    return setting_name(*location, prefix=prefix) if location else "the settings"


def cannot_load(problems: list[Problem], fix: str) -> ConfigurationError:
    """The one error for the settings that cannot load, each named with why, never a value."""
    return ConfigurationError(
        "These settings cannot load: "
        + "; ".join(f"{name} ({why})" for name, why in problems)
        + f". {fix}",
        details={"settings": [{"setting": name, "problem": why} for name, why in problems]},
    )


def refused(settings: VoiceSettings) -> tuple[tuple[str, str], str, str] | None:
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


def dotenv(path: Path, marked: str) -> dict[str, str | None]:
    """The variables of the `.env` file `path` whose names start with `marked`, in any case,
    as written (a byte-order mark dropped, as Notepad may write one). A file whose text is not
    UTF-8 (Windows PowerShell 5.1's `>` writes UTF-16), or that cannot be opened or read, is a
    ConfigurationError with the FIX for which it is, holding none of its bytes: a decode error
    holds the whole file, keys and all, so it is not chained."""
    try:
        reader = _reader(path)
    except OSError as error:
        why, fix = f"cannot be read ({type(error).__name__})", UNREADABLE
    else:
        if reader is not None:
            return {n: v for n, v in reader.env_vars.items() if n.upper().startswith(marked)}
        why, fix = "is not UTF-8 text", NOT_UTF8
    raise ConfigurationError(f"The env file given {why}. {fix}", details={"setting": "env_file"})


def _reader(path: Path) -> DotEnvSettingsSource | None:
    """pydantic-settings' reader of the `.env` file `path`; None when its text is not UTF-8,
    a NUL in it included: UTF-16 written with no byte-order mark (by .NET's encoders) decodes
    as UTF-8, a NUL after each character, and would give names that match no setting, every
    line dropped unseen."""
    if b"\x00" in path.read_bytes():
        return None
    try:
        return DotEnvSettingsSource(
            _DotEnv, env_file=path, env_file_encoding="utf-8-sig", case_sensitive=True
        )
    except UnicodeDecodeError:  # it holds the file's bytes: not chained
        return None


def refuse_strangers(strangers: list[str], prefix: str, unknown: Unknown) -> None:
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
