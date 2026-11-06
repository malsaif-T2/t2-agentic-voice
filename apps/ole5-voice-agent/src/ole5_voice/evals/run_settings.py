"""The settings of a `poe eval` run (`run.py`): loaded from the environment and `--env-file`,
or the working folder's `.env` when it names none, the command line's on top, so a `groq` run's
model, timeout and base URL are its own whatever a `T2V_` variable holds; shown by their dotted
names, a secret only as set or not set, as the scorecard and the history record them; and
`--show-settings`, which logs each of them, the worktree and each path, and sends nothing.

**Run W's arms** (`answer_options`): with `--prompt-vocabulary FILE` (`evals/terms.toml`), each
request carries a Whisper prompt for the language it is sent in, built from the file's terms, in
its order, then the presets' command words for that language (their stop, wait and repeat lists,
in the presets' order and the form the rule compares in), each once, joined with a comma, and
trimmed to `PROMPT_BYTES` by that order, so the first term that does not fit and every one after
it are left out; the log says how many were kept (arm W1; without it, none: W0). With
`--language-hint ar`, every variant is sent as Arabic, an English item's too, as an Arabic call
sends it (arm X). Each is recorded as `run.prompt` and `run.language_hint`.

The library reads no `.env` it is not given (the design's 7.2): reading the working folder's is
this app's choice, as the golden set's first runs read it; and a run is a developer's, so its
settings run as `env=dev` whatever `T2V_ENV` says.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel
from t2_agentic_voice import ConfigurationError, Phrases, T2VoiceError, VoiceSettings, get_logger

from ole5_voice.evals.items import (
    GOLDEN_DIR,
    HISTORY_FILE,
    SPELLING_FILE,
    SPLIT_FILE,
    GoldenSetError,
    load_terms,
)
from ole5_voice.evals.run_parts import DATA, Parts, audio_roots
from ole5_voice.evals.worktree import check_out, inspect, refused

# The models a run may name, and the address it sends to unless `--base-url` gives another: the
# library's own (`stt.model`'s choices, `groq.base_url`'s default), which a test ties them to.
MODELS = ("whisper-large-v3", "whisper-large-v3-turbo")
GROQ_BASE_URL = "https://api.groq.com"  # the SDK's own, `groq.base_url`'s default
# The `.env` a run's settings load from when `--env-file` names none: the working folder's.
# tests/conftest.py sets it to None, so no test reads the developer's.
DOTENV: Path | None = Path(".env")
# A setting shown only as set or not set: a secret, a key map, or a secret's file.
_SECRET = re.compile(r"(^|_)(key|keys|secret|token|password|file)$")

# Whisper's longest prompt is 224 tokens (Groq's transcription API). No tokenizer is installed,
# so a prompt is held to as many bytes of UTF-8: a token of a byte-level tokenizer is a byte at
# least, so a prompt within the bytes is within the tokens.
PROMPT_BYTES: Final = 224
_PROMPT_LANGUAGES: Final[tuple[Literal["ar", "en"], ...]] = ("ar", "en")  # the codes sent
_COMMAND_KINDS: Final = ("stop", "wait", "repeat")  # the presets' lists a prompt adds

log = get_logger(__name__)

# The command line's URL flags, by the setting each one gives.
_URL_FLAGS = {
    ("tracing", "endpoint"): (
        "--tracing-endpoint",
        "an http:// or https:// URL with a host and no user name or password",
        "the traces endpoint, such as http://127.0.0.1:6006/v1/traces",
    ),
    ("groq", "base_url"): (
        "--base-url",
        "an https:// URL with a host, and no user name, password, query or fragment",
        f"Groq's API, {GROQ_BASE_URL}, or leave it out",
    ),
}


def load_settings(args: argparse.Namespace) -> VoiceSettings:
    """The settings from the environment and `--env-file` (or `DOTENV`), the command line's on
    top. The run is traced only when `--tracing-endpoint` says so, whatever `tracing.endpoint`
    holds, and sends to `--base-url` or the SDK's own address, whatever `groq.base_url` holds."""
    env_file = args.env_file
    if env_file is None and DOTENV is not None and DOTENV.is_file():
        env_file = DOTENV
    loaded = VoiceSettings.from_env(env_file=env_file, env="dev")
    data = loaded.model_dump()
    data["tracing"]["endpoint"] = args.tracing_endpoint
    data["groq"]["base_url"] = args.base_url or GROQ_BASE_URL
    data["stt"]["model"] = args.model or data["stt"]["model"]
    data["stt"]["timeout_s"] = args.timeout_s or data["stt"]["timeout_s"]
    data["storage"]["var_dir"] = args.var_dir or data["storage"]["var_dir"]
    try:
        checked = VoiceSettings.model_validate(data, context={"prefix": loaded.prefix})
    except ConfigurationError as error:  # a URL, or a choice the library's settings no longer take
        failed = _named(error)
    else:
        # A copy keeps what `from_env` noted (its prefix, and whether GROQ_API_KEY is set, for
        # the adapter's error), which settings validated from a dump would not.
        return loaded.model_copy(update=dict(checked))
    flags = {loaded.env_name(*location): words for location, words in _URL_FLAGS.items()}
    for setting in failed:
        if setting in flags:
            flag, rule, fix = flags[setting]
            raise ConfigurationError(
                f"{flag} is not {rule}. FIX: give {fix}.", details={"setting": flag}
            )
    setting = ", ".join(failed)
    raise ConfigurationError(
        f"{setting} is not a value the library's settings take. FIX: give one they do.",
        details={"setting": setting},
    )


