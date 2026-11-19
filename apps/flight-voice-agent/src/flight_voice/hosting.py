"""The settings a host needs to serve the same flight agent (HOSTING.md): every setting this
machine's environment and `.env` set, the library's (`T2V_`) and the app's (`FLIGHT_VOICE_`),
written as an env file to hand the server's manager, with each secret's value left blank.

    uv run --offline python -m flight_voice.hosting --env-file .env --out alpha.env

Each line is `NAME=value` for a setting given here (a default is left out, so the host follows
the default as this machine does); a secret (a key, the access code, the join keys, the TURN
secret) is written `NAME=` under a comment saying it is set here and must be given on the
server by hand, through the company's way of passing secrets; a folder or file path is marked
as this machine's, to be set to the server's. Nothing secret is ever printed or written.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Final

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings
from t2_agentic_voice import VoiceSettings

from flight_voice.settings import load

__all__ = ["env_lines", "main"]

LIBRARY: Final = "T2V_"
APP: Final = "FLIGHT_VOICE_"
SECRET_NOTE: Final = "# secret, set here: give it on the server by hand, never in a shared file"  # noqa: S105
PATH_NOTE: Final = "# this machine's path: set the server's own"


def _value(value: object) -> str:
    """A setting's value as an env file writes it: JSON for a list, a map or a model."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False, default=_plain)
    return str(value)


def _plain(value: object) -> object:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else str(value)


def _secret(value: object) -> bool:
    if isinstance(value, SecretStr):
        return True
    if isinstance(value, Mapping):
        return any(_secret(v) for v in value.values())
    return isinstance(value, (list, tuple)) and any(_secret(v) for v in value)


def _lines(model: BaseModel, prefix: str) -> Iterator[str]:
    """`model`'s settings that were given, one `NAME=value` (or a blank secret) each."""
    for name in sorted(model.model_fields_set):
        value = getattr(model, name)
        key = f"{prefix}{name.upper()}"
        if isinstance(value, BaseModel) and not isinstance(value, BaseSettings):
            yield from _lines(value, f"{key}__")
        elif _secret(value):
            yield SECRET_NOTE
            yield f"{key}="
        elif isinstance(value, Path):
            yield PATH_NOTE
            yield f"{key}={value}"
        elif value is not None:
            yield f"{key}={_value(value)}"


def env_lines(env_file: Path | None) -> list[str]:
    """The env file's lines for the settings loaded from the environment and `env_file`."""
    app = load(env_file).app  # refused, naming the setting, when the settings cannot load
    given = VoiceSettings.from_env(env_file=env_file)  # the library's, as the environment set them
    head = [
        "# The flight agent's settings as this machine runs it (flight_voice/hosting.py).",
        "# Defaults are left out; blank values are secrets to give on the server by hand.",
        "# Change for the server: T2V_ENV, T2V_SERVER__PUBLIC_URL and the others in HOSTING.md.",
        "",
    ]
    return head + list(_lines(given, LIBRARY)) + [""] + list(_lines(app, APP))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m flight_voice.hosting",
        description="Write the settings a host needs for the same flight agent, secrets blank.",
    )
    parser.add_argument("--env-file", type=Path, default=None, help="the .env to read too")
    parser.add_argument("--out", type=Path, required=True, help="the env file to write")
    args = parser.parse_args(argv)
    args.out.write_text("\n".join(env_lines(args.env_file)) + "\n", encoding="utf-8")
    sys.stdout.write(f"Wrote {args.out}: share it; give the blank secrets on the server.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
