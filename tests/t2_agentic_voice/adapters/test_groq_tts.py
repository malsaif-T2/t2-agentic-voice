"""GroqTTS against a fake Groq: the baseline request, the audio as it
streams (its sample rate read, its headroom on the first chunk, a take cut short flagged on the
last, the silence trimmed only when asked), the text refused over `max_chars`, and each failure
as a ProviderError, a model whose terms are not accepted with its FIX. The prototype's call was
read as a spec, never run (Ole5-chatbot/src/ole5_chat/voice/tts.py, lines 191-221). A fake
transport only: nothing leaves the machine. And `check_language`, with no synthesis, giving the
time Groq sent the model list from its `Date`.
test_groq_tts_checks.py holds the rest: the key, the SDK's own variables, a stop and a timeout,
and the settings' checks."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from t2_agentic_voice.adapters.groq_tts import GroqTTS, cut_short
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.tts import TtsSettings, TtsVoice
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk

from tests.t2_agentic_voice.adapters.groq_support import KEY, FakeGroq, Reply
from tests.t2_agentic_voice.adapters.tts_support import (
    ENGLISH,
    answer,
    silence,
    speak,
    tone,
    tts_settings,
    wav,
)

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "groq_tts_request.json").read_text(encoding="utf-8")
)
SENT = {"host", "accept", "accept-encoding", "connection", "user-agent", "content-type"}
SENT |= {"content-length", "authorization"}
REMAINING = ("x-ratelimit-remaining-requests", "x-ratelimit-remaining-tokens")
ARABIC = "هذه كلمات مصنوعة للتجربة فقط."  # 29 characters


def spoken(reply: Reply, text: str = ENGLISH, language: str = "en", **tts: Any) -> list[AudioChunk]:
    return asyncio.run(speak(FakeGroq(reply), text, language, **tts))


def test_the_request_is_block_0s_baseline() -> None:
    call, want, client = FIXTURE["call"], FIXTURE["request"], FIXTURE["client"]
    defaults = TtsSettings()
    assert (GroqSettings().base_url, defaults.timeout_s) == (
        call["settings"]["groq.base_url"],
        call["settings"]["tts.timeout_s"],
    )
    fake = FakeGroq(answer(wav(tone(0.1))))
    asyncio.run(speak(fake, call["text"], call["language"]))
    (request,) = fake.requests
    assert (request.method, str(request.url)) == (want["method"], want["url"])
    assert request.content == want["body"].encode("utf-8")
    sha = hashlib.sha256(request.content).hexdigest()
    assert (len(request.content), sha) == (want["body_bytes"], want["body_sha256"])
    sent = json.loads(request.content)
    assert sent == want["json"] and not set(want["absent_fields"]) & set(sent)
    assert (request.headers["accept"], request.headers["content-type"]) == (
        want["accept"],
        want["content_type"],
    )
    assert set(request.headers) == SENT  # the SDK's raw-response marker never sent
    assert request.headers.get_list("authorization") == [f"Bearer {KEY}"]
    assert int(request.headers["content-length"]) == len(request.content)
    phases = ("connect", "read", "write", "pool")
    assert request.extensions["timeout"] == dict.fromkeys(phases, client["timeout_s"])


@pytest.mark.parametrize("language", ["ar", "en"])
def test_each_language_is_spoken_in_its_own_model_and_voice(language: str) -> None:
    voices = {"ar": TtsVoice(model="canopylabs/orpheus-arabic-saudi", voice="made-up-voice")}
    voices["en"] = TtsVoice(model="canopylabs/orpheus-v1-english", voice="another")
    fake = FakeGroq(answer(wav(tone(0.1))))
    asyncio.run(speak(fake, "Made up.", language, languages=voices))
    sent = json.loads(fake.requests[0].content)
    assert (sent["model"], sent["voice"]) == (voices[language].model, voices[language].voice)


@pytest.mark.parametrize("rate", [22_050, 24_000])
def test_the_audio_streams_in_whole_samples_at_the_rate_its_header_names(rate: int) -> None:
    pcm = tone(2.0, rate)
    headers = {REMAINING[0]: "13", REMAINING[1]: "1150"}
    chunks = spoken(answer(wav(pcm, rate=rate), size=333, headers=headers))
    assert len(chunks) > 10 and b"".join(c.pcm16 for c in chunks) == pcm
    assert {c.sample_rate for c in chunks} == {rate}
    assert (chunks[0].remaining_requests, chunks[0].remaining_tokens) == (13, 1150)
    assert {(c.remaining_requests, c.remaining_tokens) for c in chunks[1:]} == {(None, None)}
    assert not any(c.cut_short for c in chunks) and all(c.pcm16 for c in chunks)


@pytest.mark.parametrize(
    ("sent", "headroom"),
    [
        ({}, (None, None)),
        ({REMAINING[0]: "0", REMAINING[1]: "x"}, (0, None)),
        ({REMAINING[0]: "-1", REMAINING[1]: "007"}, (None, 7)),
    ],
)
def test_the_headroom_rides_on_the_first_chunk(
    sent: dict[str, str], headroom: tuple[int | None, int | None]
) -> None:
    (first, *_) = spoken(answer(wav(tone(2.0)), headers=sent))
    assert (first.remaining_requests, first.remaining_tokens) == headroom


def test_a_take_with_no_audio_ends_with_one_empty_chunk_that_carries_its_headroom() -> None:
    chunks = spoken(answer(wav(b""), headers={REMAINING[0]: "9"}), "Short.")
    assert chunks == [AudioChunk(pcm16=b"", sample_rate=24_000, remaining_requests=9)]


CUT = [
    (ENGLISH, "en", 1.0, True),  # 44 characters in 1 s: 44 a second, over English's 30
    (ENGLISH, "en", 2.0, False),  # 22 a second
    ("مرحبا بك، هذه جملة مصنوعة من أجل التجربة.", "ar-SA", 1.5, True),  # 41 in 1.5 s: 27
    ("مرحبا بك، هذه جملة مصنوعة من أجل التجربة.", "ar", 2.0, False),  # 20.5 a second
    ("Made-up words.", "en", 0.1, False),  # under 30 characters: too short to tell
    (ENGLISH, "en", 0.0, True),  # no speech at all
]


@pytest.mark.parametrize(("text", "language", "speech_s", "short"), CUT)
def test_a_take_cut_short_is_flagged_on_its_last_chunk(
    text: str, language: str, speech_s: float, short: bool
) -> None:
    """The prototype's ceilings, on the speech from its first sound (0.5 s of silence lead it);
    flagged, never made again, and an empty chunk only when there is a flag to carry."""
    assert cut_short(text, language, speech_s) is short
    pcm = silence(0.5) + tone(speech_s)
    chunks = spoken(answer(wav(pcm)), text, language)
    assert b"".join(c.pcm16 for c in chunks) == pcm
    assert [c.cut_short for c in chunks] == [False] * (len(chunks) - 1) + [short]
    assert (chunks[-1].pcm16 == b"") is short


def test_the_silence_before_the_speech_is_trimmed_only_when_asked() -> None:
    pcm = silence(0.48) + tone(1.0)
    kept = b"".join(c.pcm16 for c in spoken(answer(wav(pcm), size=100)))
    trimmed = b"".join(c.pcm16 for c in spoken(answer(wav(pcm), size=100), trim_silence=True))
    assert (kept, trimmed) == (pcm, pcm[11 * 1920 :])  # its last 40 ms before the speech kept


def test_the_trims_held_silence_at_the_end_comes_on_the_last_chunk() -> None:
    """Speech only in the last part of a 40 ms frame: the trim gives it once the take ends."""
    pcm = silence(0.08) + tone(0.01)
    chunks = spoken(answer(wav(pcm)), "Short.", trim_silence=True)
    assert [c.pcm16 for c in chunks] == [pcm[1920:]]


@pytest.mark.parametrize(("length", "sent"), [(200, 1), (201, 0)])
def test_a_text_over_max_chars_is_refused_unsent(length: int, sent: int) -> None:
    fake = FakeGroq(answer(wav(tone(0.1))))
    text = ("Made up. " * 30)[:length]
    adapter = GroqTTS.from_settings(tts_settings(), transport=fake)
    assert (adapter.max_chars("en"), adapter.max_chars("ar-SA")) == (200, 200)
    if sent:
        asyncio.run(speak(fake, text))
    else:
        with pytest.raises(ProviderError) as raised:
            asyncio.run(speak(fake, text))
        assert (raised.value.kind, raised.value.retryable) == ("rejected", False)
        assert raised.value.details == {"error": "too_long", "max_chars": 200}
    assert len(fake.requests) == sent
    asyncio.run(adapter.aclose())


def test_a_language_with_no_model_is_refused_unsent() -> None:
    fake = FakeGroq()
    only = {"en": TtsVoice(model="canopylabs/orpheus-v1-english", voice="troy")}
    with pytest.raises(ProviderError) as raised:
        asyncio.run(speak(fake, ARABIC, "ar", languages=only))
    assert (raised.value.kind, raised.value.details) == ("rejected", {"error": "no_voice"})
    assert fake.requests == []
    adapter = GroqTTS.from_settings(tts_settings(languages=only))
    assert adapter.max_chars("ar") == 200  # the least of the models': no text of it is spoken
    asyncio.run(adapter.aclose())


def _status(
    status: int, retry_after: str | None = None, body: dict[str, Any] | None = None
) -> httpx.Response:
    headers = {} if retry_after is None else {"retry-after": retry_after}
    return httpx.Response(status, headers=headers, json=body or {"error": {"message": "made-up"}})


BAD = ("server_error", False, None)  # an answer that is not the WAV asked for
FAILURES = [
    (_status(429, "7"), "rate_limited", True, 7.0),
    (_status(429), "rate_limited", True, None),
    *[(_status(code), "server_error", True, None) for code in (500, 503, 409)],
    (_status(408), "timeout", True, None),
    *[(_status(code), "rejected", False, None) for code in (400, 401, 403, 404, 413, 422)],
    (
        httpx.Response(307, headers={"location": "https://elsewhere.example/"}),
        "rejected",
        False,
        None,
    ),
    (httpx.ReadTimeout("made-up"), "timeout", True, None),
    (httpx.ConnectError("made-up"), "connection_lost", True, None),
    # The SDK does not wrap a failure while the answer streams.
    (answer(wav(tone(1.0)), fail=httpx.ReadTimeout("made-up")), "timeout", True, None),
    (
        answer(wav(tone(1.0)), fail=httpx.RemoteProtocolError("made-up")),
        "connection_lost",
        True,
        None,
    ),
    (answer(wav(tone(1.0)), fail=httpx.ReadError("made-up")), "connection_lost", True, None),
    (answer(b"made-up, no WAV"), *BAD),
    (answer(wav(b"", channels=2)), *BAD),
    (answer(wav(tone(0.1))[:30]), *BAD),  # ended before its audio
]


@pytest.mark.parametrize(("reply", "kind", "retry", "delay"), FAILURES)
def test_each_failure_asked_once(reply: Reply, kind: str, retry: bool, delay: float | None) -> None:
    fake = FakeGroq(reply)
    with pytest.raises(ProviderError) as raised:
        asyncio.run(speak(fake))
    error = raised.value
    assert (error.kind, error.retryable, error.retry_after_s) == (kind, retry, delay)
    assert len(fake.requests) == 1  # no retry, no redirect followed
    assert (error.__cause__, error.__context__, error.__suppress_context__) == (None, None, True)
    assert "fix" not in error.details


TERMS = {"message": "made-up", "type": "invalid_request_error", "code": "model_terms_required"}


@pytest.mark.parametrize("code", [400, 403])
def test_a_model_whose_terms_are_not_accepted_is_rejected_with_its_fix(code: int) -> None:
    with pytest.raises(ProviderError) as raised:
        spoken(_status(code, body={"error": TERMS}), ARABIC, "ar-SA")
    error = raised.value
    assert (error.kind, error.retryable) == ("rejected", False)
    fix = error.details.pop("fix")
    assert error.details == {
        "error": "model_terms_required",
        "status": code,
        "model": "canopylabs/orpheus-arabic-saudi",
    }
    assert isinstance(fix, str) and fix.startswith("FIX: accept the terms of")
    assert "console.groq.com" in fix and error.__notes__ == [fix]


@pytest.mark.parametrize(
    "body",
    [{"error": TERMS | {"code": "made_up"}}, {"error": "model_terms_required"}, {"code": TERMS}],
)
def test_another_refusal_carries_no_fix(body: dict[str, Any]) -> None:
    with pytest.raises(ProviderError) as raised:
        spoken(_status(400, body=body))
    assert raised.value.details == {"error": "BadRequestError", "status": 400}


MODEL = {"object": "model", "created": 0, "owned_by": "made-up"}
LISTED = {
    "object": "list",
    "data": [MODEL | {"id": voice.model} for voice in TtsSettings().languages.values()],
}


async def _check(fake: FakeGroq, language: str, **tts: Any) -> datetime | None:
    adapter = GroqTTS.from_settings(tts_settings(**tts), transport=fake)
    try:
        return await adapter.check_language(language)
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("language", ["ar-SA", "ar", "en"])
def test_check_language_asks_only_for_the_model_list(language: str) -> None:
    fake = FakeGroq(httpx.Response(200, json=LISTED))
    assert asyncio.run(_check(fake, language)) is None  # no Date: no time
    (request,) = fake.requests
    assert (request.method, request.url.path, request.content) == ("GET", "/openai/v1/models", b"")
    assert request.headers.get_list("authorization") == [f"Bearer {KEY}"]


@pytest.mark.parametrize(
    ("date", "sent"),
    [
        ("Wed, 04 Nov 2026 09:15:02 GMT", datetime(2026, 11, 4, 9, 15, 2, tzinfo=UTC)),
        ("Wed, 04 Nov 2026 25:15:02 GMT", None),
        ("made-up", None),
    ],
)
def test_check_language_gives_the_time_groq_sent_the_list_in_its_one_request(
    date: str, sent: datetime | None
) -> None:
    fake = FakeGroq(httpx.Response(200, json=LISTED, headers={"date": date}))
    assert asyncio.run(_check(fake, "en")) == sent
    assert [(r.method, r.url.path) for r in fake.requests] == [("GET", "/openai/v1/models")]


def test_check_language_refuses_a_model_groq_does_not_list() -> None:
    listing = {"object": "list", "data": [MODEL | {"id": "canopylabs/orpheus-v1-english"}]}
    with pytest.raises(ProviderError) as raised:
        asyncio.run(_check(FakeGroq(httpx.Response(200, json=listing)), "ar-SA"))
    error = raised.value
    fix = error.details.pop("fix")
    assert (error.kind, error.details) == (
        "rejected",
        {"error": "model_not_listed", "model": "canopylabs/orpheus-arabic-saudi"},
    )
    assert isinstance(fix, str) and fix.startswith("FIX: ") and error.__notes__ == [fix]


def test_check_language_refuses_a_language_with_no_model_unasked() -> None:
    fake = FakeGroq()
    only = {"en": TtsSettings().languages["en"]}
    with pytest.raises(ConfigurationError) as raised:
        asyncio.run(_check(fake, "ar", languages=only))
    assert raised.value.details == {"setting": "T2V_TTS__LANGUAGES"}
    assert "FIX: give T2V_TTS__LANGUAGES a model and a voice" in raised.value.message
    assert fake.requests == []


@pytest.mark.parametrize(
    ("reply", "kind"),
    [
        (httpx.Response(401, json={"error": {"message": "made-up"}}), "rejected"),
        (httpx.Response(503, json={"error": {"message": "made-up"}}), "server_error"),
        (httpx.Response(200, json={"object": "list"}), "server_error"),  # no data: unread
        (httpx.ConnectError("made-up"), "connection_lost"),
    ],
)
def test_check_language_fails_as_a_provider_error(
    reply: httpx.Response | Exception, kind: str
) -> None:
    with pytest.raises(ProviderError) as raised:
        asyncio.run(_check(FakeGroq(reply), "en"))
    assert raised.value.kind == kind
    assert (raised.value.__cause__, raised.value.__context__) == (None, None)
