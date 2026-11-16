"""A speech-to-text provider's own language, as a classifier a pass of `poe eval-languages`
hears each turn through (languages_run.py, D-100): `ProviderLanguage`.

It wraps the provider's adapter, which `Providers.speech_to_text` builds from `stt.provider`,
and sends each turn's first `stt.classifier_from_s` of speech, the seconds the library's rule
hands a classifier, with no language named and no prompt, so the provider detects the
language itself. The language it heard (`Transcript.heard_language`, else, for Whisper on Groq,
the `language` it reported) becomes the turn's scores: its probability (ElevenLabs'
`language_probability`) its share, the rest shared among the agent's other codes; 1 when the
provider gives no score (Whisper on Groq, Soniox); an even share with that probability as the
mass when it is below an even share, since the score is the provider's confidence in its top
language among about a hundred and the rest is mostly languages outside the agent's, so no
other code becomes the best; and an even share with no mass when it heard no language, or one
not among the agent's codes. Both even shares leave the rule unsure. Only the
providers that report a language take part (`PROVIDERS`); Speechmatics' pack and Cohere report
none. It lives in the app's evals, never in the library: the library's classifiers send no
audio anywhere (invariant 8), and this one sends every classified turn to the provider, paid.

One classification at a time: a second ask while one is out is answered busy (None), as the
port says. Each request is counted billed as it is sent, at the provider's least a request
(Groq's 10 s) or the seconds sent, a failed one too, so the pass records what it spent at the
most. `check_pass_cost` logs the pass's dry estimate before any clip is fed, the most it can
send (each turn classified holds `from_s` of the fed audio, turns never overlap) and cost, and
refuses a pass whose most passes `--cap-usd`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final, Literal

from t2_agentic_voice import Providers, VoiceSettings, get_logger
from t2_agentic_voice.evals import run_refused
from t2_agentic_voice.ports import AudioClip, LanguageScores, SpeechToText, Transcript

from ole5_voice.evals.runs import cost_usd
from ole5_voice.evals.stt_arms import ARMS, SttArm

log = get_logger(__name__)
# The providers whose answer names the language they heard, in `ARMS`' order.
PROVIDERS: Final = tuple(name for name, arm in ARMS.items() if arm.hears_language)
# A provider's names of the agent's languages that are not codes (Whisper's).
_NAMES: Final = {"arabic": "ar", "english": "en"}


def code_of(heard: str | None, among: Sequence[str]) -> str | None:
    """The code of `among` a provider's language names, exactly: the code itself, a tagged
    form of it ("ar-SA", "en_US") or Whisper's name of it ("Arabic"), in any case; None for
    none or any other ("armenian" is not "ar")."""
    named = (heard or "").strip().casefold()
    primary = named.replace("_", "-").split("-")[0]
    code = _NAMES.get(named, primary)
    return code if code in among else None


def scores_of(transcript: Transcript, among: Sequence[str]) -> LanguageScores:
    """A provider's answer as a classifier's (the module's docstring)."""
    code = code_of(transcript.heard_language or transcript.language, among)
    if code is None:
        even = 1 / len(among)
        return LanguageScores.parsed(dict.fromkeys(among, even), among=among, mass=0.0)
    share = 1.0 if transcript.language_probability is None else transcript.language_probability
    even = 1 / len(among)
    if share < even:  # the rest is mostly languages outside `among`: never another's best
        return LanguageScores.parsed(dict.fromkeys(among, even), among=among, mass=share)
    rest = (1 - share) / (len(among) - 1)
    shares = {each: share if each == code else rest for each in among}
    return LanguageScores.parsed(shares, among=among, mass=share)


class ProviderLanguage:
    """A provider's own language as a classifier (the module's docstring); what it sent so far
    in `requests` and `billed_seconds`."""

    def __init__(self, stt: SpeechToText, arm: SttArm) -> None:
        self.name = f"{arm.provider}-language"
        self.arm = arm
        self._stt = stt
        self._busy = False
        self.requests = 0
        self.billed_seconds = 0.0

    async def load(self, among: Sequence[str]) -> None:
        """Nothing to load: the provider is asked at each turn."""

    async def classify(self, clip: AudioClip, *, among: Sequence[str]) -> LanguageScores | None:
        """The provider's language for `clip` as the scores of `among`; None while another
        clip is out. Its `ProviderError` passes on unchanged."""
        if self._busy:
            return None
        self._busy = True
        self.requests += 1
        self.billed_seconds += max(self.arm.minimum_s, clip.seconds)
        try:
            transcript = await self._stt.transcribe(clip, language=None, prompt=None)
        finally:
            self._busy = False
        return scores_of(transcript, among)

    async def aclose(self) -> None:
        """Close the provider's adapter."""
        await self._stt.aclose()


def provider_language(settings: VoiceSettings) -> ProviderLanguage:
    """The classifier of the provider `stt.provider` names, its adapter built by the library
    with no IO (a ConfigurationError naming the key's setting when it has none)."""
    return ProviderLanguage(Providers.speech_to_text(settings), ARMS[settings.stt.provider])


def most_requests(seconds: Sequence[float], *, from_s: float, tail_s: float) -> int:
    """The most turns a pass can classify over clips of `seconds`, each fed with `tail_s` of
    silence after it: each classified turn holds `from_s` of its own audio."""
    return sum(math.floor((each + tail_s) / from_s) for each in seconds)


def check_pass_cost(
    arm: SttArm,
    seconds: Sequence[float],
    *,
    from_s: float,
    tail_s: float,
    price_per_hour_usd: float,
    cap_usd: float,
    estimate_only: bool,
) -> Literal["estimated", "within"]:
    """Log the pass's dry estimate (the module's docstring), then refuse it when its most cost
    passes `cap_usd`. `estimated` for `--estimate-only`, so nothing is fed; else `within`."""
    most = most_requests(seconds, from_s=from_s, tail_s=tail_s)
    billed = most * max(arm.minimum_s, from_s)
    most_usd = cost_usd(billed, price_per_hour_usd)
    log.info(
        "run_estimate",
        provider=arm.provider,
        variants=len(seconds),
        most_requests=most,
        most_billed_s=round(billed, 1),
        most_usd=round(most_usd, 4),
        cap_usd=cap_usd,
    )
    if most_usd > cap_usd:
        raise run_refused(
            f"the pass's most cost, ${most_usd:.4f}, passes --cap-usd",
            "raise --cap-usd, or check --price-per-hour",
        )
    return "estimated" if estimate_only else "within"
