"""Where a call's turns end, measured on the file-fed pipeline: `turn_ends`, which `poe eot` runs
over the golden set's paused requests (plan 003's registration, E), provisional, re-exported by
the `evals` facade since an app imports only public modules (plan 003's decision log).

Each clip is fed as a fresh call of one `VoiceCalls`, started once: its start warms one Silero
VAD and one Smart Turn v3.2, and each call builds its own speech detector and turn analyzer
from the settings' `turns` group, since each keeps one stream's state (voice/calls.py, which
wins over this module's first words, that the models load once for every clip: plan 003's
decision log, 2026-11-03). No request leaves the machine: the call's agent, its text-to-speech,
its phrase audio and its speech-to-text are testing's own. The speech-to-text answers at once
with nothing heard, so the transcript adds no time and the session says nothing back (an empty
transcript is said back as nothing); the text-to-speech and the phrase audio say every text as
silence of no length, so the greeting has played once the call is connected, and each clip's
lead starts there (voice/file_transport.py's rule, unchanged). A greeting would move no turn
end, which the speech detector and the turn analyzer find in the caller's audio alone, never in
a file-fed call's captured output; taking the phrase cache's audio, as `echo_timings` does,
would make `poe eot`, an offline run with no spend, synthesize the greeting.

Each turn end is given in milliseconds from the clip's first frame (`FedCall.started_at`, the
silence fed before it left out), on the call's clock, `time.perf_counter`; Pipecat's own steps
have about 16 ms resolution on Windows under Python 3.12, and Smart Turn stalls the audio 100 to
163 ms at each speech stop (plan 003's appendix, "Changes to the plan's interfaces", item 23).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import Event
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, DataFlow, Transcript
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.file_transport import RATE
from t2_agentic_voice.voice.session.session_events import TurnClosed

# The speech detector's rate, the only one a file-fed call's caller is given in: the file-fed
# transport's (voice/file_transport.py's `RATE`).
CLIP_RATE = RATE
# The rate of the silence testing's text-to-speech and phrase audio say: the pipeline's output
# rate, which an empty chunk never plays at.
_SILENCE_RATE = 24_000
_FLOW = DataFlow(
    provider="none", processed_in="this process", stored_in="nowhere", retention="none"
)
# A call held in one language, whichever: the speech detector and the turn analyzer hear no
# language, and nothing is said back.
_AGENT = VoiceAgent(name="turn-ends", languages=[Language.english(greeting="Welcome.")])
_CALLER = Caller(subject="turn-ends")
_CONSENT = Consent(version=None, record_audio=False)


class TurnEnd(BaseModel):
    """One turn's end in a file-fed call, in milliseconds from the clip's start (the silence fed
    before it left out): when the speech detector last heard the speech stop before it, and when
    the turn analyzer ended the turn."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    speech_stop_ms: float
    end_ms: float


class HearsNothing:
    """A speech-to-text that answers at once, with nothing heard, and sends nothing."""

    name = "none"
    data_flow = _FLOW

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        return Transcript(text="", language=language, billed_seconds=0.0)

    async def aclose(self) -> None:
        """Nothing is held open."""


class SaysSilence:
    """A text-to-speech, and the phrase audio, that say every text as silence of no length."""

    name = "none"
    data_flow = _FLOW

    def max_chars(self, language: str) -> int | None:
        return None

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        yield self.audio(text, language="en")

    async def check_language(self, language: str) -> None:
        """Every language is spoken, as silence."""

    async def aclose(self) -> None:
        """Nothing is held open."""

    def audio(self, text: str, *, language: LanguageTag) -> AudioChunk:
        return AudioChunk(pcm16=b"", sample_rate=_SILENCE_RATE)


def _ignored(event: Event) -> None:
    """Where a measured call's public events go: nowhere, since only its turn ends count."""


async def turn_ends(
    clips: Iterable[AudioClip], *, settings: VoiceSettings, lead_s: float, tail_s: float
) -> AsyncIterator[tuple[TurnEnd, ...]]:
    """Each clip's turn ends, clip by clip, in the order the turn analyzer ended them: each clip
    (mono PCM16 at 16 kHz) fed as a fresh call through the file-fed pipeline at real-time pace,
    with `settings`' turn settings, `lead_s` of digital silence before it and `tail_s` after it,
    and a speech-to-text that answers at once, so the transcript adds no time. The calls are
    one `VoiceCalls`, started before the first clip and closed after the last, or when the
    caller stops iterating and closes the iterator. ValueError, before any call, for a clip at
    another rate."""
    from t2_agentic_voice.voice.file_transport import feed_file  # Pipecat's side, at first use

    clips = list(clips)
    if any(clip.sample_rate != CLIP_RATE for clip in clips):
        raise ValueError(f"a file-fed call's caller is mono PCM16 at {CLIP_RATE} Hz")
    silence = SaysSilence()
    calls = VoiceCalls(
        agent=_AGENT,
        settings=settings,
        stt=HearsNothing(),
        tts=silence,
        phrases=silence,
        tracing=Tracing(),
        emit=_ignored,
    )
    await calls.start()
    try:
        for number, clip in enumerate(clips):
            fed = await feed_file(
                calls,
                clip,
                call_id=f"turn-ends-{number}",
                caller=_CALLER,
                consent=_CONSENT,
                language=_AGENT.languages[0],
                lead_s=lead_s,
                tail_s=tail_s,
            )
            start = fed.started_at
            yield tuple(
                TurnEnd(
                    speech_stop_ms=(event.speech_ended_at - start) * 1000,
                    end_ms=(event.at - start) * 1000,
                )
                for event in fed.events
                if isinstance(event, TurnClosed)
            )
    finally:
        await calls.aclose()
