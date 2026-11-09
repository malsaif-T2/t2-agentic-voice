"""The phrase cache (adapters/phrase_cache.py, plan 003's Track B): each fixed phrase synthesized
once and kept, a cache hit sending nothing; a phrase over `max_chars` packed into the fewest
requests that fit; a rate-limited request waited for and sent again, within the bounds; the
pronunciation map and the provider's text sent, the phrase found as written. Against
`FakeTextToSpeech` (tests/t2_agentic_voice/fakes.py), and Track A's splitter and map standing
in by their contracts until Track A merges (phrase_support.py's `track_a`). The prototype's
cache was read as a spec, never run (Ole5-chatbot/src/ole5_chat/voice/fillers.py, lines 24-75).
test_phrase_cache_files.py holds the files' tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Collection, Mapping
from pathlib import Path

import pytest
from t2_agentic_voice.adapters.phrase_cache import MAX_RETRY_DELAY_S, RETRIES, PhraseCache
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech
from t2_agentic_voice.domain.presets import ARABIC_FRAME, NOTICES
from t2_agentic_voice.voice.session.io import PhraseAudio

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.phrase_support import (
    ENGLISH,
    GREETING,
    LINES,
    LONG,
    VOICES,
    Sleeps,
    declare,
    english,
    take,
    track_a,
)
from tests.t2_agentic_voice.fakes import FAKE_FLOW, FakeTextToSpeech

__all__ = ["track_a"]  # Track A's stand-ins, for every test here


def test_each_phrase_is_synthesized_once_and_a_second_start_sends_nothing(
    tmp_path: Path,
) -> None:
    first = FakeTextToSpeech()
    cache, sent = declare(first, tmp_path, english())
    assert (sent, first.calls) == (5, [(text, "en") for text in ENGLISH])
    again = FakeTextToSpeech()
    cached, sent = declare(again, tmp_path, english())
    assert (sent, again.calls) == (0, [])  # a cache hit sends nothing
    for text in ENGLISH:
        audio = cached.audio(text, language="en")
        assert (
            audio
            == cache.audio(text, language="en")
            == AudioChunk(pcm16=take(text, first), sample_rate=24_000)
        )
    phrases: PhraseAudio = cached  # the session's view: mypy checks the protocol's shape
    assert phrases.audio(GREETING, language="en").seconds > 0


def test_a_changed_phrase_alone_is_synthesized_anew(tmp_path: Path) -> None:
    declare(FakeTextToSpeech(), tmp_path, english())
    fake = FakeTextToSpeech()
    _, sent = declare(fake, tmp_path, english("Hello, and welcome to another made-up line."))
    assert (sent, fake.calls) == (1, [("Hello, and welcome to another made-up line.", "en")])


def test_a_phrase_two_languages_share_is_synthesized_once(tmp_path: Path) -> None:
    """Both Arabic presets say the same frame in the same model and voice: one request."""
    fake = FakeTextToSpeech()
    languages = [Language.saudi_arabic(greeting="أهلا بك."), Language.arabic(greeting="مرحبا.")]
    cache, sent = declare(fake, tmp_path, VoiceAgent(name="echo", languages=languages))
    assert sent == 9 and [text for text, _ in fake.calls].count(ARABIC_FRAME) == 1
    assert cache.audio(ARABIC_FRAME, language="ar-SA") == cache.audio(ARABIC_FRAME, language="ar")


def test_a_long_greeting_of_eight_sentences_sends_two_requests(tmp_path: Path) -> None:
    assert len(LONG) == 204
    fake = FakeTextToSpeech(limit=200)
    cache, _ = declare(fake, tmp_path, english(LONG))
    sent = [text for text, _ in fake.calls if text not in ENGLISH[1:]]
    assert sent == [" ".join(LINES[:7]), LINES[7]] and all(len(text) <= 200 for text in sent)
    assert cache.audio(LONG, language="en").pcm16 == b"".join(take(text, fake) for text in sent)


def test_a_phrase_within_max_chars_is_one_request_even_with_a_comma(tmp_path: Path) -> None:
    fake = FakeTextToSpeech(limit=200)
    declare(fake, tmp_path, english())
    assert fake.calls[0] == (GREETING, "en")


class RefusedOnce:
    """A TextToSpeech that refuses the first request for each text of `refused` with its
    error, then passes every request to `inner`: `FakeTextToSpeech`'s `failures` fail every
    request for a text (plan 003's decision log, 2026-11-03). It keeps each text asked for."""

    name = "refused-once"
    data_flow = FAKE_FLOW

    def __init__(self, inner: FakeTextToSpeech, refused: Mapping[str, ProviderError]) -> None:
        self.inner = inner
        self.refused = dict(refused)
        self.asked: list[str] = []

    def max_chars(self, language: str) -> int | None:
        return self.inner.max_chars(language)

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        self.asked.append(text)
        refusal = self.refused.pop(text, None)
        if refusal is not None:
            raise refusal
        async for chunk in self.inner.synthesize(text, language=language):
            yield chunk

    async def check_language(self, language: str) -> None:
        await self.inner.check_language(language)

    async def aclose(self) -> None:
        await self.inner.aclose()


@pytest.mark.parametrize(("asked", "waited"), [(7.0, 7.0), (0.0, 0.0), (120.0, 60.0), (None, 60.0)])
def test_a_429_then_a_success_waits_once_and_sends_the_request_once_more(
    asked: float | None, waited: float, tmp_path: Path
) -> None:
    """The delay the provider asked for, at most a minute, and a minute when it asked none."""
    refused = RefusedOnce(
        FakeTextToSpeech(), {GREETING: ProviderError("rate_limited", True, asked)}
    )
    sleeps = Sleeps()
    cache, sent = declare(refused, tmp_path, english(), sleeps)
    assert (sleeps, sent, refused.asked) == ([waited], 6, [GREETING, *ENGLISH])
    assert cache.audio(GREETING, language="en").pcm16 == take(GREETING, refused.inner)


def test_three_429s_fail_naming_the_phrase_and_never_its_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeTextToSpeech(failures={GREETING: ProviderError("rate_limited", True, 3.0)})
    sleeps = Sleeps()
    with pytest.raises(ProviderError) as raised:
        declare(fake, tmp_path, english(), sleeps)
    error = raised.value
    assert (error.kind, error.retryable, error.retry_after_s) == ("rate_limited", True, 3.0)
    assert error.details == {"phrase": "greeting", "language": "en"}
    assert (sleeps, len(fake.calls)) == ([3.0] * RETRIES, RETRIES + 1)
    assert holding(GREETING, shown(error, caplog=caplog, capsys=capsys)) == []
    assert (error.__cause__, error.__context__) == (None, None)


def test_any_other_failure_fails_at_once_naming_the_phrase(tmp_path: Path) -> None:
    refusal = ProviderError("server_error", True, details={"status": 503})
    fake = FakeTextToSpeech(failures={NOTICES["en"]["ended"]: refusal})
    sleeps = Sleeps()
    with pytest.raises(ProviderError) as raised:
        declare(fake, tmp_path, english(), sleeps)
    assert (raised.value.kind, sleeps, len(fake.calls)) == ("server_error", [], 5)
    assert raised.value.details == {"status": 503, "phrase": "notices.ended", "language": "en"}


def test_the_pronunciation_map_is_sent_and_the_phrase_found_as_written(tmp_path: Path) -> None:
    greeting = "Your code starts with LT- and four digits."
    fake = FakeTextToSpeech()
    cache, _ = declare(fake, tmp_path, english(greeting, {"LT-": {"en": "L T"}}))
    assert fake.calls[0] == ("Your code starts with L T and four digits.", "en")
    assert cache.audio(greeting, language="en").pcm16 == take(fake.calls[0][0], fake)


def test_a_map_that_takes_a_phrase_past_max_chars_sends_two_requests(tmp_path: Path) -> None:
    greeting = " ".join(["Your code LT- is here."] * 8)  # 183 characters, 311 once said
    fake = FakeTextToSpeech(limit=200)
    cache, sent = declare(fake, tmp_path, english(greeting, {"LT-": {"en": "the letters L and T"}}))
    said = "Your code the letters L and T is here."
    assert [text for text, _ in fake.calls[:2]] == [" ".join([said] * 5), " ".join([said] * 3)]
    assert sent == 6 and all(len(text) <= 200 for text, _ in fake.calls)
    assert cache.audio(greeting, language="en").seconds > 0


def test_a_saudi_greeting_is_sent_with_no_direction_mark_and_a_plain_space(tmp_path: Path) -> None:
    greeting = "أهلا وسهلا‏ بك في الخط."  # a no-break space, a right-to-left mark
    fake = FakeTextToSpeech()
    agent = VoiceAgent(name="echo", languages=[Language.saudi_arabic(greeting=greeting)])
    cache, _ = declare(fake, tmp_path, agent)
    assert fake.calls[0] == ("أهلا وسهلا بك في الخط.", "ar-SA")
    assert cache.audio(greeting, language="ar-SA").pcm16 == take(fake.calls[0][0], fake)


def test_heard_words_never_reach_the_cache(tmp_path: Path) -> None:
    """Invariant 8: `audio` finds only what was declared, with no request and no file, and its
    error holds no text of the call."""
    fake = FakeTextToSpeech()
    cache, _ = declare(fake, tmp_path, english())
    files = sorted(tmp_path.iterdir())
    heard = "made-up words a caller said"
    for text, language in [(heard, "en"), (GREETING, "ar-SA")]:
        with pytest.raises(LookupError) as raised:
            cache.audio(text, language=language)  # type: ignore[arg-type]
        assert holding(text, shown(raised.value)) == []
        assert raised.value.__context__ is None
    assert (len(fake.calls), sorted(tmp_path.iterdir())) == (5, files)


class Rates:
    """A TextToSpeech whose takes come at `rates`, one a request in turn."""

    name = "rates"
    data_flow = FAKE_FLOW

    def __init__(self, rates: Collection[int]) -> None:
        self.fakes = [FakeTextToSpeech(sample_rate=rate) for rate in rates]
        self.sent = 0

    def max_chars(self, language: str) -> int | None:
        return 200

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        fake = self.fakes[self.sent % len(self.fakes)]
        self.sent += 1
        async for chunk in fake.synthesize(text, language=language):
            yield chunk

    async def check_language(self, language: str) -> None:
        return None

    async def aclose(self) -> None:
        return None


@pytest.mark.parametrize(
    ("tts", "error"),
    [
        (Rates([24_000, 22_050]), "sample_rates_differ"),
        (FakeTextToSpeech(seconds_per_char=0), "no_audio"),
    ],
)
def test_a_phrase_with_two_rates_or_no_audio_fails_as_a_server_error(
    tts: TextToSpeech, error: str, tmp_path: Path
) -> None:
    with pytest.raises(ProviderError) as raised:
        declare(tts, tmp_path, english(LONG))
    assert (raised.value.kind, raised.value.retryable) == ("server_error", False)
    assert raised.value.details == {"error": error, "phrase": "greeting", "language": "en"}


def test_a_language_with_no_voice_is_a_configuration_error(tmp_path: Path) -> None:
    cache = PhraseCache(FakeTextToSpeech(), folder=tmp_path, voices={"ar": VOICES["ar"]})
    with pytest.raises(ConfigurationError) as raised:
        asyncio.run(cache.declare(english()))
    assert raised.value.details == {"setting": "T2V_TTS__LANGUAGES"}
    assert "FIX: give T2V_TTS__LANGUAGES a model and a voice" in raised.value.message


def test_a_rate_limited_request_waits_at_most_a_minute_and_is_sent_again_twice() -> None:
    """The bounds the integrator ruled for the phrases' requests at start (plan 003)."""
    assert (MAX_RETRY_DELAY_S, RETRIES) == (60.0, 2)
