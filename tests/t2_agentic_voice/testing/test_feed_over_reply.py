"""The file-fed transport's clip over a reply (voice/file_transport.py's `over_reply`, the audio
replay's: testing/audio_call.py), through the same Pipecat modules as a call, with the fakes'
detectors and providers: the clip's first frame is due its lead after the greeting's first audio
was queued, while the greeting still plays, and each event's handing time lies between the
commands the session gave for the one before it and those it gave for it."""

from __future__ import annotations

import asyncio

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.voice.file_transport import FedCall, feed_file
from t2_agentic_voice.voice.session.commands import Speak
from t2_agentic_voice.voice.session.session_events import ClausePlayed, ClauseQueued, Connected

from tests.t2_agentic_voice.fakes import FakeSpeechToText, tone
from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import voice_calls

CALLER, CONSENT = Caller(subject="made-up"), Consent(version=None, record_audio=False)
GREETING_S = 2.5  # the fake phrase audio's greeting: long enough for the clip to start over it


def _over(settings: VoiceSettings, *, lead_s: float) -> FedCall:
    built = voice_calls(settings, stt=FakeSpeechToText(["made-up words"]))
    built.phrases.seconds = GREETING_S

    async def run() -> FedCall:
        await built.calls.start()
        try:
            return await feed_file(
                built.calls,
                AudioClip(pcm16=tone(0.4, 16_000)),
                call_id="call-over",
                caller=CALLER,
                consent=CONSENT,
                language=AGENT.languages[0],
                lead_s=lead_s,
                tail_s=2.5,
                over_reply=True,
            )
        finally:
            await built.calls.aclose()

    return asyncio.run(asyncio.wait_for(run(), timeout=60))


def test_a_clip_over_the_reply_starts_its_lead_after_the_greetings_first_audio(
    settings: VoiceSettings,
) -> None:
    fed = _over(settings, lead_s=0.5)
    queued = next(e for e in fed.events if isinstance(e, ClauseQueued) and e.reply_id == 0)
    played = next(e for e in fed.events if isinstance(e, ClausePlayed) and e.reply_id == 0)
    assert queued.at + 0.5 <= fed.started_at < played.at  # the clip lies over the greeting
    assert fed.started_at - (queued.at + 0.5) < 0.2  # its lead counts from the event's time


def test_each_event_is_handed_between_the_commands_of_the_one_before_and_its_own(
    settings: VoiceSettings,
) -> None:
    fed = _over(settings, lead_s=0.3)
    assert len(fed.handed_at) == len(fed.events) and list(fed.handed_at) == sorted(fed.handed_at)
    connected = next(i for i, e in enumerate(fed.events) if isinstance(e, Connected))
    greeting = next(at for at, c in fed.commands if isinstance(c, Speak) and c.reply_id == 0)
    assert fed.handed_at[connected] <= greeting < fed.handed_at[connected + 1]
    assert all(e.at <= at for e, at in zip(fed.events, fed.handed_at, strict=True))
