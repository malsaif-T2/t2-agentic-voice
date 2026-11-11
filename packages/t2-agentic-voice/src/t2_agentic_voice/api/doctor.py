"""`t2v doctor` (the first part of the design's 10.6): what a first call needs that the library
can check without a call, each a `Check` that passes or says what to fix.

- **The key**, from the settings (inline or in its file), with no request.
- **Each language's model and voice**, through the text-to-speech adapter's `check_language`:
  the key and the model list (a GET), with no synthesis, so a model whose terms are not accepted
  shows only with `--synthesize`.
- **The ONNX files** Silero VAD and Smart Turn run on, each file's SHA-256 against the one the
  installed Pipecat wheel's record holds, read from its metadata: Pipecat is not imported.
- **The classifier's files** (plan 007's Block H), under `stt.live_language = "classified"`:
  each model file in `stt.classifier_dir` against its pinned size and SHA-256
  (adapters/model_files.py), as the ONNX files are checked; and under `stt.classifier =
  "ecapa"`, whether torch is installed and any CUDA package (`nvidia-*`, `cuda-*`) or triton
  beside it, read from the installed distributions' metadata, never by importing torch.
- **The clock**: this machine's UTC time and its skew against the text-to-speech provider's
  clock, with no request of its own: `check_language` returns the time the provider's answer
  gave (Groq's `Date` header, whole seconds), and the skew is this machine's time at the middle
  of that request minus it, rounded down to the second, from the last language check that gave
  one. Rounded so, it is within 1 s of the true skew; so the check passes while the skew plus
  1 s stays within the join tokens' allowance (`join.max_clock_skew_s`), and past it fails
  with a FIX line that says how to set the clock, since tokens minted on a machine whose clock
  is right would be refused. With no language check passed, or no time in their answers, the
  line says the skew was not measured and why, and does not fail.
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
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Final

from t2_agentic_voice.adapters.ecapa_language import ECAPA_FILES
from t2_agentic_voice.adapters.model_files import ModelFile, digest, folder_problem, problem
from t2_agentic_voice.adapters.silero_language import SILERO_FILES
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
_EXTRA = "FIX: install the library's ecapa extra (in this workspace: uv sync --group language-id)."
# The resolution of the provider's time: an HTTP Date holds whole seconds.
RESOLUTION_S: Final = 1
_SET_CLOCK = (
    "FIX: set this machine's clock: on Windows, Settings > Time & language > Date & time > "
    "Sync now, or w32tm /resync in an administrator's terminal; elsewhere, sync it with NTP "
    "(on Linux, timedatectl set-ntp true)."
)
# This machine's UTC time, aware.
Wall = Callable[[], datetime]


@dataclass(frozen=True)
class Check:
    """One check: what it checked, whether it passed, and what it found or how to fix it."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class _Reading:
    """The time `provider`'s answer to a language check gave (`sent`), and this machine's at
    the middle of that request (`local`)."""

    provider: str
    local: datetime
    sent: datetime

    @property
    def skew_s(self) -> int:
        """This machine's clock minus the provider's, rounded down to the whole second."""
        return math.floor((self.local - self.sent).total_seconds())


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def checks(
    settings: VoiceSettings,
    *,
    synthesize: bool,
    providers: Providers | None = None,
    wall: Wall = _utc_now,
) -> list[Check]:
    """Every check, in order; `providers` are the settings' own unless given (a test's fakes),
    and are closed after when built here; `wall` is this machine's UTC time unless given (a
    test's)."""
    found = [_key(settings)]
    built = providers is None
    if providers is None:
        try:
            providers = Providers.from_settings(settings)
        except ConfigurationError as error:
            clock = _clock(settings, wall(), "no language check ran")
            found += [Check("providers", False, error.message), *onnx()]
            return [*found, *classifier_checks(settings), clock]
    try:
        measured: _Reading | None = None
        passed = False
        for tag in settings.tts.languages:
            check, reading = await _language(providers, tag, wall)
            found.append(check)
            passed, measured = passed or check.ok, reading or measured
        why = (
            f"no answer of {providers.tts.name}'s gave its time (an HTTP Date header)"
            if passed
            else "no language check passed"
        )
        found += [*onnx(), *classifier_checks(settings), _clock(settings, wall(), measured or why)]
        if synthesize:
            for tag in settings.tts.languages:
                found.append(await _synthesis(providers, tag))
    finally:
        if built:
            await providers.stt.aclose()
            await providers.tts.aclose()
            for other in (providers.chat, providers.classifier):
                if other is not None:
                    await other.aclose()
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


