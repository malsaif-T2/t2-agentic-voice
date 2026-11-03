"""Audio replayed over a reply through the real turn-taking (the design's 9.5, provisional; plan
005's registration, the arm O): `AudioCall` feeds a clip, mono PCM16 at 16 kHz, into a fresh call
of the file-fed pipeline (voice/file_transport.py) while the agent speaks a reply of the given
clauses, at real-time pace, under `interruptions.mode = "two_step"`, with the speech-to-text the
caller gives (a fake, or a real provider through its port) and a text-to-speech whose reply
outlasts the clip. For each clip it records the overlap's verdict and the part that decided it,
each of its speech-to-text requests, and the time from the clip's labelled word end to the last
agent audio frame sent. Re-exported by the `evals` facade, as `turn_ends` is, since an app
imports only public modules (D-019's Proposed bullet).

Plan 005's Track E builds it; until then each method but the constructor raises.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import InterruptionKind
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.interruptions import OverlapAction, VerdictReason
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech

# Which of a turn's speech-to-text requests one was (voice/session/session_events.py's
# `TranscriptPart`, spelt out for the public signature).
RequestPart = Literal["window", "overlap", "turn"]


class OverlapRequest(BaseModel):
    """One speech-to-text request of the clip's turn, in milliseconds from the clip's start:
    its part, when it went and when its answer came (None when none did), the seconds of audio
    sent, the text heard and the provider's probability that it held no speech."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    part: RequestPart
    sent_ms: float
    answered_ms: float | None = None
    audio_s: float
    text: str | None = None
    no_speech_prob: float | None = None


class OverlapReplay(BaseModel):
    """One clip played over a reply: whether its speech opened an overlap; the verdict that
    decided it (its action, the `Interrupted` kind, the rule's step) and the part whose
    transcript decided it, each None when none did; every speech-to-text request of its turn;
    and, in milliseconds from the clip's start, when the speech detector last heard its speech
    stop, when the last agent audio frame was sent, and from the labelled word end to that last
    frame (`stop_ms`, None with no label or no stop)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    opened: bool
    action: OverlapAction | None = None
    kind: InterruptionKind | None = None
    reason: VerdictReason | None = None
    decided_by: RequestPart | None = None
    requests: tuple[OverlapRequest, ...] = ()
    speech_stop_ms: float | None = None
    last_audio_ms: float | None = None
    stop_ms: float | None = None


class AudioCall:
    """Clips replayed over a reply, each as a fresh call of one runtime of calls, started once
    (`start`) and closed after the last (`aclose`), with `settings` (their `interruptions` and
    `turns` groups among them), `stt` and `tts`."""

    def __init__(self, *, settings: VoiceSettings, stt: SpeechToText, tts: TextToSpeech) -> None:
        self.settings = settings
        self.stt = stt
        self.tts = tts

    async def start(self) -> None:
        """Start the calls' runtime once, before the first clip: the speech detector's and the
        turn analyzer's models warmed."""
        raise NotImplementedError("the audio replay is plan 005's Track E's to build")

    async def over_reply(
        self,
        clip: AudioClip,
        *,
        reply: Sequence[str],
        language: LanguageTag,
        at_s: float,
        tail_s: float,
        word_end_ms: float | None = None,
    ) -> OverlapReplay:
        """Play `clip` `at_s` seconds into a reply of the clauses `reply`, in a call held in
        `language`, with `tail_s` of silence after it, and what came of it; `word_end_ms`, the
        clip's labelled word end, from its start, times the stop. ValueError, before any call,
        for a clip at another rate than 16 kHz."""
        raise NotImplementedError("the audio replay is plan 005's Track E's to build")

    async def aclose(self) -> None:
        """Close the calls' runtime, after the last clip."""
        raise NotImplementedError("the audio replay is plan 005's Track E's to build")
