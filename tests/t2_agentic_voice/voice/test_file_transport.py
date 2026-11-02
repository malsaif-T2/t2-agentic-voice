"""The file-fed transport (voice/file_transport.py). Plan 003's Track E builds it and replaces this
file's stub test with its own (60 s of frames within 100 ms of real time)."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.domain.declaration import Language
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.file_transport import FedCall, feed_file
from t2_agentic_voice.voice.session.commands import HangUp
from t2_agentic_voice.voice.session.session_events import Connected


def test_the_file_fed_transport_is_a_stub_until_track_e() -> None:
    with pytest.raises(NotImplementedError, match="Track E"):
        asyncio.run(
            feed_file(
                VoiceCalls.__new__(VoiceCalls),
                AudioClip(pcm16=b"\x00\x00" * 16_000),
                call_id="call-1",
                caller=Caller(subject="made-up"),
                consent=Consent(version=None, record_audio=False),
                language=Language.english(greeting="Hello there."),
                lead_s=1.0,
                tail_s=4.5,
            )
        )
    hung_up = (7.5, HangUp(reason="caller_left"))  # each command with when it was given
    done = FedCall(started_at=1.0, events=(Connected(at=0.5),), commands=(hung_up,))
    assert (done.events[0].at, done.commands[-1]) == (0.5, hung_up)