def _named(error: ConfigurationError) -> list[str]:
    """The settings a settings error names, in order, from its details."""
    entries = error.details.get("settings")
    named = entries if isinstance(entries, list) else []
    return [str(entry["setting"]) for entry in named if isinstance(entry, dict)]


@dataclass(frozen=True)
class Prompt:
    """One language's Whisper prompt, and how many of its candidate terms it kept."""

    text: str
    kept: int
    of: int


def whisper_prompts(terms: Sequence[str], phrases: Phrases | None = None) -> dict[str, Prompt]:
    """Each language's prompt (the module's docstring): `terms`, then the command words of
    `phrases` (the presets' by default), kept in that order within `PROMPT_BYTES`."""
    lists = Phrases.defaults() if phrases is None else phrases
    found: dict[str, Prompt] = {}
    for code in _PROMPT_LANGUAGES:
        words = lists.words(code)
        commands = [word for kind in _COMMAND_KINDS for word in getattr(words, kind)]
        candidates = list(dict.fromkeys([*terms, *commands]))
        kept: list[str] = []
        for term in candidates:
            if len(", ".join([*kept, term]).encode("utf-8")) > PROMPT_BYTES:
                break
            kept.append(term)
        found[code] = Prompt(", ".join(kept), len(kept), len(candidates))
    return found


@dataclass(frozen=True)
class AnswerOptions:
    """Run W's arms as the `groq` answerer takes them: the language every request goes in
    (None: the item's), each language's prompt, and how the run records them (`run.prompt`)."""

    language: str | None = None
    prompts: Mapping[str, str] = field(default_factory=dict)
    shown: str = "none"


def answer_options(args: argparse.Namespace) -> AnswerOptions:
    """The arms `--language-hint ar` and `--prompt-vocabulary` choose; the run's refusal, before
    anything is sent, for a vocabulary that does not load."""
    language = "ar" if args.language_hint == "ar" else None
    path: Path | None = args.prompt_vocabulary
    if path is None:
        return AnswerOptions(language=language)
    try:
        terms = load_terms(path)
    except GoldenSetError:
        raise refused(
            "--prompt-vocabulary does not load as a list of terms, each once",
            "give a TOML file of terms = [...], such as evals/terms.toml",
        ) from None
    prompts = whisper_prompts(terms)
    for code, prompt in prompts.items():
        log.info("whisper_prompt", language=code, terms_kept=prompt.kept, of=prompt.of)
    texts = {code: prompt.text for code, prompt in prompts.items() if prompt.text}
    digest = hashlib.sha256(json.dumps(texts, sort_keys=True).encode("utf-8")).hexdigest()
    counts = ", ".join(f"{code} {p.kept} of {p.of} terms" for code, p in prompts.items())
    return AnswerOptions(language, texts, f"{path.name}, sha256 {digest[:16]}, {counts}")


def shown(
    settings: VoiceSettings, args: argparse.Namespace, *, prompt: str | None = None
) -> dict[str, str]:
    """Every setting a run has, by its dotted name, resolved; a secret only as set or not set.
    Those a run uses come first, then every other (`_others`), so a setting the library gains
    is recorded too; `prompt`, a `poe eval` run's `AnswerOptions.shown`, as `run.prompt`.
    (`storage.var_dir`, a local path that changes no result, is shown by `--show-settings`
    alone.)"""
    groq, stt, tracing = settings.groq, settings.stt, settings.tracing
    used = {
        "env": settings.env,
        "logging.level": settings.logging.level,
        "logging.format": settings.logging.format,
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
    }
    others = {name: value for name, value in _others(settings) if name not in used}
    prompted = {} if prompt is None else {"run.prompt": prompt}
    return (
        used
        | others
        | prompted
        | {
            "run.language_hint": args.language_hint,
            "run.max_rpm": str(args.max_rpm),
            "run.max_attempts": str(args.max_attempts),
            "run.variant_timeout_s": str(args.variant_timeout_s),
            "run.cap_usd": "none" if args.cap_usd is None else str(args.cap_usd),
            "run.windows_ms": ",".join(map(str, args.windows_ms)) or "none",
            "run.smoke_only": str(args.smoke_only).lower(),
        }
    )


def _others(settings: VoiceSettings) -> list[tuple[str, str]]:
    """Every setting of every group, `storage.var_dir` aside, by its dotted name, as text: a
    secret, a key map and a secret's file only as set or not set, a list as its length, a map
    as JSON, nothing as none."""
    found: list[tuple[str, str]] = []
    for group in type(settings).model_fields:
        values = getattr(settings, group)
        if not isinstance(values, BaseModel):
            continue  # `env`, which `shown` names itself
        for name in type(values).model_fields:
            if f"{group}.{name}" != "storage.var_dir":
                found.append((f"{group}.{name}", _text(name, getattr(values, name))))
    return found


def _text(name: str, value: object) -> str:
    """A setting's value as a run records it."""
    if _SECRET.search(name):
        return "set" if value else "not set"
    if value is None or isinstance(value, bool):
        return "none" if value is None else str(value).lower()
    if isinstance(value, tuple):
        return f"{len(value)} entries"
    if isinstance(value, Mapping):  # a read-only map: dumped as the plain object it holds
        plain = dict(value)
        return json.dumps(plain, default=lambda each: each.model_dump(mode="json"), sort_keys=True)
    return str(value)


def show(
    args: argparse.Namespace, settings: VoiceSettings, parts: Parts, *, prompt: str = "none"
) -> None:
    """`--show-settings`: each setting, the worktree and each path, as a run would use them."""
    var_dir = {"storage.var_dir": str(settings.storage.var_dir)}
    for name, value in (shown(settings, args, prompt=prompt) | var_dir).items():
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