async def _language(
    providers: Providers, tag: LanguageTag, wall: Wall
) -> tuple[Check, _Reading | None]:
    """`tag`'s check, and the provider's time its answer gave, if any, against this machine's
    at the middle of the request."""
    name = f"model and voice {tag}"
    before = wall()
    try:
        sent = await providers.tts.check_language(tag)
    except (ConfigurationError, ProviderError) as error:
        return Check(name, False, _failure(error)), None
    local = before + (wall() - before) / 2
    reading = None if sent is None else _Reading(providers.tts.name, local, sent)
    return Check(name, True, "listed"), reading


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


def classifier_checks(
    settings: VoiceSettings,
    *,
    files: Sequence[ModelFile] | None = None,
    installed: Mapping[str, str] | None = None,
) -> list[Check]:
    """The classifier's section (the module's docstring), under `classified` only: its pinned
    `files` (the settings' classifier's unless given) and, for ECAPA, the `installed`
    distributions by name with their versions (this environment's unless given)."""
    stt = settings.stt
    if stt.live_language != "classified":
        return []
    ecapa = stt.classifier == "ecapa"
    pinned = files if files is not None else (ECAPA_FILES if ecapa else SILERO_FILES)
    folder, unset = stt.classifier_dir, folder_problem(stt.classifier_dir)
    found = [Check("classifier folder", False, unset)] if unset is not None else []
    if folder is not None and unset is None:
        found += [_pinned(folder, file) for file in pinned]
    if ecapa:
        found += _torch(_installed() if installed is None else installed)
    return found


def _pinned(folder: Path, file: ModelFile) -> Check:
    name = f"classifier {file.name}"
    try:
        failed = problem(folder, file)
        return Check(name, failed is None, failed or f"sha256 {digest(folder / file.name)}")
    except OSError as error:
        return Check(name, False, f"cannot be read ({type(error).__name__}). FIX: fetch it again.")


def _installed() -> dict[str, str]:
    """Each installed distribution's normalized name, with its version, from the metadata."""
    found = {}
    for each in metadata.distributions():
        name = each.metadata["Name"] or ""
        found[name.lower().replace("_", "-").replace(".", "-")] = each.version
    return found


def _torch(installed: Mapping[str, str]) -> list[Check]:
    """Whether torch is installed for ECAPA, and whether a CUDA package or triton is beside
    it: the CPU wheels the lock takes hold none."""
    version = installed.get("torch")
    torch = (
        Check("torch", True, f"torch {version}, read from its metadata")
        if version is not None
        else Check("torch", False, f"torch is not installed, and ECAPA runs on it. {_EXTRA}")
    )
    gpu = sorted(n for n in installed if n.startswith(("nvidia-", "cuda-")) or n == "triton")
    if not gpu:
        return [torch, Check("cuda", True, "no CUDA package and no triton is installed")]
    fix = (
        "FIX: take torch from PyTorch's CPU index (the workspace root's [tool.uv.sources]) and "
        "sync again; ECAPA runs on the CPU."
    )
    return [torch, Check("cuda", False, f"{', '.join(gpu)} installed beside torch. {fix}")]


def _clock(settings: VoiceSettings, now: datetime, measured: _Reading | str) -> Check:
    """The clock's line: its skew against the provider's (`measured`), or why it was not
    measured, beside this machine's time (`now` when not measured)."""
    allowed = settings.join.max_clock_skew_s
    if isinstance(measured, str):
        return Check(
            "clock",
            True,
            f"this machine's UTC time is {_shown(now)}; join tokens are taken up to {allowed} s "
            f"off it (join.max_clock_skew_s); its skew was not measured: {measured}",
        )
    skew, provider = measured.skew_s, measured.provider
    said = (
        f"this machine's UTC time is {_shown(measured.local)}; its skew against {provider}'s "
        f"clock is {skew:+d} s (this machine's minus {provider}'s, read to the second)"
    )
    allowance = f"the {allowed} s join tokens allow (join.max_clock_skew_s)"
    if abs(skew) + RESOLUTION_S <= allowed:
        return Check("clock", True, f"{said}, within {allowance} with 1 s for the reading")
    return Check(
        "clock",
        False,
        f"{said}, past {allowance} with 1 s for the reading, so join tokens minted on a "
        f"machine whose clock is right may be refused. {_SET_CLOCK}",
    )


def _shown(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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
