"""The baselines the code is compared with stay consistent: plan 002's (step 11),
whose fixed clip rebuilds to the hash the Groq request records and whose normalizer table agrees
with itself row by row; and plan 003's speech request (step 11), which holds the fields
the plan registers and is what the installed groq SDK sends for them, through the client every
Groq adapter builds. The code compared with them is tested in its own files."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import struct
import wave
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_client import groq_client, own_headers
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.tts import TtsSettings

from tests.t2_agentic_voice.adapters.groq_support import KEY, FakeGroq

FIXTURES = Path(__file__).parent / "fixtures"
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _load(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return loaded


def test_the_groq_request_baseline_rebuilds_from_its_clip() -> None:
    baseline = _load("groq_stt_request.json")
    clip, request = baseline["clip"], baseline["request"]
    pcm = b"".join(struct.pack("<h", (i * 97) % 4096 - 2048) for i in range(clip["samples"]))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(clip["sample_rate"])
        writer.writeframes(pcm)
    wav = buffer.getvalue()
    assert hashlib.sha256(pcm).hexdigest() == clip["pcm16_sha256"]
    assert (len(wav), hashlib.sha256(wav).hexdigest()) == (clip["wav_bytes"], clip["wav_sha256"])
    assert (request["file"]["bytes"], request["file"]["sha256"]) == (len(wav), clip["wav_sha256"])


def test_the_groq_request_baseline_sends_what_the_plan_registers() -> None:
    baseline = _load("groq_stt_request.json")
    call, client, request = baseline["call"], baseline["client"], baseline["request"]
    assert request["fields"] == {
        "model": call["settings"]["stt.model"],
        "language": call["language"],
        "response_format": "verbose_json",
        "temperature": "0",
    }
    assert call["prompt"] is None and "prompt" in request["absent_fields"]
    assert (request["file"]["filename"], request["file"]["content_type"]) == (
        "speech.wav",
        "audio/wav",
    )
    assert request["url"] == f"{client['base_url']}/openai/v1/audio/transcriptions"
    assert (client["max_retries"], client["timeout_s"]) == (0, call["settings"]["stt.timeout_s"])


def test_the_speech_baseline_sends_what_the_plan_registers() -> None:
    baseline = _load("groq_tts_request.json")
    call, client, request = baseline["call"], baseline["client"], baseline["request"]
    settings, language = call["settings"], call["language"]
    voice = settings[f"tts.languages.{language}"]
    assert request["json"] == {
        "input": call["text"],
        "model": voice["model"],
        "voice": voice["voice"],
        "response_format": "wav",
    }
    assert 0 < len(call["text"]) <= 200  # the Orpheus models' limit (plan 003, step 11)
    assert not set(request["absent_fields"]) & set(request["json"])
    body = request["body"].encode("utf-8")
    assert json.loads(body) == request["json"]
    assert list(json.loads(body)) == list(request["json"])  # the SDK's order of the fields
    assert (len(body), hashlib.sha256(body).hexdigest()) == (
        request["body_bytes"],
        request["body_sha256"],
    )
    assert request["url"] == f"{client['base_url']}/openai/v1/audio/speech"
    assert (client["max_retries"], client["timeout_s"]) == (0, settings["tts.timeout_s"])
    defaults = TtsSettings()  # the baseline's settings are the defaults
    assert defaults.languages[language].model_dump() == voice
    assert (GroqSettings().base_url, defaults.timeout_s) == (
        settings["groq.base_url"],
        settings["tts.timeout_s"],
    )


def test_the_installed_sdk_sends_the_speech_baseline() -> None:
    """The baseline is what groq 1.7.0 sends for its fields, through the shared client with a
    JSON adapter's hook, as GroqTTS builds it: the method, the URL and the body, byte for byte;
    the Accept and Content-Type headers the SDK sets itself, read before the adapter's hook
    replaces them; and those the hook then sends."""
    baseline = _load("groq_tts_request.json")
    client, request = baseline["client"], baseline["request"]
    fake = FakeGroq(httpx.Response(200, content=b"RIFF"))
    built: list[httpx.Headers] = []  # the SDK's own headers, before the adapter's hook

    async def speak() -> None:
        own = own_headers(
            SecretStr(KEY),
            accept=request["accept"].encode(),
            content_type=request["content_type"].encode(),
            opens_with=b"{",
            refusal="foreign_body",
        )

        async def hook(sent: httpx.Request) -> None:
            built.append(httpx.Headers(sent.headers))
            await own(sent)

        api = groq_client(
            api_key=SecretStr(KEY),
            base_url=client["base_url"],
            timeout_s=client["timeout_s"],
            hook=hook,
            transport=fake,
        )
        fields = request["json"]
        try:
            await api.audio.speech.create(
                model=fields["model"],
                voice=fields["voice"],
                input=fields["input"],
                response_format=fields["response_format"],
            )
        finally:
            await api.close()

    asyncio.run(speak())
    (sdk,), (sent,) = built, fake.requests
    assert (sent.method, str(sent.url)) == (request["method"], request["url"])
    assert sent.content == request["body"].encode("utf-8")
    assert (sdk["accept"], sdk["content-type"]) == (request["accept"], request["content_type"])
    assert (sent.headers["accept"], sent.headers["content-type"]) == (
        request["accept"],
        request["content_type"],
    )


def test_each_characterization_row_agrees_with_itself() -> None:
    rows = _load("arabic_normalizer_characterization.json")["rows"]
    assert len(rows) >= 30
    assert len({row["input"] for row in rows}) == len(rows)
    for row in rows:
        assert set(row) <= {"input", "normalize", "norm", "note", "gap"}, row
        assert row["norm"] == row["normalize"].translate(DIGITS).replace(" ", ""), row
        assert row["normalize"] == " ".join(row["normalize"].split()), row
    # Q8 rules otherwise than the prototype only on digits said one by one; it folds only the
    # prototype's letter forms, so no other row is a gap.
    gaps = [row["gap"] for row in rows if "gap" in row]
    assert gaps == ["digits spelled out", "digits spelled out"]
