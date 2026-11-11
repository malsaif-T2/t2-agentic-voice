"""The text-to-speech bridge's held clauses (voice/tts_bridge.py, plan 007): with a text-to-speech
that holds speech (`HeldSpeech`, the clause cache), a clause whose take it holds plays from it,
as a fixed phrase plays, with no request; a miss is requested as today; a stop that lands while a
take is read drops the clause unplayed; and a text-to-speech that holds none gives today's events
in today's order (GP-18). The rig is test_tts_bridge.py's."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, HeldSpeech
from t2_agentic_voice.voice.session.commands import StopSpeaking
from t2_agentic_voice.voice.session.session_events import (
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Synthesizing,
)

from tests.t2_agentic_voice.fakes import FakeTextToSpeech, tone
from tests.t2_agentic_voice.voice.kit import until
from tests.t2_agentic_voice.voice.test_tts_bridge import SECOND, Rig, _run, _speak

HELD = "A clause said before."
TAKE = AudioChunk(pcm16=tone(0.5, 24_000), sample_rate=24_000)


class _Held(FakeTextToSpeech):
    """The fakes' text-to-speech holding `takes` by text (a `HeldSpeech`), each look-up kept
    in `asked`, and `during` awaited while one is read."""

    def __init__(self, takes: dict[str, AudioChunk], **options: Any) -> None:
        super().__init__(**options)
        self.takes = takes
        self.asked: list[tuple[str, str]] = []
        self.during: Callable[[], Awaitable[None]] | None = None

    async def held(self, text: str, *, language: str) -> AudioChunk | None:
        self.asked.append((text, language))
        if self.during is not None:
            await self.during()
        return self.takes.get(text)


def _by_clause(rig: Rig) -> dict[tuple[int, int], list[str]]:
    """Each clause's events, by their kinds, in the order they came."""
    found: dict[tuple[int, int], list[str]] = {}
    for event in rig.session.events:
        if isinstance(event, Synthesizing | ClauseQueued | ClausePlayed | ClauseFailed):
            found.setdefault((event.reply_id, event.clause), []).append(type(event).__name__)
    return found


def test_a_held_clause_plays_with_no_request_and_a_miss_is_requested() -> None:
    port = _Held({HELD: TAKE})
    assert isinstance(port, HeldSpeech)

    async def body(rig: Rig) -> None:
        await rig.commands.run(_speak(0, HELD))
        await rig.commands.run(_speak(0, "A new clause.", clause=1))
        await until(lambda: len(rig.session.of(ClausePlayed)) == 2)

    rig = _run(port, body)
    assert port.asked == [(HELD, "en"), ("A new clause.", "en")]
    assert port.calls == [("A new clause.", "en")]  # no request for the held one
    assert _by_clause(rig) == {
        (0, 0): ["ClauseQueued", "ClausePlayed"],
        (0, 1): ["Synthesizing", "ClauseQueued", "ClausePlayed"],
    }
    held, asked = rig.session.of(ClauseQueued)
    assert (held.held, held.requested_at, asked.held) == (True, None, False)
    assert asked.requested_at is not None
    played = rig.session.of(ClausePlayed)[0]
    assert (played.audio_s, played.chunks, played.remaining_requests) == (0.5, 1, None)
    assert rig.captured.audio_s() == pytest.approx(0.5 + 13 * 0.06, abs=0.08)


def test_a_fixed_phrase_and_an_empty_clause_are_never_looked_up() -> None:
    port = _Held({HELD: TAKE})

    async def body(rig: Rig) -> None:
        await rig.commands.run(_speak(0, HELD, audio=SECOND))
        await rig.commands.run(_speak(1, "   "))
        await until(lambda: len(rig.session.of(ClausePlayed)) == 2)

    rig = _run(port, body)
    assert port.asked == [] and port.calls == []
    assert [e.held for e in rig.session.of(ClauseQueued)] == [False, False]


def test_a_clause_a_stop_dropped_while_its_take_was_read_is_never_played() -> None:
    """The stop's drop marked while the take is read, before the interruption reaches the
    bridge: the bridge checks again, and the clause is never spoken; the next one plays."""
    port = _Held({HELD: TAKE})

    async def body(rig: Rig) -> None:
        async def dropped() -> None:
            rig.events.dropped.add((0, 0))

        port.during = dropped
        await rig.commands.run(_speak(0, HELD))
        await until(lambda: bool(port.asked))
        port.during = None
        await rig.commands.run(_speak(1, "Welcome", audio=SECOND))
        await until(lambda: (1, 0) in rig.keyed(ClausePlayed))

    rig = _run(port, body)
    assert (0, 0) not in _by_clause(rig) and port.calls == []
    assert rig.captured.audio_s() == pytest.approx(1.0, abs=0.05)  # the phrase's alone


def test_a_stop_that_lands_while_a_take_is_read_drops_it_unplayed() -> None:
    port = _Held({HELD: TAKE})
    release = asyncio.Event()

    async def body(rig: Rig) -> None:
        async def waiting() -> None:
            await release.wait()

        port.during = waiting
        await rig.commands.run(_speak(0, HELD))
        await until(lambda: bool(port.asked))
        await rig.commands.run(StopSpeaking(reply_id=0))
        release.set()
        await asyncio.sleep(0.1)
        port.during = None
        await rig.commands.run(_speak(1, "Welcome", audio=SECOND))
        await until(lambda: (1, 0) in rig.keyed(ClausePlayed))

    rig = _run(port, body)
    assert (0, 0) not in _by_clause(rig) and port.calls == []
    assert rig.keyed(ClausePlayed) == [(1, 0)]


def test_a_text_to_speech_that_holds_no_speech_gives_todays_events_in_todays_order() -> None:
    """The characterization test (GP-18): no look-up, each clause's events as before the hook,
    none of them held."""
    port = FakeTextToSpeech()
    assert not isinstance(port, HeldSpeech)

    async def body(rig: Rig) -> None:
        await rig.commands.run(_speak(0, "Hello there"))
        await rig.commands.run(_speak(1, "Welcome", audio=SECOND))
        await rig.commands.run(_speak(2, "   "))
        await rig.commands.run(_speak(3, "and more"))
        await until(lambda: len(rig.session.of(ClausePlayed)) == 4)

    rig = _run(port, body)
    assert _by_clause(rig) == {
        (0, 0): ["Synthesizing", "ClauseQueued", "ClausePlayed"],
        (1, 0): ["ClauseQueued", "ClausePlayed"],
        (2, 0): ["ClauseQueued", "ClausePlayed"],
        (3, 0): ["Synthesizing", "ClauseQueued", "ClausePlayed"],
    }
    assert rig.keyed(ClausePlayed) == [(0, 0), (1, 0), (2, 0), (3, 0)]
    assert port.calls == [("Hello there", "en"), ("and more", "en")]
    assert not any(e.held for e in rig.session.of(ClauseQueued))
    assert rig.tts._holder is None
