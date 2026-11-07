"""Run T's replay (first_audio_run.py's `Replay`; plan 006's registration, T) wired to the library:
each recording replayed as one call of the agent by the `evals` facade's `AudioCall`, its talker
writing with the run's chat model, said as a turn `lead_s` after the agent's own greeting in the
call's language has played (`AudioCall.turn`), and what the call gave back read into the run's
`ReplayedCall` (`replayed`).

- **The times** are the turn's: from the owner's marked end of speech where the recording has one
  (`TurnReplay.ttfa_ms`, `progress_ms`), else from the speech detector's stop less its delay, as
  the call report times every turn (its `TurnTimes`), to the first audible frame of the reply and
  of a progress line (Q18: both kinds of start, read together by the targets).
- **The turns** are the call report's that the talker answered: not dropped (said over the
  greeting), with words heard. Whether a tool ran in a reply is its `ToolStarted`; its failure
  the first `ProviderFailed` of its turn; its opening the turn's `TurnReplay.opening`, the
  first seconds of the reply's audio as sent, for the owner's listen (`poe first-audio-listen`).
- **The usage** is the call report's, the chat model's apart (`ChatSpend`, with its tokens and
  the headroom its provider last reported); and the voice's every request, counted as it goes
  (`CountedVoice`): the session's, which the report counts, and the replay's own, the greeting it
  says before each call and the progress lines it says once at the start, which it does not.
- **A failed call** is one turn of its failure (`failed`), never an error out of the run: the
  greeting's request the voice failed (its `ProviderError` kind, so run T replays a
  `rate_limited` one), or the call whose greeting never played (`GREETING_NOT_PLAYED`); what it
  used counted all the same.

The phrase cache a run declares (`phrases`) is not the replay's: `AudioCall` says the greeting
and the progress lines itself and every other fixed phrase as silence, so a reply's time is the
talker's and the voice's alone.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import datetime
from typing import Final

from t2_agentic_voice import ProviderError, T2VoiceError, VoiceAgent, VoiceSettings
from t2_agentic_voice.evals import AudioCall, TurnReplay
from t2_agentic_voice.events import (
    CallEnded,
    CallReport,
    Event,
    ModelUsage,
    ProviderFailed,
    ToolStarted,
)
from t2_agentic_voice.ports import AudioChunk, AudioClip, ChatModel, SpeechToText, TextToSpeech

from ole5_voice.evals.first_audio_score import ChatSpend, ReplayedCall, ReplayedTurn
from ole5_voice.evals.timing_run import Tag

# A call's failure when its greeting never played (the file-fed transport's T2VoiceError).
GREETING_NOT_PLAYED: Final = "greeting_not_played"


class CountedVoice:
    """The replay's text-to-speech: `inner`, each request counted by its language's voice
    (`models`, by tag) as it goes, its characters too; a `TextToSpeech`."""

    def __init__(self, inner: TextToSpeech, models: Mapping[str, str]) -> None:
        self.inner, self.models = inner, models
        self.name, self.data_flow = inner.name, inner.data_flow
        self.requests: Counter[str] = Counter()
        self.characters: Counter[str] = Counter()

    def max_chars(self, language: str) -> int | None:
        return self.inner.max_chars(language)

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        model = self.models.get(language, language)
        self.requests[model] += 1
        self.characters[model] += len(text)
        async for chunk in self.inner.synthesize(text, language=language):
            yield chunk

    async def check_language(self, language: str) -> datetime | None:
        return await self.inner.check_language(language)

    async def aclose(self) -> None:
        """Nothing of its own: the run closes the voice it was given."""

    def taken(self) -> dict[str, tuple[int, int]]:
        """Each voice's requests and characters since the last time they were taken."""
        found = {m: (self.requests[m], self.characters[m]) for m in self.requests}
        self.requests.clear()
        self.characters.clear()
        return found


