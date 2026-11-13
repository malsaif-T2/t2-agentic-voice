"""The time of each step of an echo call, measured on the file-fed pipeline: `echo_timings`, which
runs T1 and T2 use over the golden set's paused requests (plan 003's registration, T),
provisional, re-exported by the `evals` facade since an app imports only public modules (plan
003's decision log), with the phrase audio it takes (`PhraseAudio`).

Each clip is fed as a fresh call of one `VoiceCalls`, started once (its start warms one Silero
VAD and one Smart Turn v3.2; each call builds its own speech detector and turn analyzer, as
voice/calls.py says, which wins over this module's first words, that the models load once for
every clip: plan 003's decision log, 2026-11-03), untraced. Each step is timed on the call's
clock, `time.perf_counter`; Pipecat's own steps have about 16 ms resolution on Windows under
Python 3.12, and Smart Turn stalls the audio 100 to 163 ms at each speech stop (plan 003's
appendix, "Changes to the plan's interfaces", item 23). A turn's times come from the events the
Pipecat side handed its session and the commands the session gave (voice/file_transport.py's
`FedCall`), and the heard words' first sound from their audio as the text-to-speech gave it,
which `echo_timings` reads on its way to the pipeline, changing nothing of it
(timed_speech.py). A turn's own transcript is its `turn` part's `Transcribing` and
`Transcribed` only: an overlap's `window` and `overlap` parts (plan 005) are not its request.

A call's usage per model is counted from the same events, as voice/session/io.py's usage says: each
`Transcribing` one speech-to-text request, whatever its part, its audio sent and billed at least
`WHISPER_MIN_BILLED_S` (core/settings/stt.py); each `Synthesizing` one text-to-speech request, its
`Speak`'s text the characters sent; each fixed phrase played from the phrase audio a cache hit; and
the last headroom the provider reported, each model's.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import AsyncIterator, Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderErrorKind
from t2_agentic_voice.core.events import Event, ModelUsage, TurnId
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.stt import WHISPER_MIN_BILLED_S
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.testing.timed_speech import Take, TimedSpeech
from t2_agentic_voice.testing.turns import CLIP_RATE
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.protocol import ClauseIndex, ReplyId
from t2_agentic_voice.voice.session.commands import Speak
from t2_agentic_voice.voice.session.io import PhraseAudio
from t2_agentic_voice.voice.session.session_events import (
    AgentAudio,
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Synthesizing,
    Transcribed,
    Transcribing,
    TurnClosed,
    TurnOpened,
)

if TYPE_CHECKING:  # named in annotations only; feed_file is imported at first use
    from t2_agentic_voice.voice.file_transport import FedCall

# A file-fed call's caller and consent: no identity source, and nothing recorded.
_CALLER = Caller(subject="echo-timings")
_CONSENT = Consent(version=None, record_audio=False)
_Clause = tuple[ReplyId, ClauseIndex]


class TurnTiming(BaseModel):
    """When each step of one turn of a file-fed echo call happened, in milliseconds from the
    clip's start, each None when it did not: the speech detector's last stop before the turn's
    end; the turn's end; the speech-to-text request sent and answered; the echo's text ready
    (the heard words' first `Speak` given); the cached frame's first audio sent (the first
    output frame from its first audio queued on); the heard words' text-to-speech request sent,
    its first audio, and its first sound above the noise floor (timed_speech.py's
    `NOISE_FLOOR`) as the provider gave it; how much of its audio came before that sound
    (`leading_silence_ms`, a length of audio, not a time); and the failure the turn met, its
    transcript's or one of its echo's clauses', as `ProviderError` names it. A turn whose
    speech began while the agent spoke has no echo (voice/session/io.py's drop rule)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    turn_id: TurnId
    speech_stop_ms: float | None = None
    end_ms: float | None = None
    stt_sent_ms: float | None = None
    stt_answered_ms: float | None = None
    echo_text_ms: float | None = None
    frame_audio_ms: float | None = None
    tts_sent_ms: float | None = None
    tts_first_audio_ms: float | None = None
    heard_sound_ms: float | None = None
    leading_silence_ms: float | None = None
    failure: ProviderErrorKind | None = None


class EchoTiming(BaseModel):
    """One file-fed echo call: each of its turns' timings, in the order they opened, and each
    model's usage, speech-to-text's first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    turns: tuple[TurnTiming, ...]
    usage: tuple[ModelUsage, ...]


@dataclass
class _Usage:
    """One model's counts as a call's events give them."""

    requests: int = 0
    audio_sent_s: float = 0.0
    billed_s: float = 0.0
    characters: int = 0
    cache_hits: int = 0
    remaining: tuple[int | None, int | None] = (None, None)

    def seen(self, requests: int | None, tokens: int | None) -> None:
        if requests is not None or tokens is not None:
            self.remaining = (requests, tokens)


@dataclass
class _Call:
    """One fed call's events, indexed: each turn's, each clause's, and the output frames' times."""

    fed: FedCall
    opened: list[TurnOpened] = field(default_factory=list)
    closed: dict[TurnId, TurnClosed] = field(default_factory=dict)
    sent: dict[TurnId, Transcribing] = field(default_factory=dict)
    heard: dict[TurnId, Transcribed] = field(default_factory=dict)
    synthesizing: dict[_Clause, Synthesizing] = field(default_factory=dict)
    queued: dict[_Clause, ClauseQueued] = field(default_factory=dict)
    failed: dict[_Clause, ClauseFailed] = field(default_factory=dict)
    frames: list[float] = field(default_factory=list)  # each output frame's time, in order

    def __post_init__(self) -> None:
        for event in self.fed.events:
            if isinstance(event, TurnOpened):
                self.opened.append(event)
            elif isinstance(event, TurnClosed):
                self.closed.setdefault(event.turn_id, event)
            elif isinstance(event, Transcribing) and event.part == "turn":
                self.sent.setdefault(event.turn_id, event)
            elif isinstance(event, Transcribed) and event.part == "turn":
                self.heard.setdefault(event.turn_id, event)
            elif isinstance(event, Synthesizing):
                self.synthesizing.setdefault((event.reply_id, event.clause), event)
            elif isinstance(event, ClauseQueued):
                self.queued.setdefault((event.reply_id, event.clause), event)
            elif isinstance(event, ClauseFailed):
                self.failed.setdefault((event.reply_id, event.clause), event)
            elif isinstance(event, AgentAudio) and event.pcm16:
                self.frames.append(event.at)
        self.frames.sort()

    def ms(self, at: float | None) -> float | None:
        return None if at is None else (at - self.fed.started_at) * 1000

    def frame_from(self, at: float) -> float | None:
        """The first output frame at or after `at`."""
        index = bisect_left(self.frames, at)
        return self.frames[index] if index < len(self.frames) else None


def timing_of(fed: FedCall, takes: Iterable[Take]) -> tuple[TurnTiming, ...]:
    """Each turn of `fed`, in the order the turns opened, timed from its events and commands
    and from `takes`, the call's text-to-speech requests in the order they were sent: a turn's
    heard words take the first take not yet claimed with their text and language."""
    call = _Call(fed)
    unclaimed = list(takes)
    speaks = [(at, command) for at, command in fed.commands if isinstance(command, Speak)]
    return tuple(_turn(call, opened.turn_id, speaks, unclaimed) for opened in call.opened)


def _turn(
    call: _Call, turn: TurnId, speaks: list[tuple[float, Speak]], unclaimed: list[Take]
) -> TurnTiming:
    """One turn's timing; the take its heard words claim leaves `unclaimed`."""
    times: dict[str, float | None] = {}
    if (closed := call.closed.get(turn)) is not None:
        times |= {"speech_stop_ms": call.ms(closed.speech_ended_at), "end_ms": call.ms(closed.at)}
    if (sent := call.sent.get(turn)) is not None:
        times["stt_sent_ms"] = call.ms(sent.at)
    failure: ProviderErrorKind | None = None
    if (heard := call.heard.get(turn)) is not None:
        times["stt_answered_ms"] = call.ms(heard.at)
        failure = heard.failure
    echo = [(at, speak) for at, speak in speaks if speak.turn_id == turn]
    for _, speak in echo:
        failed = call.failed.get((speak.reply_id, speak.clause))
        failure = failure or (failed.failure if failed is not None else None)
    frame = next((speak for _, speak in echo if speak.audio is not None), None)
    if frame is not None and (queued := call.queued.get((frame.reply_id, frame.clause))):
        times["frame_audio_ms"] = call.ms(call.frame_from(queued.at))
    words = next(((at, speak) for at, speak in echo if speak.audio is None), None)
    if words is not None:
        at, speak = words
        key = (speak.reply_id, speak.clause)
        times["echo_text_ms"] = call.ms(at)
        if (synthesizing := call.synthesizing.get(key)) is not None:
            times["tts_sent_ms"] = call.ms(synthesizing.at)
        if (first := call.queued.get(key)) is not None:
            times["tts_first_audio_ms"] = call.ms(first.at)
        said = (speak.text, speak.language)
        take = next((each for each in unclaimed if (each.text, each.language) == said), None)
        if take is not None:
            unclaimed.remove(take)
            times["heard_sound_ms"] = call.ms(take.first_sound_at)
            if take.leading_silence_s is not None:
                times["leading_silence_ms"] = take.leading_silence_s * 1000
    return TurnTiming.model_validate({"turn_id": turn, "failure": failure, **times})


def usage_of(
    fed: FedCall, *, stt_model: str, tts_models: Mapping[LanguageTag, str]
) -> tuple[ModelUsage, ...]:
    """Each model's usage in `fed`, as voice/session/io.py's usage counts it: speech-to-text's
    under `stt_model`, then each text-to-speech model's, the model of each clause's language
    (`tts_models`), in the order they were first used; a model with nothing counted is left
    out."""
    counts: dict[str, _Usage] = {stt_model: _Usage()}
    speaks = {(c.reply_id, c.clause): c for _, c in fed.commands if isinstance(c, Speak)}

    def model_of(key: _Clause) -> _Usage | None:
        speak = speaks.get(key)
        return None if speak is None else counts.setdefault(tts_models[speak.language], _Usage())

    for key, speak in speaks.items():
        if speak.audio is not None and (model := model_of(key)) is not None:
            model.cache_hits += 1
    stt = counts[stt_model]
    for event in fed.events:
        if isinstance(event, Transcribing):
            stt.requests += 1
            stt.audio_sent_s += event.audio_s
            stt.billed_s += max(WHISPER_MIN_BILLED_S, event.audio_s)
        elif isinstance(event, Transcribed) and event.transcript is not None:
            stt.seen(event.transcript.remaining_requests, event.transcript.remaining_tokens)
        elif isinstance(event, Synthesizing) and (model := model_of(_key(event))) is not None:
            model.requests += 1
            model.characters += len(speaks[_key(event)].text)
        elif isinstance(event, ClausePlayed) and (model := model_of(_key(event))) is not None:
            model.seen(event.remaining_requests, event.remaining_tokens)
    return tuple(
        ModelUsage(
            model=name,
            requests=each.requests,
            audio_sent_s=each.audio_sent_s,
            billed_s=each.billed_s,
            characters=each.characters,
            cache_hits=each.cache_hits,
            remaining_requests=each.remaining[0],
            remaining_tokens=each.remaining[1],
        )
        for name, each in counts.items()
        if each.requests or each.cache_hits
    )


def _key(event: Synthesizing | ClausePlayed) -> _Clause:
    return (event.reply_id, event.clause)


def _ignored(event: Event) -> None:
    """Where a measured call's public events go: nowhere, since its usage is counted here."""


async def echo_timings(
    clips: Iterable[tuple[AudioClip, LanguageTag]],
    *,
    agent: VoiceAgent,
    settings: VoiceSettings,
    stt: SpeechToText,
    tts: TextToSpeech,
    phrases: PhraseAudio,
    lead_s: float,
    tail_s: float,
) -> AsyncIterator[EchoTiming]:
    """Each clip's echo call, clip by clip: each clip (mono PCM16 at 16 kHz) fed as a fresh call
    of `agent` through the file-fed pipeline at real-time pace, held in its language (the
    session's, as `stt.live_language = "session"` sends it), with `lead_s` of digital silence
    before it and `tail_s` after it, speech-to-text through `stt` and the heard words'
    text-to-speech through `tts`, untraced. The agent's fixed phrases (domain/fixed_phrases.py:
    the greeting, the frame and the notices a call speaks, so a failed turn's notice plays as in
    a call) play from `phrases`, which the caller built before the run as the runtime does, with
    the `stores` facade's `PhraseCache`: so no fixed phrase sends a request here, and what they
    cost run T's budget is the count `PhraseCache.declare(agent)` returned (one for each request
    it packed, none for a phrase its folder held). Each clip's lead starts once the call's
    greeting has played (voice/file_transport.py), so `lead_s` counts from there. The calls are
    one `VoiceCalls`, started before the first clip and closed after the last, or when the
    caller stops iterating and closes the iterator. ValueError, before any call, for a clip at
    another rate than 16 kHz or in a language the agent does not speak."""
    from t2_agentic_voice.voice.file_transport import feed_file  # Pipecat's side, at first use

    clips = list(clips)
    spoken = {language.tag: language for language in agent.languages}
    if any(clip.sample_rate != CLIP_RATE for clip, _ in clips):
        raise ValueError(f"a file-fed call's caller is mono PCM16 at {CLIP_RATE} Hz")
    if unknown := sorted({tag for _, tag in clips} - spoken.keys()):
        raise ValueError(f"the agent speaks no {', '.join(unknown)}: give each clip one of its")
    timed = TimedSpeech(tts)
    calls = VoiceCalls(
        agent=agent,
        settings=settings,
        stt=stt,
        tts=timed,
        phrases=phrases,
        tracing=Tracing(),
        emit=_ignored,
    )
    models = {tag: voice.model for tag, voice in settings.tts.languages.items()}
    await calls.start()
    try:
        for number, (clip, tag) in enumerate(clips):
            timed.takes.clear()
            fed = await feed_file(
                calls,
                clip,
                call_id=f"echo-timings-{number}",
                caller=_CALLER,
                consent=_CONSENT,
                language=spoken[tag],
                lead_s=lead_s,
                tail_s=tail_s,
            )
            yield EchoTiming(
                turns=timing_of(fed, timed.takes),
                usage=usage_of(fed, stt_model=settings.stt.model, tts_models=models),
            )
    finally:
        await calls.aclose()
