"""The measuring part of a `poe eval-timing` run (`timing.py`): the fixed phrases declared once,
the smoke test, then each paused request as a fresh echo call through the `evals` facade's
`echo_timings`, paced between variants and held under the run's cap.

Before each variant the run waits until its pacers have room for the most a variant is budgeted
to send (`STT_PER_VARIANT` Whisper requests and `TTS_PER_VARIANT` to its Orpheus model: up to two
turns a variant, a cut-off splitting one in two, and one heard-words clause a turn, the
registration's T), and refuses to start one whose budgeted cost would take the run past
`--cap-usd`. A variant whose call met a rate limit is run again after `RATE_LIMIT_PAUSE_S`, up to
`MAX_ATTEMPTS` calls in all, every call's requests counted. The phrase cache sends its requests
one at a time with no pacer of its own (adapters/phrase_cache.py), so the requests it returns
are counted on every Orpheus model's pacer before the first variant.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol

from t2_agentic_voice import Language, VoiceAgent, VoiceSettings, get_logger
from t2_agentic_voice.evals import EchoTiming, PhraseAudio
from t2_agentic_voice.events import ModelUsage
from t2_agentic_voice.ports import AudioClip, SpeechToText, TextToSpeech

from ole5_voice.evals.audio import read_wav
from ole5_voice.evals.eot import LEAD_S, TAIL_S
from ole5_voice.evals.groq_answerer import GROQ_MINIMUM_S, Sleep
from ole5_voice.evals.models import Language as ItemLanguage
from ole5_voice.evals.pacers import MinutePacer
from ole5_voice.evals.run_parts import Todo
from ole5_voice.evals.timing_score import TimingResult, cost, failure_of, judged

STT_PER_VARIANT: Final = 2
TTS_PER_VARIANT: Final = 2
MAX_CHARS: Final = 200  # the most characters one Orpheus request takes (Groq's Orpheus page)
MAX_ATTEMPTS: Final = 3
RATE_LIMIT_PAUSE_S: Final = 60.0  # a whole pacer window, the per-minute limit's own
# The agent a timing run calls: one language per register the paused requests are in, each
# opening its calls with a short greeting, so a call reaches its clip soon.
AGENT: Final = VoiceAgent(
    name="ole5-timing",
    languages=[
        Language.saudi_arabic(greeting="مرحبا"),
        Language.arabic(greeting="مرحبا"),
        Language.english(greeting="Hello."),
    ],
)
# The language a variant's call is held in, by its item's: Saudi and mixed requests in Saudi
# Arabic, MSA in Modern Standard Arabic, English in English.
Tag = Literal["ar-SA", "ar", "en"]  # the library's language tags (`Language.tag`)
TAGS: Final[Mapping[ItemLanguage, Tag]] = {
    "saudi": "ar-SA",
    "mixed": "ar-SA",
    "msa": "ar",
    "english": "en",
}
log = get_logger(__name__)
EchoTimings = Callable[..., AsyncIterator[EchoTiming]]


class Phrases(PhraseAudio, Protocol):
    """The phrase cache as a timing run uses it (the `stores` facade's `PhraseCache`)."""

    def declare(self, agent: VoiceAgent) -> Awaitable[int]:
        """Have each fixed phrase of `agent` at hand; how many requests that sent."""


class CapReachedError(Exception):
    """The next variant's budgeted cost would take the run past `--cap-usd`."""


@dataclass
class Prices:
    """What a request costs, and the most the run may spend."""

    stt_model: str
    per_hour_usd: float
    per_million_usd: Mapping[str, float]
    cap_usd: float

    def of(self, usages: Iterable[ModelUsage]) -> float:
        """What `usages` cost (`timing_score.cost`)."""
        return cost(
            usages,
            stt_model=self.stt_model,
            price_per_hour_usd=self.per_hour_usd,
            tts_price_per_million_usd=self.per_million_usd,
        )

    def budget(self, clip_s: float, tts_model: str) -> float:
        """The most one variant of `clip_s` seconds is budgeted to cost."""
        billed = STT_PER_VARIANT * max(GROQ_MINIMUM_S, clip_s)
        characters = TTS_PER_VARIANT * MAX_CHARS
        tts = characters / 1e6 * self.per_million_usd.get(tts_model, 0.0)
        return billed / 3600 * self.per_hour_usd + tts


@dataclass
class Measuring:
    """One timing run's measuring: what it calls, its pacers and prices, and what it found."""

    settings: VoiceSettings
    stt: SpeechToText
    tts: TextToSpeech
    phrases: Phrases
    echo_timings: EchoTimings
    pacers: Mapping[str, MinutePacer]
    prices: Prices
    sleep: Sleep
    usages: list[ModelUsage] = field(default_factory=list)  # every call's, in order
    phrase_requests: int = 0

    def tts_model(self, tag: Tag) -> str:
        return self.settings.tts.languages[tag].model

    async def declare(self) -> None:
        """The fixed phrases, at hand before the first variant, their requests counted."""
        self.phrase_requests = await self.phrases.declare(AGENT)
        for model in {self.tts_model(language.tag) for language in AGENT.languages}:
            self.pacers[model].count(self.phrase_requests)

    async def variant(self, todo: Todo) -> TimingResult:
        """One variant's echo call, run again while it meets a rate limit."""
        tag = TAGS[todo.item.language]
        clip = AudioClip(pcm16=b"".join(read_wav(p).pcm16 for p in todo.request.segments))
        attempts = 0
        while True:
            attempts += 1
            timing = await self._call(clip, tag)
            if failure_of(timing) != "rate_limited" or attempts >= MAX_ATTEMPTS:
                break
            log.warning("variant_rate_limited", attempt=attempts, pause_s=RATE_LIMIT_PAUSE_S)
            await self.sleep(RATE_LIMIT_PAUSE_S)
        true_end = float(todo.variant.turn_ends_ms[-1])
        cut, place, steps = judged(timing, true_end)
        return TimingResult(
            item=todo.item.id,
            variant=todo.variant.id,
            split="dev",
            language=todo.item.language,
            device=todo.variant.device,
            true_end_ms=true_end,
            attempts=attempts,
            turns=timing.turns,
            cut=cut,
            timed_turn=place,
            steps=steps,
            failure=failure_of(timing),
        )

    async def _call(self, clip: AudioClip, tag: Tag) -> EchoTiming:
        """One paced call, refused at the cap, its requests counted on the pacers."""
        tts_model = self.tts_model(tag)
        await self.pacers[self.prices.stt_model].room_for(STT_PER_VARIANT)
        await self.pacers[tts_model].room_for(TTS_PER_VARIANT)
        spent = self.prices.of(self.usages)
        if spent + self.prices.budget(clip.seconds, tts_model) > self.prices.cap_usd:
            raise CapReachedError
        found = self.echo_timings(
            [(clip, tag)],
            agent=AGENT,
            settings=self.settings,
            stt=self.stt,
            tts=self.tts,
            phrases=self.phrases,
            lead_s=LEAD_S,
            tail_s=TAIL_S,
        )
        timing = EchoTiming(turns=(), usage=())
        async for each in found:
            timing = each
        self.usages.extend(timing.usage)
        for usage in timing.usage:
            if usage.model in self.pacers:
                self.pacers[usage.model].count(usage.requests)
        return timing

    async def aclose(self) -> None:
        await self.stt.aclose()
        await self.tts.aclose()
