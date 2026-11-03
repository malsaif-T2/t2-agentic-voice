"""The voice session in echo mode (voice/session/call.py), driven by the fake session I/O: the
call's start (the language named to speech-to-text, the `hello`, the greeting as reply 0), the
echo per language (the cached frame, then the heard words in the language's voice, clause by
clause, as the pronunciation map says them), the heard clauses packed into as few requests as fit
and an echo's requests bounded, every reply's and caption's key its own, a turn whose speech
began during the greeting not said back, the phrase cache never asked for heard words, and a call
whose phrase audio lacks a fixed phrase."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import AgentSpeechEnded, CallStarted, UserTurnEnded
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.fixed_phrases import fixed_phrases
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.voice.protocol import Ended, Notice, SessionHello, State
from t2_agentic_voice.voice.session.commands import HangUp, ListenIn
from t2_agentic_voice.voice.session.echo import MAX_ECHO_REQUESTS

from tests.t2_agentic_voice.session_fakes import AGENT, FakePhrases
from tests.t2_agentic_voice.voice.session.session_support import (
    HEARD,
    HEARD_AR,
    call,
    captions,
    emitted,
    greeted,
    play,
    report,
    said_back,
    sent,
    speaks,
    turn,
)


@pytest.mark.parametrize(("tag", "heard"), [("en", HEARD), ("ar-SA", HEARD_AR)])
def test_the_echo_says_each_turn_back_in_the_voice_of_its_language(
    settings: VoiceSettings, tag: LanguageTag, heard: str
) -> None:
    """Once connected: the call's language named to speech-to-text, the `hello` with the call's
    language first, the greeting from the cache as reply 0. A turn is said back as the next
    reply: its language's cached frame, then the heard words, each clause a request in that
    language's voice, captioned as said; the phrase cache is never asked for them."""
    io, _ = call(settings, language=tag)
    language = io.setup.language

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, f"  {heard} ", language=language.primary)
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    commands = io.commands.commands
    assert commands[0] == ListenIn(language=language.primary)
    (hello,) = sent(io, SessionHello)
    assert hello.call_id == "call-1" and hello.languages[0] == tag and len(hello.languages) == 2
    greeting, frame, *words = speaks(io)
    assert (greeting.reply_id, greeting.turn_id, greeting.text) == (0, None, language.greeting)
    assert (frame.reply_id, frame.clause, frame.turn_id) == (1, 0, 0)
    assert frame.text == language.echo_frame and frame.audio is not None
    clauses = said_back(io, heard)
    assert [w.text for w in words] == [provider_text(c) for c in clauses]
    assert all(w.audio is None and w.language == tag and w.turn_id == 0 for w in words)
    assert {s.language for s in speaks(io)} == {tag}  # one voice a call, its language's
    assert [c.text for c in captions(io)] == [language.greeting, language.echo_frame, *clauses]
    (caller,) = captions(io, "caller")
    assert (caller.text, caller.turn_id) == (heard, 0)
    asked = {text for text, _ in io.phrases.asked}
    assert asked == {language.greeting, language.echo_frame} and heard not in asked
    assert [e.heard for e in emitted(io, UserTurnEnded)] == [heard]
    spoken = emitted(io, AgentSpeechEnded)
    assert [(e.turn_id, e.played_fraction) for e in spoken] == [(None, 1.0), (0, 1.0)]
    assert spoken[1].text == " ".join([language.echo_frame, *clauses])
    assert len(emitted(io, CallStarted)) == 1 and commands[-1] == HangUp(reason="caller_left")
    (record,) = report(io).turns
    assert (record.heard, record.said, record.language) == (heard, spoken[1].text, tag)
    states = [m.state for m in sent(io, State)]
    assert states[:2] == ["thinking", "speaking"] and "listening" in states


_THANKS = " ".join(["Thank you."] * 15)  # a turn Whisper's hallucination might give


@pytest.mark.parametrize(
    ("tag", "heard", "max_chars", "requests"),
    [
        ("en", "Hi, I want to check my order. Can you help?", 200, None),
        ("en", _THANKS, 200, None),
        ("ar-SA", "ابغى اعرف حالة الطلب، وش صار عليه؟ ابي رد.", 200, None),
        (
            "en",
            "One, two. Three, four. Five, six. Seven, eight.",
            30,
            ["One, two. Three, four. Five,", "six. Seven, eight."],
        ),
    ],
)
def test_the_heard_clauses_are_packed_into_as_few_requests_as_fit(
    settings: VoiceSettings,
    tag: LanguageTag,
    heard: str,
    max_chars: int,
    requests: list[str] | None,
) -> None:
    """A clause the splitter cuts at a comma, a full stop or a question mark is not a request
    of its own: the clauses go greedily, in order, into requests of at most `max_chars`, joined
    by a space, each captioned as said, so a turn of n characters costs about n / `max_chars`
    requests (one a clause would burst past Groq's published 10 a minute). None: the turn fits
    one request."""
    io, _ = call(settings, language=tag, max_chars=max_chars)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, heard, language=io.setup.language.primary)
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    expected = [heard] if requests is None else requests
    words = speaks(io, 1)[1:]
    assert [w.text for w in words] == expected and all(len(w.text) <= max_chars for w in words)
    assert [c.text for c in captions(io) if c.reply_id == 1][1:] == expected
    _, orpheus = report(io).usage
    assert orpheus.requests == len(expected)


