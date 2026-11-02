"""The settings of a `poe eval` run (`run.py`): loaded from the environment and `--env-file`,
the command line's on top, so a `groq` run's model, timeout and base URL are its own whatever a
`T2V_` variable holds; shown by their dotted names, a secret only as set or not set, as the
scorecard and the history record them; and `--show-settings`, which logs each of them, the
worktree and each path, and sends nothing.
"""

from __future__ import annotations

import argparse

from pydantic import ValidationError
from t2_agentic_voice import ConfigurationError, Settings, T2VoiceError, get_logger

from ole5_voice.evals.items import GOLDEN_DIR, HISTORY_FILE, SPELLING_FILE, SPLIT_FILE
from ole5_voice.evals.run_parts import DATA, Parts, audio_roots
from ole5_voice.evals.worktree import check_out, inspect

# The models a run may name, and the address it sends to unless `--base-url` gives another: the
# library's own (`stt.model`'s choices, `groq.base_url`'s default), which a test ties them to.
MODELS = ("whisper-large-v3", "whisper-large-v3-turbo")
GROQ_BASE_URL = "https://api.groq.com"  # the SDK's own, `groq.base_url`'s default

log = get_logger(__name__)

_URL_FLAGS = {
    "tracing": (
        "--tracing-endpoint",
        "an http:// or https:// URL with a host and no user name or password",
        "the traces endpoint, such as http://127.0.0.1:6006/v1/traces",
    ),
    "groq": (
        "--base-url",
        "an https:// URL with a host, and no user name, password, query or fragment",
        f"Groq's API, {GROQ_BASE_URL}, or leave it out",
    ),
}


def load_settings(args: argparse.Namespace) -> Settings:
    """The settings from the environment and `--env-file`, the command line's on top. The run is
    traced only when `--tracing-endpoint` says so, whatever `tracing.endpoint` holds, and sends
    to `--base-url` or the SDK's own address, whatever `groq.base_url` holds."""
    data = Settings.from_env(args.env_file).model_dump()
    data["tracing"]["endpoint"] = args.tracing_endpoint
    data["groq"]["base_url"] = args.base_url or GROQ_BASE_URL
    data["stt"]["model"] = args.model or data["stt"]["model"]
    data["stt"]["timeout_s"] = args.timeout_s or data["stt"]["timeout_s"]
    data["var_dir"] = args.var_dir or data["var_dir"]
    try:
        return Settings.model_validate(data)
    except ValidationError as error:  # a URL, or a choice the library's settings no longer take
        where = error.errors(include_input=False)[0]["loc"]
    if (group := str(where[0])) in _URL_FLAGS:
        flag, rule, fix = _URL_FLAGS[group]
        raise ConfigurationError(
            f"{flag} is not {rule}. FIX: give {fix}.", details={"setting": flag}
        )
    setting = ".".join(map(str, where))
    raise ConfigurationError(
        f"{setting} is not a value the library's settings take. FIX: give one they do.",
        details={"setting": setting},
    )


def shown(settings: Settings, args: argparse.Namespace) -> dict[str, str]:
    """Every setting a run uses, by its dotted name, resolved; a secret only as set or not set.
    (`var_dir`, a local path that changes no result, is shown by `--show-settings` alone.)"""
    groq, stt, tracing = settings.groq, settings.stt, settings.tracing
    return {
        "env": settings.env,
        "log_level": settings.log_level,
        "log_format": settings.log_format,
        "groq.api_key": "not set" if groq.resolved_api_key() is None else "set",
        "groq.api_key_file": "not set" if groq.api_key_file is None else "set",
        "groq.base_url": groq.base_url,
        "stt.provider": stt.provider,
        "stt.model": stt.model,
        "stt.timeout_s": str(stt.timeout_s),
        "tracing.endpoint": tracing.endpoint or "none",
        "tracing.project": tracing.project or "none",
        "tracing.include_transcripts": str(tracing.include_transcripts).lower(),
        "tracing.redact": f"{len(tracing.redact)} patterns",
        "run.language_hint": args.language_hint,
        "run.max_rpm": str(args.max_rpm),
        "run.max_attempts": str(args.max_attempts),
        "run.variant_timeout_s": str(args.variant_timeout_s),
        "run.cap_usd": "none" if args.cap_usd is None else str(args.cap_usd),
        "run.windows_ms": ",".join(map(str, args.windows_ms)) or "none",
        "run.smoke_only": str(args.smoke_only).lower(),
    }


def show(args: argparse.Namespace, settings: Settings, parts: Parts) -> None:
    """`--show-settings`: each setting, the worktree and each path, as a run would use them."""
    for name, value in (shown(settings, args) | {"var_dir": str(settings.var_dir)}).items():
        log.info("setting", name=name, value=value)
    try:
        checkout = inspect(parts.folder, parts.git)
    except T2VoiceError as error:
        log.info("worktree", state=error.message)
        return
    problem = checkout.refusal()
    state = "ready" if problem is None else problem.message
    log.info("worktree", top=str(checkout.top), commit=checkout.commit, state=state)
    data = checkout.top / DATA
    paths = {"items": data / GOLDEN_DIR, "split": data / SPLIT_FILE}
    paths |= {"spelling": data / SPELLING_FILE, "history": data / HISTORY_FILE}
    paths |= {f"audio.{root}": folder for root, folder in audio_roots(args.audio).items()}
    for name, path in paths.items():
        log.info("path", name=name, path=str(path), state="exists" if path.exists() else "missing")
    if args.out is not None:
        try:
            state, out = "new", check_out(args.out, checkout, parts.git)
        except T2VoiceError as error:
            state, out = error.message, args.out
        log.info("path", name="out", path=str(out), state=state)
