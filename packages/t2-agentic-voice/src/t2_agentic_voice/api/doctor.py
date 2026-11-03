"""`t2v doctor` (the first part of the design's 10.6): what a first call needs that the library
can check without a call, each a `Check` that passes or says what to fix.

- **The key**, from the settings (inline or in its file), with no request.
- **Each language's model and voice**, through the text-to-speech adapter's `check_language`:
  the key and the model list (a GET), with no synthesis, so a model whose terms are not accepted
  shows only with `--synthesize`.
- **The ONNX files** Silero VAD and Smart Turn run on, each file's SHA-256 against the one the
  installed Pipecat wheel's record holds, read from its metadata: Pipecat is not imported.
- **The clock**: this machine's UTC time and the join tokens' skew allowance. Its skew against
  another clock is not measured: no port reports a provider's time.
- **`--synthesize`**: one short request per language, which checks its voice and the model's
  terms (Groq documents no other way to learn whether they are accepted), counted in the
  key's budget. A model whose terms are not accepted fails with the adapter's FIX line, which
  names the console's terms (adapters/groq_tts.py).

No check prints a secret or a value it refused: each failure is the error's own message, which
names the setting, never its value, and a FIX line; a provider's FIX line is the one its
adapter put in the error's details (`fix`), since the message is fixed per kind.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from typing import Final

from t2_agentic_voice.api.runtime import Providers
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.tts import LanguageTag

# The distribution whose ONNX models a call runs on.
PIPECAT: Final = "pipecat-ai"
# What `--synthesize` says in each language: short, so it costs few tokens.
SAMPLES: Final[dict[str, str]] = {
    # Arabic for "voice check": FEH HAH SAD, space, ALEF LAM SAD WAW TEH, a full stop.
    "ar": "فحص الصوت.",
    "en": "Voice check.",
}
_REINSTALL = "FIX: reinstall it (uv sync --reinstall-package pipecat-ai)."


@dataclass(frozen=True)
class Check:
    """One check: what it checked, whether it passed, and what it found or how to fix it."""

    name: str
    ok: bool
    detail: str


async def checks(
    settings: VoiceSettings, *, synthesize: bool, providers: Providers | None = None
) -> list[Check]:
    """Every check, in order; `providers` are the settings' own unless given (a test's fakes),
    and are closed after when built here."""
    found = [_key(settings)]
    built = providers is None
    if providers is None:
        try:
            providers = Providers.from_settings(settings)
        except ConfigurationError as error:
            return [*found, Check("providers", False, error.message), *onnx(), _clock(settings)]
    try:
        for tag in settings.tts.languages:
            found.append(await _language(providers, tag))
        found += [*onnx(), _clock(settings)]
        if synthesize:
            for tag in settings.tts.languages:
                found.append(await _synthesis(providers, tag))
    finally:
        if built:
            await providers.stt.aclose()
            await providers.tts.aclose()
    return found


def _key(settings: VoiceSettings) -> Check:
    try:
        key = settings.groq.resolved_api_key(settings.prefix)
    except ConfigurationError as error:
        return Check("key", False, error.message)
    if key is None:
        setting = settings.env_name("groq", "api_key")
        return Check("key", False, f"No Groq API key is set. FIX: set {setting}.")
    return Check("key", True, "set")


async def _language(providers: Providers, tag: LanguageTag) -> Check:
    name = f"model and voice {tag}"
    try:
        await providers.tts.check_language(tag)
    except (ConfigurationError, ProviderError) as error:
        return Check(name, False, _failure(error))
    return Check(name, True, "listed")


async def _synthesis(providers: Providers, tag: LanguageTag) -> Check:
    name = f"synthesis {tag}"
    seconds, cut_short = 0.0, False
    try:
        async for chunk in providers.tts.synthesize(SAMPLES[_primary(tag)], language=tag):
            seconds += chunk.seconds
            cut_short = cut_short or chunk.cut_short
    except (ConfigurationError, ProviderError) as error:
        return Check(name, False, _failure(error))
    if seconds <= 0:
        return Check(name, False, "the provider answered with no audio")
    shortened = ", cut short" if cut_short else ""
    return Check(name, True, f"{seconds:.2f} s of audio{shortened}, 1 request")


def onnx() -> list[Check]:
    """Each ONNX file of the installed Pipecat, its SHA-256 against its wheel's record."""
    try:
        files = metadata.distribution(PIPECAT).files or []
    except metadata.PackageNotFoundError:
        return [Check("onnx", False, f"{PIPECAT} is not installed. {_REINSTALL}")]
    models = [f for f in files if f.suffix == ".onnx"]
    if not models:
        return [Check("onnx", False, f"{PIPECAT} holds no ONNX model. {_REINSTALL}")]
    return [_model(f) for f in models]


def _model(file: metadata.PackagePath) -> Check:
    name = f"onnx {file.name}"
    try:
        digest = hashlib.sha256(file.read_binary()).digest()
    except OSError as error:
        return Check(name, False, f"cannot be read ({type(error).__name__}). {_REINSTALL}")
    recorded = file.hash
    expected = recorded.value if recorded is not None and recorded.mode == "sha256" else None
    shown = f"sha256 {digest.hex()}"
    if expected != base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii"):
        return Check(name, False, f"{shown} differs from the wheel's record. {_REINSTALL}")
    return Check(name, True, shown)


def _clock(settings: VoiceSettings) -> Check:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    skew = settings.join.max_clock_skew_s
    return Check(
        "clock",
        True,
        f"this machine's UTC time is {now}; join tokens are taken up to {skew} s off it "
        "(join.max_clock_skew_s); its skew against another clock is not measured",
    )


def _failure(error: ConfigurationError | ProviderError) -> str:
    """A failure's own message, which holds no value; a provider's with its kind, then its
    adapter's FIX line when its details hold one (`fix`)."""
    if not isinstance(error, ProviderError):
        return error.message
    shown = f"{error.message} ({error.kind})"
    fix = error.details.get("fix")
    return f"{shown} {fix}" if isinstance(fix, str) else shown


def _primary(tag: LanguageTag) -> str:
    return "en" if tag == "en" else "ar"
