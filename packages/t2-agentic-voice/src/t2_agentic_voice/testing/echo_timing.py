"""The time of each step of an echo call, measured on the file-fed pipeline: `echo_timings`, which
runs T1 and T2 use over the golden set's paused requests (plan 003's registration, T),
provisional, re-exported by the `evals` facade since an app imports only public modules (plan
003's decision log), with the phrase audio it takes (`PhraseAudio`). Built by plan 003's Track H,
which settles its fields; until then a stub.

Each step is timed on `time.perf_counter`; Pipecat's own steps have about 16 ms resolution on
Windows under Python 3.12, and Smart Turn stalls the audio 100 to 163 ms at each speech stop
(plan 003's appendix, "Changes to the plan's interfaces", item 23).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import ModelUsage
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.session.io import PhraseAudio

_STUB = "echo_timings is built by plan 003's Track H"


class TurnTiming(BaseModel):
    """When each step of one turn of a file-fed echo call happened, in milliseconds from the
    clip's start, each None when it did not: the speech detector's last stop before the turn's
    end; the turn's end; the speech-to-text request sent and answered; the cached frame's first
    audio sent; the heard words' text-to-speech request sent, its first audio, and its first
    sound above the noise floor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    speech_stop_ms: float | None = None
    end_ms: float | None = None
    stt_sent_ms: float | None = None
    stt_answered_ms: float | None = None
    frame_audio_ms: float | None = None
    tts_sent_ms: float | None = None
    tts_first_audio_ms: float | None = None
    heard_sound_ms: float | None = None


class EchoTiming(BaseModel):
    """One file-fed echo call: each of its turns' timings, and each model's usage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    turns: tuple[TurnTiming, ...]
    usage: tuple[ModelUsage, ...]


def echo_timings(
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
    """Each clip's echo call, clip by clip: each clip fed as a fresh call of `agent` through the
    file-fed pipeline at real-time pace, held in its language (the session's, as
    `stt.live_language = "session"` sends it), with `lead_s` of digital silence before it and
    `tail_s` after it, speech-to-text through `stt` and the heard words' text-to-speech through
    `tts`; the models loaded once for every clip. The agent's fixed phrases
    (domain/fixed_phrases.py: the greeting, the frame and the notices a call speaks, so a failed
    turn's notice plays as in a call) play from `phrases`, which the caller built before the run
    as the runtime does, with the `stores` facade's `PhraseCache`: so no fixed phrase sends a
    request here, and what they cost run T's budget is the count `PhraseCache.declare(agent)`
    returned (one for each request it packed, none for a phrase its folder held). Each clip's
    lead starts once the call's greeting has played (voice/file_transport.py), so `lead_s`
    counts from there. Track H's test: with a fake `PhraseAudio`, echo_timings sends `tts` no
    request for a fixed phrase."""
    raise NotImplementedError(_STUB)
