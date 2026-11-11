"""The measuring part of a `poe first-audio` run (`first_audio.py`; plan 006's registration, T):
the agent's fixed phrases declared once, then each recording replayed as a fresh call of the
agent with the real speech-to-text, chat model, knowledge and voice, paced between recordings
and held under the run's cap and the key's day.

**The replay** is the seam to the library (`Replay`): one call of the agent per recording, at
real-time pace, the recording's labelled end handed in where marked, and what the call gives
back (`ReplayedCall`); the run's is the `evals` facade's `AudioCall` replaying the recording as a
turn of the agent's talker (first_audio_replay.py), a test's a fake.

**Limits.** Before each recording the run waits until each model's pacer has room for what one
recording may send (`STT_PER_VARIANT`, `TTS_PER_VARIANT` to its voice, `CHAT_PER_VARIANT`), or
for as many as its limit allows; refuses to start one whose budget (`Prices.budget`: each
request at its most) would take the run past `--cap-usd`; and stops before one when a model's
headroom for the key's day, as the provider last reported it in a call's usage (Groq's
`x-ratelimit-remaining-requests`), is under what one recording may send it. A recording whose
call met a rate limit is replayed after `RATE_LIMIT_PAUSE_S`, up to `MAX_ATTEMPTS` calls, every
call's requests counted, and what the clause cache did in each call, when the run has one, kept
apart (first_audio_cache.py). The phrase cache's requests are counted on each voice's pacer before
the first recording, each at its most characters.

**The call's language** is the one the agent gives a caller whose locale is the recording's
(`held_in`, the library's `VoiceAgent.call_language`): an MSA request is held in Saudi Arabic by
an agent that declares no MSA, as Ole5's talker is (it answers MSA in MSA within it), and as its
real call would be; a run whose agent speaks no language of a recording's locale is refused.
**The tail** after each recording (`tail_of`) is the slowest reply that still answers: its
turn's end, its transcript, the talker's every model request and its slowest tool between them,
each at its time limit, and the voice's first request at its own; a reply not heard by then is
counted as one never heard (first_audio_score.py's `no_audio`), never dropped.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

from t2_agentic_voice import Tool, VoiceAgent, VoiceSettings, get_logger
from t2_agentic_voice.evals import PhraseAudio
from t2_agentic_voice.events import ModelUsage
from t2_agentic_voice.ports import AudioClip

from ole5_voice.evals.audio import read_wav, write_wav
from ole5_voice.evals.first_audio_cache import ClauseCall
from ole5_voice.evals.first_audio_score import AudioResult, ChatSpend, ReplayedCall, result_of
from ole5_voice.evals.groq_answerer import GROQ_MINIMUM_S, Sleep
from ole5_voice.evals.models import Language as ItemLanguage
from ole5_voice.evals.models import Split
from ole5_voice.evals.pacers import MinutePacer
from ole5_voice.evals.run_parts import Todo
from ole5_voice.evals.timing_run import TAGS, Tag
from ole5_voice.evals.timing_score import cost

STT_PER_VARIANT: Final = 2  # a turn's transcript, and a second turn's when the caller's is cut
# The greeting the replay says before the call, and a spoken reply's clauses: one to three
# short sentences, and room.
TTS_PER_VARIANT: Final = 5
CHAT_PER_VARIANT: Final = 3  # the talker's most model requests a turn
TTS_CHARS_PER_VARIANT: Final = 800  # the voice's most characters a request (200) times four
MAX_CHARS: Final = 200
MAX_ATTEMPTS: Final = 3
RATE_LIMIT_PAUSE_S: Final = 60.0  # a whole pacer window, the per-minute limit's own
LEAD_S: Final = 1.0  # digital silence before each recording (the golden set's runs')
TURN_END_S: Final = 1.0  # the caller's turn ended after its speech: the hold and the detector
TOOL_TIMEOUT_S: Final = 5.0  # a declared tool's time limit when it names none (the library's)
REPLIES_DIR: Final = "replies"  # a dev run's reply openings, for the owner's listen
log = get_logger(__name__)


def tail_of(settings: VoiceSettings, agent: VoiceAgent) -> float:
    """The silence after each recording, in seconds (the module's docstring): the talker's
    `CHAT_PER_VARIANT` model requests with its slowest tool run between each two."""
    tool_s = max(
        (t.timeout_s if isinstance(t, Tool) else TOOL_TIMEOUT_S for t in agent.tools), default=0.0
    )
    talker = CHAT_PER_VARIANT * settings.llm.timeout_s + (CHAT_PER_VARIANT - 1) * tool_s
    return TURN_END_S + settings.stt.timeout_s + talker + settings.tts.timeout_s


def held_in(agent: VoiceAgent, language: ItemLanguage) -> Tag:
    """The tag of the language a recording of `language` is held in: the one `agent` gives a
    caller of its locale (`TAGS`), or its first when it speaks none of that locale's."""
    return agent.call_language(None, locale=TAGS[language]).tag


def speaks(agent: VoiceAgent, language: ItemLanguage) -> bool:
    """Whether `agent` speaks a language of the locale of a recording of `language` (its
    primary subtag: `ar` for Saudi Arabic and MSA)."""
    return held_in(agent, language).partition("-")[0] == TAGS[language].partition("-")[0]


class Replay(Protocol):
    """The replay of a recording as a call of the agent, or a test's fake."""

    async def start(self) -> None:
        """Start the calls' runtime once, before the first recording."""

    async def clear(self) -> None:
        """Empty the clause cache the calls speak through, its counts too, when the run keeps
        one (run I's arm): once the smoke call has passed."""

    async def call(
        self,
        clip: AudioClip,
        *,
        language: Tag,
        end_ms: float | None,
        lead_s: float,
        tail_s: float,
    ) -> ReplayedCall:
        """Replay `clip` as one call held in `language`, its speech's labelled end `end_ms`
        from its start where marked (None: the detector's stop less its delay)."""

    async def aclose(self) -> None:
        """Close the calls' runtime, after the last recording."""


# How a replay is built: with `agent`, `settings`, `stt`, `tts`, `llm` and `phrases`.
ReplayFactory = Callable[..., Replay]


class Phrases(PhraseAudio, Protocol):
    """The phrase cache as a run uses it (the `stores` facade's `PhraseCache`)."""

    def declare(self, agent: VoiceAgent) -> Awaitable[int]:
        """Have each fixed phrase of `agent` at hand; how many requests that sent."""


class Closes(Protocol):
    """An adapter a run closes once it is done with it."""

    async def aclose(self) -> None:
        """Close what it holds open."""


class CapReachedError(Exception):
    """The next recording's budget would take the run past `--cap-usd`."""


class DayLimitError(Exception):
    """A model's headroom for the day is under what the next recording may send it."""


@dataclass(frozen=True)
class Prices:
    """What a request costs, the most the chat model reads a request, and the cap."""

    stt_model: str
    per_hour_usd: float
    per_million_chars_usd: Mapping[str, float]
    chat_input_usd: float
    chat_cached_usd: float
    chat_output_usd: float
    chat_input_tokens: int
    chat_output_tokens: int
    cap_usd: float

    def of(self, usages: Iterable[ModelUsage], chats: Iterable[ChatSpend]) -> float:
        """What `usages` and `chats` cost."""
        speech = cost(
            usages,
            stt_model=self.stt_model,
            price_per_hour_usd=self.per_hour_usd,
            tts_price_per_million_usd=self.per_million_chars_usd,
        )
        chat = sum(
            (each.input_tokens - each.cached_tokens) * self.chat_input_usd
            + each.cached_tokens * self.chat_cached_usd
            + each.output_tokens * self.chat_output_usd
            for each in chats
        )
        return speech + chat / 1e6

    def phrases(self, requests: int) -> float:
        """The most the phrase cache's `requests` cost: each at the voices' highest price."""
        return requests * MAX_CHARS / 1e6 * max(self.per_million_chars_usd.values(), default=0.0)

    def budget(self, clip_s: float, tts_model: str) -> float:
        """The most one recording of `clip_s` seconds is budgeted to cost."""
        billed = STT_PER_VARIANT * max(GROQ_MINIMUM_S, clip_s)
        voice = TTS_CHARS_PER_VARIANT / 1e6 * self.per_million_chars_usd.get(tts_model, 0.0)
        reads = self.chat_input_tokens * max(self.chat_input_usd, self.chat_cached_usd)
        chat = CHAT_PER_VARIANT * (reads + self.chat_output_tokens * self.chat_output_usd) / 1e6
        return billed / 3600 * self.per_hour_usd + voice + chat


@dataclass
class Measuring:
    """One run's measuring: the agent and its replay, the phrase cache, the pacers by model,
    the prices, where a dev run's reply openings go, and what it found."""

    agent: VoiceAgent
    settings: VoiceSettings
    replay: Replay
    phrases: Phrases
    pacers: Mapping[str, MinutePacer]
    prices: Prices
    sleep: Sleep
    replies: Path | None  # None for a held-out run, which keeps no reply
    tail_s: float  # the silence after each recording (`tail_of`)
    adapters: tuple[Closes, ...] = ()  # the speech, voice and chat adapters, closed at the end
    usages: list[ModelUsage] = field(default_factory=list)  # every call's, in order
    chats: list[ChatSpend] = field(default_factory=list)
    phrase_requests: int = 0
    _headroom: dict[str, int] = field(default_factory=dict)

    @property
    def spent_usd(self) -> float:
        return self.prices.of(self.usages, self.chats) + self.prices.phrases(self.phrase_requests)

    def tts_model(self, tag: Tag) -> str:
        return self.settings.tts.languages[tag].model

    async def declare(self) -> None:
        """The fixed phrases, at hand before the first recording, their requests counted."""
        self.phrase_requests = await self.phrases.declare(self.agent)
        for model in {self.tts_model(language.tag) for language in self.agent.languages}:
            self.pacers[model].count(min(self.phrase_requests, self.pacers[model].limit))

    async def variant(self, todo: Todo, side: Split) -> AudioResult:
        """One recording's call, held in the language the agent gives its caller (`held_in`),
        replayed while it meets a rate limit, its time from the owner's label of its speech's
        end (the last of `turn_ends_ms`) where marked."""
        item, variant = todo.item, todo.variant
        tag = held_in(self.agent, item.language)
        clip = AudioClip(pcm16=b"".join(read_wav(p).pcm16 for p in todo.request.segments))
        end_ms = float(variant.turn_ends_ms[-1]) if variant.turn_ends_ms else None
        base: dict[str, object] = {
            "item": item.id,
            "variant": variant.id,
            "split": side,
            "language": item.language,
            "device": variant.device,
            "end": "detector" if end_ms is None else "label",
            "end_ms": end_ms,
        }
        attempts, clauses = 0, list[ClauseCall]()  # what the clause cache did in each call
        while True:
            attempts += 1
            call = await self._call(clip, tag, end_ms)
            clauses += [] if call.clauses is None else [call.clauses]
            limited = any(turn.failure == "rate_limited" for turn in call.turns)
            if not limited or attempts >= MAX_ATTEMPTS:
                break
            log.warning("variant_rate_limited", attempt=attempts, pause_s=RATE_LIMIT_PAUSE_S)
            await self.sleep(RATE_LIMIT_PAUSE_S)
        return result_of(base, call, attempts, self._openings(todo, call), tuple(clauses))

    async def _call(self, clip: AudioClip, tag: Tag, end_ms: float | None) -> ReplayedCall:
        """One paced call, refused at the cap and at the day's headroom, its requests
        counted."""
        tts_model = self.tts_model(tag)
        wanted = {
            self.prices.stt_model: STT_PER_VARIANT,
            tts_model: TTS_PER_VARIANT,
            self.settings.llm.model: CHAT_PER_VARIANT,
        }
        for model, most in wanted.items():
            if self._headroom.get(model, most) < most:
                raise DayLimitError
            pacer = self.pacers[model]
            await pacer.room_for(min(most, pacer.limit))
        if self.spent_usd + self.prices.budget(clip.seconds, tts_model) > self.prices.cap_usd:
            raise CapReachedError
        call = await self.replay.call(
            clip, language=tag, end_ms=end_ms, lead_s=LEAD_S, tail_s=self.tail_s
        )
        self.usages.extend(call.usage)
        self.chats.append(call.chat)
        for usage in call.usage:
            if usage.model in self.pacers:
                self.pacers[usage.model].count(usage.requests)
            if usage.remaining_requests is not None:
                self._headroom[usage.model] = usage.remaining_requests
        self.pacers[self.settings.llm.model].count(call.chat.requests)
        if call.chat.remaining_requests is not None:
            self._headroom[self.settings.llm.model] = call.chat.remaining_requests
        return call

    def _openings(self, todo: Todo, call: ReplayedCall) -> tuple[str | None, ...]:
        """Each reply's opening written into the run's folder (a dev run's), by its name."""
        if self.replies is None:
            return ()
        found: list[str | None] = []
        for number, chunk in enumerate(call.openings):
            if chunk is None or not chunk.pcm16:
                found.append(None)
                continue
            name = f"{todo.variant.id}-{number}.wav"
            self.replies.mkdir(exist_ok=True)
            (self.replies / name).write_bytes(write_wav(chunk.pcm16, chunk.sample_rate))
            found.append(f"{REPLIES_DIR}/{name}")
        return tuple(found)

    async def aclose(self) -> None:
        await self.replay.aclose()
        for adapter in self.adapters:
            await adapter.aclose()
