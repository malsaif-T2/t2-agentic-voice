"""GroqSTT's own checks (plan 002's review of the merged tracks): built in code, it refuses what
the settings refuse, by the settings' own models (GP-20); and every request carries the adapter's
own multipart boundary, so a `GROQ_CUSTOM_HEADERS` content-type line can only fail a request,
and audio that holds a boundary line adds no form field (GP-08). A fake transport only."""

from __future__ import annotations

import asyncio
import logging
import math
import re
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_stt import GroqSTT
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.groq_support import CLIP, KEY, SETTING, FakeGroq, call, parts

URLS = ("http://api.groq.com", "https://made:up@api.groq.com", "https://api.groq.com?made=up")
MORE_URLS = ("https://api.groq.com#made-up", "https://", "https://api.groq.com:99999", "https://[x")
# The settings refuse these too: a port of 0, and a space or a tab anywhere in the URL.
SPACED_URLS = ("https://api.groq.com:0", "https://api.groq.com/a b", "https://api.groq.com\t")
REFUSED = [
    *[({"api_key": SecretStr(key)}, SETTING) for key in (" ", "made up", "made-up-é", "a\nb")],
    ({"model": "whisper-1"}, "T2V_STT__MODEL"),
    *[({"base_url": url}, "T2V_GROQ__BASE_URL") for url in URLS + MORE_URLS + SPACED_URLS],
    *[({"timeout_s": value}, "T2V_STT__TIMEOUT_S") for value in (0.0, -1.0, math.inf, math.nan)],
]
VALID: dict[str, Any] = {"api_key": SecretStr(KEY), "model": "whisper-large-v3"}
VALID |= {"base_url": "https://api.groq.com", "timeout_s": 6.0}
SENT_FIELDS = ["model", "language", "response_format", "temperature", "file"]
# Audio that holds a boundary line, then the head of a form field the adapter never sends.
INJECTED = b'\r\n--madeup\r\nContent-Disposition: form-data; name="prompt"\r\n\r\nmade-up words'
PCM = INJECTED + b"\x00" * (32_000 - len(INJECTED))  # 1 s at 16 kHz, holding it
CONTENT_TYPE_LINES = ("content-type", "CONTENT-TYPE", "content-Type")


@pytest.mark.parametrize(("given", "setting"), REFUSED)
def test_built_in_code_it_refuses_what_settings_refuse(given: dict[str, Any], setting: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        GroqSTT(**(VALID | given))
    assert raised.value.details == {"setting": setting}
    assert setting in raised.value.message and "FIX: " in raised.value.message
    if "api_key" in given and given["api_key"].get_secret_value().strip():
        assert holding(given["api_key"].get_secret_value(), shown(raised.value)) == []
    if given.get("base_url", "https://") != "https://":  # the rule names the scheme itself
        assert holding(given["base_url"], shown(raised.value)) == []


def test_a_refused_value_is_named_and_no_file_of_the_repository() -> None:
    """An installed library ships no `.env.example`, so the FIX line names only the setting."""
    with pytest.raises(ConfigurationError) as raised:
        GroqSTT(**(VALID | {"timeout_s": 0.0}))
    assert raised.value.message == (
        "The Groq adapter refuses its T2V_STT__TIMEOUT_S (Input should be greater than 0). "
        "FIX: give it a value the settings take."
    )


def test_a_bad_key_is_refused_with_the_settings_own_fix_line() -> None:
    """Not "give one that holds a character no API key holds", which asked for the opposite."""
    with pytest.raises(ConfigurationError) as raised:
        GroqSTT(**(VALID | {"api_key": SecretStr("made up")}))
    message = raised.value.message
    assert message.startswith(f"{SETTING} holds a character no API key holds")
    assert message.endswith("FIX: give the key alone, on one line.")


def test_a_key_with_space_around_it_is_sent_as_the_settings_read_it() -> None:
    fake = FakeGroq()

    async def scenario() -> None:
        adapter = GroqSTT(**(VALID | {"api_key": SecretStr(f"  {KEY}\n")}), transport=fake)
        await adapter.transcribe(CLIP, language="ar", prompt=None)
        await adapter.aclose()

    asyncio.run(scenario())
    assert fake.requests[0].headers.get_list("authorization") == [f"Bearer {KEY}"]


def _boundary(request: httpx.Request) -> str:
    kind, _, boundary = request.headers["content-type"].partition("; boundary=")
    assert kind == "multipart/form-data"
    assert request.content.startswith(f"--{boundary}\r\n".encode())
    return boundary


def test_each_adapter_cuts_its_body_with_a_random_boundary_of_its_own() -> None:
    first, second = FakeGroq(), FakeGroq(httpx.Response(200, json={"text": "x"}))
    asyncio.run(call(first))
    asyncio.run(call(second))
    boundaries = [_boundary(fake.requests[0]) for fake in (first, second)]
    assert all(re.fullmatch(r"[0-9a-f]{32}", b) for b in boundaries)
    assert boundaries[0] != boundaries[1]


@pytest.mark.parametrize("name", CONTENT_TYPE_LINES)
def test_a_content_type_line_in_another_case_fails_the_request_and_sends_nothing(
    name: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """httpx would cut the body by the line's boundary; the hook refuses the body unsent, as a
    request no attempt can mend, and no error or log line holds the key or the boundary."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("GROQ_CUSTOM_HEADERS", f"{name}: multipart/form-data; boundary=madeup")
    fake = FakeGroq()
    with pytest.raises(ProviderError) as raised:
        asyncio.run(call(fake))
    error = raised.value
    assert (error.kind, error.retryable, error.retry_after_s) == ("rejected", False, None)
    assert (fake.requests, error.details) == ([], {"error": "foreign_boundary"})
    assert (error.__cause__, error.__suppress_context__) == (None, True)
    surfaces = shown(error, caplog=caplog, capsys=capsys)
    assert (holding(KEY, surfaces), holding("madeup", surfaces)) == ([], [])


def test_audio_that_holds_a_boundary_line_adds_no_form_field() -> None:
    fake = FakeGroq()
    asyncio.run(call(fake, AudioClip(pcm16=PCM)))
    found = parts(fake.requests[0])
    assert list(found) == SENT_FIELDS
    assert INJECTED in found["file"][1]  # inside the WAV, as audio


def test_audio_that_holds_the_boundary_a_shell_line_chose_is_never_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_CUSTOM_HEADERS", "content-type: multipart/form-data; boundary=madeup")
    fake = FakeGroq()
    with pytest.raises(ProviderError, match="refused"):
        asyncio.run(call(fake, AudioClip(pcm16=PCM)))
    assert fake.requests == []
