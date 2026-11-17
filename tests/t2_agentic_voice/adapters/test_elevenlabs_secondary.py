"""ElevenLabsSTT's secondary languages (D-115), against a fake ElevenLabs on httpx's
MockTransport: a clip's `other_languages` go as `secondary_language_codes`, one form field each,
but the one named as `language_code`; with no language named, all of them; none for a clip that
gives none, as every request but `stt.live_language = "hinted"`'s; and none to a model the API
reference does not say takes them."""

from __future__ import annotations

import asyncio

from pydantic import SecretStr
from t2_agentic_voice.adapters.elevenlabs_stt import SECONDARY_MODELS, ElevenLabsSTT
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip

from tests.t2_agentic_voice.adapters.provider_support import (
    CLIP,
    HEARD,
    KEY,
    FakeProvider,
    answering,
    texts,
)

ANSWER = {"text": HEARD, "language_code": "eng", "language_probability": 0.91}


def _sent(
    clip: AudioClip, *, language: str | None, model: str = "scribe_v3"
) -> dict[str, list[str]]:
    fake = FakeProvider(answering(200, ANSWER))

    async def go() -> None:
        stt = ElevenLabsSTT(
            api_key=SecretStr(KEY), timeout_s=5.0, model=model, transport=fake.transport()
        )
        try:
            await stt.transcribe(clip, language=language, prompt=None)
        finally:
            await stt.aclose()

    asyncio.run(go())
    (request,) = fake.requests
    return texts(request)


def _with(*others: str) -> AudioClip:
    return CLIP.model_copy(update={"other_languages": others})


def test_the_other_languages_go_as_secondary_codes_one_field_each() -> None:
    sent = _sent(_with("en", "fr"), language="ar")
    assert sent["language_code"] == ["ar"]
    assert sent["secondary_language_codes"] == ["en", "fr"]


def test_the_named_language_and_a_repeat_are_not_sent_again() -> None:
    sent = _sent(_with("ar", "en", "en"), language="ar")
    assert sent["secondary_language_codes"] == ["en"]


def test_with_no_language_named_every_other_language_goes() -> None:
    sent = _sent(_with("ar", "en"), language=None)
    assert "language_code" not in sent
    assert sent["secondary_language_codes"] == ["ar", "en"]


def test_a_clip_with_no_other_language_sends_none() -> None:
    """GP-18: every request but hinted's is as it was."""
    assert CLIP.other_languages == ()
    assert "secondary_language_codes" not in _sent(CLIP, language="ar")
    assert "secondary_language_codes" not in _sent(_with("ar"), language="ar")


def test_a_model_that_takes_no_secondary_codes_gets_none() -> None:
    assert {"scribe_v3"} == SECONDARY_MODELS
    assert "secondary_language_codes" not in _sent(_with("en"), language="ar", model="scribe_v2")
