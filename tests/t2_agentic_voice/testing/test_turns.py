"""Where a call's turns end (testing/turns.py), against a fake `VoiceCalls` and a fake
`feed_file`, so no model loads and no time passes: what `turn_ends` builds its calls with (an
agent, a text-to-speech and phrase audio that say every text as silence of no length, so no
call's output holds an audio frame of its greeting; a speech-to-text that answers at once with
nothing heard), one call a clip with the lead and the tail given, each turn end counted from the
clip's first frame, and the calls started once and closed however the iteration ends. That the
clip's first frame is due `lead_s` after the greeting's `ClausePlayed` is the file-fed
transport's own rule, which Track E's test of `feed_file` holds."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.fixed_phrases import fixed_phrases
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.testing import turns
from t2_agentic_voice.testing.turns import TurnEnd, turn_ends
from t2_agentic_voice.voice import file_transport
from t2_agentic_voice.voice.file_transport import FedCall
from t2_agentic_voice.voice.session.session_events import (
    ClausePlayed,
    Connected,
    SessionEvent,
    TurnClosed,
    TurnOpened,
)

from tests.t2_agentic_voice.testing.feed_support import FakeFeed

SECOND = AudioClip(pcm16=b"\x00\x00" * 16_000)


def _fed(start: float, *events: SessionEvent) -> FedCall:
    return FedCall(started_at=start, events=events, commands=())


@pytest.fixture
def feed(monkeypatch: pytest.MonkeyPatch) -> FakeFeed:
    faked = FakeFeed([])
    monkeypatch.setattr(turns, "VoiceCalls", faked.voice_calls)
    monkeypatch.setattr(file_transport, "feed_file", faked)
    return faked


async def _all(found: AsyncIterator[tuple[TurnEnd, ...]]) -> list[tuple[TurnEnd, ...]]:
    return [ends async for ends in found]


def test_each_clip_is_a_call_whose_turn_ends_count_from_its_first_frame(
    feed: FakeFeed, settings: VoiceSettings
) -> None:
    played = ClausePlayed(reply_id=0, clause=0, at=10.0, audio_s=0.0, chunks=0)
    feed.calls = [
        _fed(
            11.0,
            Connected(at=10.0),
            played,
            TurnOpened(turn_id=0, at=11.6, speech_at=11.3),
            TurnClosed(turn_id=0, at=12.5, speech_ended_at=12.2),
            TurnOpened(turn_id=1, at=13.0, speech_at=12.8),
            TurnClosed(turn_id=1, at=14.25, speech_ended_at=13.5),
        ),
        _fed(50.0, Connected(at=49.0)),
    ]
    found = asyncio.run(
        _all(turn_ends([SECOND, SECOND], settings=settings, lead_s=1.0, tail_s=4.5))
    )
    first, second = found
    assert [(end.speech_stop_ms, end.end_ms) for end in first] == [
        pytest.approx((1200.0, 1500.0)),
        pytest.approx((2500.0, 3250.0)),
    ]
    assert second == ()
    assert [asked["call_id"] for asked in feed.asked] == ["turn-ends-0", "turn-ends-1"]
    for asked in feed.asked:
        assert (asked["clip"], asked["lead_s"], asked["tail_s"]) == (SECOND, 1.0, 4.5)
        assert not asked["consent"].record_audio
    (calls,) = feed.built
    assert (calls.started, calls.closed) == (1, 1)
    assert calls.built["settings"] is settings


def test_the_calls_say_nothing_aloud_and_hear_nothing(
    feed: FakeFeed, settings: VoiceSettings
) -> None:
    """The greeting, and every fixed phrase, is silence of no length, so the greeting has played
    once the call is connected and no output frame holds it; the speech-to-text answers at once
    with nothing heard, so the session says nothing back, and nothing leaves the machine."""
    feed.calls = [_fed(1.0)]
    asyncio.run(_all(turn_ends([SECOND], settings=settings, lead_s=1.0, tail_s=4.5)))
    built = feed.built[0].built
    agent, phrases, tts, stt = built["agent"], built["phrases"], built["tts"], built["stt"]
    for phrase in fixed_phrases(agent):
        assert phrases.audio(phrase.text, language=phrase.language).pcm16 == b""

    async def speech() -> list[bytes]:
        await tts.check_language("en")
        found = [chunk.pcm16 async for chunk in tts.synthesize("anything", language="en")]
        heard = await stt.transcribe(SECOND, language="ar", prompt=None)
        await tts.aclose()
        await stt.aclose()
        return [*found, heard.text.encode()]

    assert asyncio.run(speech()) == [b"", b""]
    assert tts.max_chars("en") is None
    assert feed.asked[0]["language"] == agent.languages[0]


def test_the_calls_close_when_the_caller_stops_early(
    feed: FakeFeed, settings: VoiceSettings
) -> None:
    feed.calls = [_fed(1.0), _fed(2.0)]

    async def first_only() -> None:
        found = turn_ends([SECOND, SECOND], settings=settings, lead_s=1.0, tail_s=4.5)
        assert isinstance(found, AsyncIterator)
        async for _ in found:
            break
        await found.aclose()  # type: ignore[attr-defined]

    asyncio.run(first_only())
    assert len(feed.asked) == 1 and feed.built[0].closed == 1


def test_a_clip_at_another_rate_is_refused_before_any_call(
    feed: FakeFeed, settings: VoiceSettings
) -> None:
    clips = [SECOND, AudioClip(pcm16=b"\x00\x00" * 8_000, sample_rate=8_000)]
    with pytest.raises(ValueError, match="16000 Hz"):
        asyncio.run(_all(turn_ends(clips, settings=settings, lead_s=1.0, tail_s=4.5)))
    assert feed.built == [] and feed.asked == []


def test_a_turn_end_is_plain_data() -> None:
    end = TurnEnd(speech_stop_ms=800.0, end_ms=1000.0)
    assert end.model_dump() == {"speech_stop_ms": 800.0, "end_ms": 1000.0}
    with pytest.raises(ValueError, match="frozen"):
        end.end_ms = 2.0  # type: ignore[misc]
