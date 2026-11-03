"""Audio replayed over a reply through the real turn-taking (the design's 9.5, provisional; plan
005's registration, the arm O): `AudioCall` feeds a clip, mono PCM16 at 16 kHz, into a fresh call
of the file-fed pipeline (voice/file_transport.py) while the agent speaks a reply of the given
clauses, at real-time pace, under the settings' interruption rule (`interruptions.mode =
"two_step"` opens an overlap; under `drop` none opens, and the replay says so), with the
speech-to-text the caller gives (a fake, or a real provider through its port) and a
text-to-speech whose reply outlasts the clip. For each clip it records the overlap's verdict and
the part that decided it, each of its speech-to-text requests, and the time from the clip's
labelled word end to the last agent audio frame sent (overlap_replay.py reads them from the
call). Re-exported by the `evals` facade, as `turn_ends` is, since an app imports only public
modules (D-019's Proposed bullet).

The reply is the call's greeting, so the session speaks it with no reach into its internals: the
agent the replay builds (as testing/turns.py builds its own) greets, in the clip's language,
with the reply's clauses as one phrase, whose audio the replay supplies, the caller's
text-to-speech saying that phrase once before the call (so its length is the reply's); every
other fixed phrase (the echo's frame, a notice) is silence of no length. The file-fed transport
feeds the clip `at_s` after the greeting's first audio was queued (`over_reply`), not after it
played, so the clip lies over the reply, with `tail_s` of silence after it. Each clip is a fresh
call of one `VoiceCalls`, started once, untraced and never recorded, whose public events go
nowhere but its `Interrupted`, which the replay reads.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.events import Event, Interrupted
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech
from t2_agentic_voice.testing.overlap_replay import (
    OverlapReplay,
    OverlapRequest,
    RequestPart,
    replay_of,
)
from t2_agentic_voice.testing.turns import CLIP_RATE
from t2_agentic_voice.voice.calls import VoiceCalls

__all__ = ["AudioCall", "OverlapReplay", "OverlapRequest", "RequestPart"]

# The rate of the silence the replay's other fixed phrases say: the pipeline's output rate,
# which an empty chunk never plays at.
_SILENCE_RATE = 24_000
# The presets a replayed call's language is built from, by its tag; and the agent the replay
# calls, whose own greetings no call speaks, each call being held in its clip's language and
# greeting with the reply.
_PRESETS: dict[LanguageTag, Callable[..., Language]] = {
    "ar-SA": Language.saudi_arabic,
    "ar": Language.arabic,
    "en": Language.english,
}
_AGENT = VoiceAgent(
    name="audio-call", languages=[preset(greeting="Replay.") for preset in _PRESETS.values()]
)
_CALLER = Caller(subject="audio-call")
_CONSENT = Consent(version=None, record_audio=False)


class _ReplyAudio:
    """The replay's phrase audio (voice's `PhraseAudio`): the reply's, for the greeting of the
    call in progress (`reply`: its text, its language's tag and its audio); any other phrase as
    silence of no length."""

    def __init__(self) -> None:
        self.reply: tuple[str, LanguageTag, AudioChunk] | None = None

    def audio(self, text: str, *, language: LanguageTag) -> AudioChunk:
        if self.reply is not None and self.reply[:2] == (text, language):
            return self.reply[2]
        return AudioChunk(pcm16=b"", sample_rate=_SILENCE_RATE)


class AudioCall:
    """Clips replayed over a reply, each as a fresh call of one runtime of calls, started once
    (`start`) and closed after the last (`aclose`), with `settings` (their `interruptions` and
    `turns` groups among them), `stt` and `tts`, neither of which it closes."""

    def __init__(self, *, settings: VoiceSettings, stt: SpeechToText, tts: TextToSpeech) -> None:
        self.settings = settings
        self.stt = stt
        self.tts = tts
        self._phrases = _ReplyAudio()
        self._interrupted: list[Interrupted] = []
        self._calls: VoiceCalls | None = None
        self._count = 0

    def _emit(self, event: Event) -> None:
        """Where a replayed call's public events go: its `Interrupted` kept, the rest nowhere."""
        if isinstance(event, Interrupted):
            self._interrupted.append(event)

    async def start(self) -> None:
        """Start the calls' runtime once, before the first clip: the speech detector's and the
        turn analyzer's models warmed."""
        self._calls = VoiceCalls(
            agent=_AGENT,
            settings=self.settings,
            stt=self.stt,
            tts=self.tts,
            phrases=self._phrases,
            tracing=Tracing(),
            emit=self._emit,
        )
        await self._calls.start()

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
        for a clip at another rate than 16 kHz or a reply a greeting cannot say (nothing, or a
        character a phrase may not hold); RuntimeError before `start`."""
        from t2_agentic_voice.voice.file_transport import feed_file  # Pipecat's side, at first use

        if clip.sample_rate != CLIP_RATE:
            raise ValueError(f"a replayed clip is mono PCM16 at {CLIP_RATE} Hz")
        text = " ".join(reply)
        try:
            spoken = _PRESETS[language](greeting=text)
        except ConfigurationError:
            raise ValueError("the reply is no phrase a greeting may say") from None
        if self._calls is None:
            raise RuntimeError("A clip came before start(). FIX: start the replay first.")
        self._phrases.reply = (text, language, await self._said(text, language))
        call_id = f"audio-call-{self._count}"
        self._count += 1
        self._interrupted.clear()
        fed = await feed_file(
            self._calls,
            clip,
            call_id=call_id,
            caller=_CALLER,
            consent=_CONSENT,
            language=spoken,
            lead_s=at_s,
            tail_s=tail_s,
            over_reply=True,
        )
        heard = [event for event in self._interrupted if event.call_id == call_id]
        return replay_of(fed, heard, word_end_ms=word_end_ms)

    async def _said(self, text: str, language: LanguageTag) -> AudioChunk:
        """`text` as the replay's text-to-speech says it in `language`, its chunks joined;
        ValueError when it says nothing, or not at one rate."""
        chunks = [chunk async for chunk in self.tts.synthesize(text, language=language)]
        rates = {chunk.sample_rate for chunk in chunks if chunk.pcm16}
        if len(rates) != 1:
            raise ValueError("the replay's text-to-speech said the reply at no one rate")
        return AudioChunk(pcm16=b"".join(c.pcm16 for c in chunks), sample_rate=rates.pop())

    async def aclose(self) -> None:
        """Close the calls' runtime, after the last clip."""
        if self._calls is not None:
            await self._calls.aclose()
            self._calls = None
