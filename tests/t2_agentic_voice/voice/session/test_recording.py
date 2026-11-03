"""The call's recorder (voice/session/recording.py; docs/SECURITY.md, invariant 8): it writes
nothing with `privacy.record_audio` off, with the token's consent false, with both, under the dev
identity's consent with the setting on, or with a consent no verified token sealed (a plain
`Consent` that says `record_audio`, a copy of a verified one), and no client message changes
that; with the setting on and a verified consent that allows it, the caller's track, the agent's
audio and the timeline are kept under `var_dir/recordings/<call ID>/`, the tracks lined up on
the call's clock; and a disk that fails stops the recording, never the call."""

from __future__ import annotations

import asyncio
import copy
import json
import threading
import wave
from collections.abc import Callable
from pathlib import Path

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Consent
from t2_agentic_voice.core.settings.privacy import PrivacySettings
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.voice.session.recording import AGENT_TRACK, CALLER_TRACK, RECORDINGS, TIMELINE

from tests.t2_agentic_voice.core.consent_support import verified
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import HEARD, call, turn

ON = PrivacySettings(record_audio=True)


def _recorded(settings: VoiceSettings, consent: Consent) -> FakeSessionIO:
    """A call of a greeting and one echoed turn, with both taps flowing and every client
    message the protocol has, and a stop; its I/O once its stream has ended."""
    io, _ = call(settings, consent=consent)

    async def drive() -> None:
        await io.connected()
        await io.caller_audio(0.5)
        await io.clause_queued(0, 0)
        await io.agent_audio(0.5)
        await io.clause_played(0, 0, audio_s=0.5)
        await io.client({"v": 1, "type": "hello", "client": "t2v-client.js/1.0.0"})
        await io.client({"v": 1, "type": "client_stats", "candidate_type": "host"})
        await io.client({"v": 1, "type": "playback", "reply_id": 0, "clause": 0, "event": "ended"})
        await io.clock.advance(1.0)
        await io.caller_audio(1.0)
        await turn(io, 0, HEARD)
        await io.clause_queued(1, 0)
        await io.agent_audio(0.2, sample_rate=16_000)  # not the track's rate: left out
        await io.agent_audio(0.3)
        await io.client({"v": 1, "type": "stop"})
        await io.ending()
        await io.close()

    asyncio.run(drive())
    return io


CONSENTS: dict[str, tuple[bool, Callable[[], Consent]]] = {
    "setting-off": (False, lambda: verified(record_audio=True)),
    "consent-false": (True, lambda: verified(record_audio=False)),
    "both": (False, lambda: verified(record_audio=False)),
    "dev-identity": (True, lambda: Consent(version=None, record_audio=False)),
    "plain-consent-true": (True, lambda: Consent(version="v1", record_audio=True)),
}


@pytest.mark.parametrize(("setting", "consent"), CONSENTS.values(), ids=CONSENTS.keys())
def test_nothing_is_recorded_unless_the_setting_and_a_signed_consent_allow_it(
    settings: VoiceSettings, setting: bool, consent: Callable[[], Consent]
) -> None:
    privacy = PrivacySettings(record_audio=setting)
    _recorded(settings.model_copy(update={"privacy": privacy}), consent())
    assert not (settings.storage.var_dir / RECORDINGS).exists()


@pytest.mark.parametrize("copied", [copy.copy, Consent.model_copy], ids=["copy", "model_copy"])
def test_a_copy_of_a_verified_consent_keeps_nothing_while_the_consent_itself_keeps_the_audio(
    settings: VoiceSettings, copied: Callable[[Consent], Consent]
) -> None:
    original = verified(record_audio=True)
    on = settings.model_copy(update={"privacy": ON})
    _recorded(on, copied(original))
    assert not (settings.storage.var_dir / RECORDINGS).exists()
    _recorded(on, original)
    assert (settings.storage.var_dir / RECORDINGS / "call-1" / CALLER_TRACK).is_file()


def test_with_the_setting_on_and_a_verified_consent_the_call_is_kept_lined_up(
    settings: VoiceSettings,
) -> None:
    """The caller's track at 16 kHz and the agent's at the output rate, each padded with
    silence to where its audio came on the call's clock, and a timeline of the call's steps,
    each at its second from the call's start."""
    consent = verified(record_audio=True)
    io = _recorded(settings.model_copy(update={"privacy": ON}), consent)
    folder = settings.storage.var_dir / RECORDINGS / "call-1"
    with wave.open(str(folder / CALLER_TRACK)) as caller:
        assert (caller.getframerate(), caller.getnchannels(), caller.getsampwidth()) == (
            16_000,
            1,
            2,
        )
        caller_s = caller.getnframes() / caller.getframerate()
    with wave.open(str(folder / AGENT_TRACK)) as agent:
        assert agent.getframerate() == 24_000
        agent_s = agent.getnframes() / agent.getframerate()
    lines = [
        json.loads(line) for line in (folder / TIMELINE).read_text(encoding="utf-8").splitlines()
    ]
    events = [line["event"] for line in lines]
    assert events[0] == "start" and lines[0]["consent"] == "v1" and events[-1] == "ended"
    for kind in ("clause_asked", "clause_queued", "clause_played", "turn_opened", "turn_closed"):
        assert kind in events
    assert {"heard", "playback", "stop", "stopped"} <= set(events)
    heard = next(line for line in lines if line["event"] == "heard")
    assert (heard["text"], heard["dropped"]) == (HEARD, False)
    asked = [line["text"] for line in lines if line["event"] == "clause_asked"]
    assert asked[0] == io.setup.language.greeting
    started = next(line["t"] for line in lines if line["event"] == "turn_opened")
    caller_audio = [e for e in io.events if type(e).__name__ == "CallerAudio"]
    assert caller_s == pytest.approx(caller_audio[-1].at - io.events[0].at + 1.0, abs=0.01)
    agent_audio = [e for e in io.events if type(e).__name__ == "AgentAudio"]
    assert agent_s == pytest.approx(agent_audio[-1].at - io.events[0].at + 0.3, abs=0.01)
    assert started > 0


def test_a_recording_the_disk_refuses_stops_and_the_call_goes_on(
    settings: VoiceSettings, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocked = tmp_path / "a-file"
    blocked.write_text("", encoding="utf-8")
    storage = StorageSettings(var_dir=blocked)
    on = settings.model_copy(update={"privacy": ON, "storage": storage})
    io = _recorded(on, verified(record_audio=True))
    assert io.commands.commands and "recording_failed" in [r.getMessage() for r in caplog.records]


def _recorders() -> list[str]:
    return [t.name for t in threading.enumerate() if t.name == "t2v-recorder" and t.is_alive()]


def test_the_recorders_thread_ends_with_the_call_whatever_ended_it(
    settings: VoiceSettings,
) -> None:
    """A recorded call leaves no thread behind: one that ended, and one whose stream ended with
    no end (the session then marks the end itself, after its recording closed)."""
    on = settings.model_copy(update={"privacy": ON})
    _recorded(on, verified(record_audio=True))
    assert _recorders() == []
    consent = verified(record_audio=True)
    io, session = call(on, consent=consent, call_id="call-2")

    async def drive() -> None:
        await io.connected()
        await io.caller_audio(0.2)
        await session.aclose()

    asyncio.run(drive())
    assert _recorders() == []
    timeline = settings.storage.var_dir / RECORDINGS / "call-2" / TIMELINE
    assert "ended" not in timeline.read_text(encoding="utf-8")