def test_an_echo_sends_at_most_its_bound_of_requests(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    """A transcript a hallucination made long, four requests' worth at 200 characters, is said
    back only as far as its first `MAX_ECHO_REQUESTS` requests, the cut logged by number alone,
    so one turn cannot burst past Groq's published 10 a minute."""
    heard = " ".join([_THANKS] * 4)
    io, _ = call(settings)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, heard)
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    full = said_back(io, heard)
    assert len(full) > MAX_ECHO_REQUESTS
    words = speaks(io, 1)[1:]
    assert [w.text for w in words] == full[:MAX_ECHO_REQUESTS]
    assert all(len(w.text) <= 200 for w in words)
    _, orpheus = report(io).usage
    assert orpheus.requests == MAX_ECHO_REQUESTS
    (cut,) = [r for r in caplog.records if r.getMessage() == "echo_cut"]
    fields = {"reply_id": 1, "requests": len(full), "sent": MAX_ECHO_REQUESTS}
    assert getattr(cut, "fields", None) == fields


def test_a_turn_begun_in_the_greeting_is_not_said_back_and_every_key_is_its_own(
    settings: VoiceSettings,
) -> None:
    """The greeting is reply 0, naming no turn. Turn 0's speech begins while it plays, so it is
    not said back (but kept, heard and dropped); turn 1's echo is reply 1, naming turn 1. Every
    `Speak` and every agent caption has a key of its own."""
    io, _ = call(settings)

    async def drive() -> None:
        await io.connected()
        await io.clause_queued(0, 0)
        await io.clock.advance(0.2)
        await io.turn_opened(0)  # its speech began while the greeting played
        await io.clock.advance(0.3)
        await io.clause_played(0, 0, audio_s=0.5)
        await io.turn_closed(0)
        await io.transcribing(0)
        await io.transcribed(0, "the greeting leaked back", language="en")
        await io.clock.advance(1.0)
        await turn(io, 1, HEARD)
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    keys = [(s.reply_id, s.clause) for s in speaks(io)]
    assert len(set(keys)) == len(keys) and {s.reply_id for s in speaks(io)} == {0, 1}
    assert [s.turn_id for s in speaks(io)] == [None] + [1] * (len(keys) - 1)
    agent = [(c.reply_id, c.clause) for c in captions(io)]
    assert agent == keys and len(set(agent)) == len(agent)
    assert [c.turn_id for c in captions(io, "caller")] == [1]  # a dropped turn is not shown
    assert [e.turn_id for e in emitted(io, UserTurnEnded)] == [1]
    dropped, answered = report(io).turns
    assert dropped.dropped and dropped.heard == "the greeting leaked back" and not dropped.said
    assert not answered.dropped and answered.said


def test_a_mapped_term_is_said_in_the_calls_language_and_its_clauses_measured_said(
    settings: VoiceSettings,
) -> None:
    """A reply holding a term of the pronunciation map gets the term's Arabic form in an Arabic
    call, and its clauses are cut on that said form, each within `max_chars`."""
    arabic = "اكمي للخدمات الرقمية المتقدمة جدا"  # longer than max_chars once said
    agent = VoiceAgent(
        name="mapped",
        languages=[Language.saudi_arabic(greeting="أهلا وسهلا")],
        pronounce={"Acme": {"ar": arabic, "en": "Ack me"}},
    )
    io, _ = call(settings, agent=agent, max_chars=20)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, "طلب Acme", language="ar")
        await play(io, 1)
        await io.ending()

    asyncio.run(drive())
    words = speaks(io, 1)[1:]
    assert len(words) > 1 and all(len(w.text) <= 20 for w in words)
    assert all("Acme" not in w.text for w in words)
    shown = " ".join(c.text for c in captions(io) if c.reply_id == 1 and c.clause)
    assert shown.split() == f"طلب {arabic}".split()


def test_the_language_named_to_speech_to_text_is_none_under_auto(settings: VoiceSettings) -> None:
    auto = VoiceSettings(
        env="test", stt=SttSettings(live_language="auto"), storage=settings.storage
    )
    io, _ = call(auto)

    async def drive() -> None:
        await io.connected()
        await io.connected()  # a second Connected changes nothing

    asyncio.run(drive())
    assert io.commands.of(ListenIn) == [ListenIn(language=None)]
    assert len(speaks(io)) == 1 and len(sent(io, SessionHello)) == 1


def test_a_phrase_the_cache_lacks_goes_unsaid_and_sends_no_request(
    settings: VoiceSettings,
) -> None:
    """With phrase audio holding none of the agent's phrases (a runtime fault): no greeting, an
    echo with no frame (its words from clause 0), an `error` notice sent but not spoken, and at
    `limits.idle_s` the `ended` notice cannot play, so the call ends at once."""
    io, _ = call(settings, phrases=FakePhrases())
    limits = settings.limits

    async def drive() -> None:
        await io.connected()
        await turn(io, 0, HEARD)
        await io.clause_queued(0, 0)
        await io.clause_failed(0, 0)
        await turn(io, 1, None, audio_s=0.5)  # an empty transcript: nothing said back
        await io.clock.advance(limits.idle_s)
        await io.close()

    asyncio.run(drive())
    assert next((s.reply_id, s.clause, s.audio) for s in speaks(io)) == (0, 0, None)
    assert all(s.audio is None for s in speaks(io))
    assert [n.kind for n in sent(io, Notice)] == ["error", "ended"]
    assert sent(io, Ended) == [Ended(reason="idle")]
    assert io.commands.commands[-1] == HangUp(reason="idle")
    fixed = {phrase.text for phrase in fixed_phrases(AGENT)}
    assert {text for text, _ in io.phrases.asked} <= fixed
