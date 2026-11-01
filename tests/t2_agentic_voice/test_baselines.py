"""The baselines Tracks A and B are compared with (plan 002, Block 0, step 11) stay consistent:
the fixed clip rebuilds to the hash the Groq request records, and each row of the normalizer's
characterization table agrees with itself. What the tracks build is tested in their own files."""

from __future__ import annotations

import hashlib
import io
import json
import struct
import wave
from pathlib import Path
from typing import Any

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
