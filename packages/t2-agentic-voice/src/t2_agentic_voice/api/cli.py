"""The `t2v` command (the first part of the design's 10.6): `t2v serve APP`, `t2v dev APP`,
`t2v doctor` and `t2v settings show --redacted`.

`APP` names a team's runtime factory as `module:function` (`minimal_example.app:make_runtime`),
a function that takes no argument and returns a `VoiceRuntime`; its module is imported from the
working folder or the installed packages. `serve` and `dev` configure the library's logging, the
app's package's, `__main__`'s and uvicorn's from the runtime's settings, then serve it until the
process is stopped. `doctor` and `settings show` load the settings from the environment under a
prefix (`T2V_` unless `--prefix` gives another), and from a `.env` file only when `--env-file`
names one.

This module imports nothing heavy at its top, so `t2v --help` and each command's `--help` only
print help: no Pipecat, no FastAPI and no provider SDK is imported (GP-17). It is the one module
of `api` that writes to standard output (`[rules] output_allowed_files`): its help, its reports
and its refusals, which name a setting and never its value.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final

from t2_agentic_voice.core.errors import ConfigurationError, T2VoiceError

if TYPE_CHECKING:
    from t2_agentic_voice.api.runtime import VoiceRuntime
    from t2_agentic_voice.core.config import VoiceSettings

PROGRAM: Final = "t2v"
# What a redacted secret, or the file that holds one, is shown as.
REDACTED: Final = "**********"
_APP_HELP = "the runtime factory, as module:function (a function that returns a VoiceRuntime)"


def main(argv: Sequence[str] | None = None) -> int:
    """Run `t2v` with `argv` (the process's arguments unless given); its exit status."""
    args = _parser().parse_args(argv)
    command: Callable[[argparse.Namespace], int] = args.command
    try:
        return command(args)
    except T2VoiceError as error:
        print(f"{PROGRAM}: {error.message}", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM, description="Serve and check a T2 Agentic Voice runtime."
    )
    commands = parser.add_subparsers(title="commands", required=True)
    serve = commands.add_parser("serve", help="serve a runtime on its own (the sidecar)")
    serve.add_argument("app", metavar="APP", help=_APP_HELP)
    serve.add_argument("--host", default="127.0.0.1", help="the address to bind (127.0.0.1)")
    _serving(serve)
    serve.set_defaults(command=_serve)
    dev = commands.add_parser(
        "dev", help="serve a runtime with its dev page on 127.0.0.1, env=dev only"
    )
    dev.add_argument("app", metavar="APP", help=_APP_HELP)
    _serving(dev)
    dev.set_defaults(command=_dev)
    doctor = commands.add_parser("doctor", help="check what a first call needs")
    doctor.add_argument(
        "--synthesize",
        action="store_true",
        help="also send one short synthesis request per language (counted in the budget)",
    )
    _loading(doctor)
    doctor.set_defaults(command=_doctor)
    settings = commands.add_parser("settings", help="the settings the library runs with")
    shown = settings.add_subparsers(title="commands", required=True)
    show = shown.add_parser("show", help="print the settings as JSON, every secret redacted")
    show.add_argument("--redacted", action="store_true", help="redact every secret (always on)")
    _loading(show)
    show.set_defaults(command=_show)
    return parser


def _serving(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", type=int, default=7860, help="the port to bind (7860)")
    parser.add_argument("--prefix", default="/voice", help="the routes' prefix (/voice)")


def _loading(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--prefix", default="T2V_", help="the settings' prefix (T2V_)")
    parser.add_argument(
        "--env-file", type=Path, default=None, help="a .env file to read (none unless given)"
    )


def _serve(args: argparse.Namespace) -> int:
    from t2_agentic_voice.api.server import serve

    runtime = _runtime(args.app)
    serve(lambda: runtime, host=args.host, port=args.port, prefix=args.prefix)
    return 0


def _dev(args: argparse.Namespace) -> int:
    from t2_agentic_voice.api.server import serve_dev

    runtime = _runtime(args.app)
    serve_dev(lambda: runtime, port=args.port, prefix=args.prefix)
    return 0


def _runtime(app: str) -> VoiceRuntime:
    """The runtime `app`'s factory makes, with logging configured from its settings for the
    library, the app's package, `__main__` and uvicorn."""
    from t2_agentic_voice.api.runtime import VoiceRuntime
    from t2_agentic_voice.core.logging import configure_logging

    module, _, name = app.partition(":")
    factory = _factory(module, name)
    runtime = factory()
    if not isinstance(runtime, VoiceRuntime):
        raise ConfigurationError(
            f"{app} returned no VoiceRuntime. FIX: name a function that returns one."
        )
    logs = runtime._settings.logging
    loggers = (module.partition(".")[0], "__main__", "uvicorn")
    configure_logging(logs.level, logs.format, loggers=loggers, content=logs.content)
    return runtime


def _factory(module: str, name: str) -> Callable[[], object]:
    """The function `name` of `module`, imported from the working folder or the installed
    packages; a ConfigurationError naming APP when it cannot be found."""
    fix = "FIX: give APP as module:function, such as minimal_example.app:make_runtime."
    if not module or not name.isidentifier():
        raise ConfigurationError(f"APP is not module:function. {fix}")
    folder = str(Path.cwd())
    if folder not in sys.path:
        sys.path.insert(0, folder)
    try:
        found = getattr(importlib.import_module(module), name)
    except (ImportError, AttributeError):
        raise ConfigurationError(f"APP names no function that can be imported. {fix}") from None
    if not callable(found):
        raise ConfigurationError(f"APP names no function. {fix}")
    factory: Callable[[], object] = found
    return factory


def _doctor(args: argparse.Namespace) -> int:
    from t2_agentic_voice.api.doctor import checks

    found = asyncio.run(checks(_settings(args), synthesize=args.synthesize))
    width = max(len(check.name) for check in found)
    for check in found:
        print(f"{'ok  ' if check.ok else 'FAIL'}  {check.name:<{width}}  {check.detail}")
    return 0 if all(check.ok for check in found) else 1


def _show(args: argparse.Namespace) -> int:
    print(json.dumps(redacted(_settings(args)), indent=2, ensure_ascii=False))
    return 0


def _settings(args: argparse.Namespace) -> VoiceSettings:
    from t2_agentic_voice.core.config import VoiceSettings

    return VoiceSettings.from_env(prefix=args.prefix, env_file=args.env_file)


def redacted(settings: VoiceSettings) -> dict[str, object]:
    """The settings as JSON values, each secret and each file that holds one shown as REDACTED
    when set: pydantic writes a secret so, and a `_file` setting is redacted here."""
    shown: dict[str, object] = settings.model_dump(mode="json")
    for group in shown.values():
        if isinstance(group, dict):
            for name, value in group.items():
                if name.endswith("_file") and value is not None:
                    group[name] = REDACTED
    return shown


if __name__ == "__main__":
    raise SystemExit(main())