class AudioReplay:
    """The replay of a run's recordings, each a fresh call of `agent` (the module's
    docstring); `audio_call` stands in for the library's in a test."""

    def __init__(
        self,
        *,
        agent: VoiceAgent,
        settings: VoiceSettings,
        stt: SpeechToText,
        tts: TextToSpeech,
        llm: ChatModel,
        audio_call: type[AudioCall] = AudioCall,
    ) -> None:
        self.agent, self.settings = agent, settings
        models: dict[str, str] = {t: v.model for t, v in settings.tts.languages.items()}
        self.voice = CountedVoice(tts, models)
        self.call_of = audio_call(settings=settings, stt=stt, tts=self.voice, agent=agent, chat=llm)

    async def start(self) -> None:
        await self.call_of.start()

    async def call(
        self,
        clip: AudioClip,
        *,
        language: Tag,
        end_ms: float | None,
        lead_s: float,
        tail_s: float,
    ) -> ReplayedCall:
        """`clip` replayed as a turn after the agent's greeting in `language`; a call that
        failed as one turn of its failure (the module's docstring)."""
        greeting = next(each.greeting for each in self.agent.languages if each.tag == language)
        chat_model = self.settings.llm.model
        try:
            replay = await self.call_of.turn(
                clip,
                greeting=(greeting,),
                language=language,
                lead_s=lead_s,
                tail_s=tail_s,
                speech_end_ms=end_ms,
            )
        except ProviderError as error:  # the greeting's request, before the call: none emitted
            return failed(error.kind, (), chat_model=chat_model, voice=self.voice.taken())
        except T2VoiceError as error:
            if type(error) is not T2VoiceError:  # a setting, a request: no failure of the call
                raise
            emitted, voice = self.call_of.emitted, self.voice.taken()
            return failed(GREETING_NOT_PLAYED, emitted, chat_model=chat_model, voice=voice)
        return replayed(
            replay,
            self.call_of.emitted,
            chat_model=chat_model,
            voice=self.voice.taken(),
            labelled=end_ms is not None,
        )

    async def aclose(self) -> None:
        await self.call_of.aclose()


def audio_replay(
    *,
    agent: VoiceAgent,
    settings: VoiceSettings,
    stt: SpeechToText,
    tts: TextToSpeech,
    llm: ChatModel,
    phrases: object = None,
) -> AudioReplay:
    """Run T's replay (first_audio_setup.py's `FirstAudioParts.replay`); `phrases`, the run's
    phrase cache, is not the replay's (the module's docstring)."""
    return AudioReplay(agent=agent, settings=settings, stt=stt, tts=tts, llm=llm)


def replayed(
    replay: TurnReplay,
    emitted: Sequence[Event],
    *,
    chat_model: str,
    voice: Mapping[str, tuple[int, int]],
    labelled: bool,
) -> ReplayedCall:
    """What one call gave back, as run T reads it (the module's docstring): `voice` holds each
    voice's requests and characters the replay counted during it, and `labelled` whether its
    recording has the owner's marked end."""
    report = next((e.report for e in emitted if isinstance(e, CallEnded)), None)
    records = [] if report is None else [t for t in report.turns if not t.dropped and t.heard]
    searched = {e.turn_id for e in emitted if isinstance(e, ToolStarted)}
    failures: dict[int | None, str] = {}
    for event in emitted:
        if isinstance(event, ProviderFailed):
            failures.setdefault(event.turn_id, event.kind)
    turns, openings = [], []
    for record in records:
        first = record.turn_id == 0
        ttfa, progress = record.times.ttfa_ms, record.times.progress_ms
        if first and labelled:  # the owner's marked end, not the detector's stop
            ttfa, progress = replay.ttfa_ms, replay.progress_ms
        turns.append(
            ReplayedTurn(
                ttfa_ms=ttfa,
                searched=record.turn_id in searched,
                progress_ms=progress,
                failure=failures.get(record.turn_id),
            )
        )
        openings.append(replay.opening if first else None)
    usage, chat = _spent(report, chat_model=chat_model, voice=voice)
    return ReplayedCall(turns=tuple(turns), openings=tuple(openings), usage=usage, chat=chat)


def failed(
    kind: str,
    emitted: Sequence[Event],
    *,
    chat_model: str,
    voice: Mapping[str, tuple[int, int]],
) -> ReplayedCall:
    """A call that failed (the module's docstring): one turn of `kind`, no opening, and what
    it used, its report's where `emitted` holds one and the voice's requests (`replayed`)."""
    report = next((e.report for e in emitted if isinstance(e, CallEnded)), None)
    usage, chat = _spent(report, chat_model=chat_model, voice=voice)
    return ReplayedCall(
        turns=(ReplayedTurn(failure=kind),), openings=(None,), usage=usage, chat=chat
    )


def _spent(
    report: CallReport | None, *, chat_model: str, voice: Mapping[str, tuple[int, int]]
) -> tuple[tuple[ModelUsage, ...], ChatSpend]:
    """A call's speech usage, the voice's requests its report did not count added, and its
    chat model's."""
    usage = [] if report is None else list(report.usage)
    chat = next((u for u in usage if u.model == chat_model), ModelUsage(model=chat_model))
    speech = [u for u in usage if u.model != chat_model]
    reported = {u.model: (u.requests, u.characters) for u in speech}
    for model, (requests, characters) in voice.items():
        sent, said = reported.get(model, (0, 0))
        if requests > sent:  # the replay's own: the greeting, the progress lines at the start
            extra = ModelUsage(
                model=model, requests=requests - sent, characters=max(characters - said, 0)
            )
            speech.append(extra)
    spend = ChatSpend(
        requests=chat.requests,
        input_tokens=chat.input_tokens,
        cached_tokens=chat.cached_tokens,
        output_tokens=chat.output_tokens,
        remaining_requests=chat.remaining_requests,
    )
    return tuple(speech), spend
