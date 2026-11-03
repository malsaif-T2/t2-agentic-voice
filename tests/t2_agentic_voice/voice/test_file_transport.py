"""The file-fed transport (voice/file_transport.py): a call whose caller is a clip, through the
same Pipecat modules as a call over WebRTC, with the fakes' detectors and providers."""

from __future__ import annotations

import asyncio

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.voice.file_transport import FedCall, feed_file
from t2_agentic_voice.voice.session.commands import HangUp, Speak
from t2_agentic_voice.voice.session.session_events import (
    ClausePlayed,
    ClauseQueued,
    Connected,
    Ending,
    Synthesizing,
    Transcribed,
    Transcribing,
    TurnClosed,
    TurnOpened,
)

from tests.t2_agentic_voice.fakes import FakeSpeechToText, tone
from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import Built, voice_calls

CALLER, CONSENT = Caller(subject="made-up"), Consent(version=None, record_audio=False)


def _feed(built: Built, clip: AudioClip, *, lead_s: float = 0.4, tail_s: float = 1.5) -> FedCall:
    async def run() -> FedCall:
        await built.calls.start()
        try:
            return await feed_file(
                built.calls,
                clip,
                call_id="call-1",
                caller=CALLER,
                consent=CONSENT,
                language=AGENT.languages[0],
                lead_s=lead_s,
                tail_s=tail_s,
            )
        finally:
            await built.calls.aclose()

    return asyncio.run(asyncio.wait_for(run(), timeout=60))


def test_a_file_fed_call_greets_hears_a_turn_and_says_it_back(settings: VoiceSettings) -> None:
    built = voice_calls(settings, stt=FakeSpeechToText(["hello there"]))
    fed = _feed(built, AudioClip(pcm16=tone(0.8, 16_000)))
    kinds = [type(e) for e in fed.events if type(e).__name__ not in ("CallerAudio", "AgentAudio")]
    assert kinds[0] is Connected and kinds[-1] is Ending
    played = [e for e in fed.events if isinstance(e, ClausePlayed)]
    assert [(e.reply_id, e.clause) for e in played] == [(0, 0), (1, 0)]
    for kind in (TurnOpened, TurnClosed, Transcribing, Transcribed, Synthesizing, ClauseQueued):
        assert kind in kinds
    (heard,) = [e for e in fed.events if isinstance(e, Transcribed)]
    assert heard.transcript is not None and heard.transcript.text == "hello there"
    assert fed.started_at >= played[0].at + 0.4
    assert isinstance(fed.commands[-1][1], HangUp)
    assert [c.text for _, c in fed.commands if isinstance(c, Speak)][-1] == "hello there"
    assert built.tts.calls == [("hello there", "en")] and len(built.stt.calls) == 1
