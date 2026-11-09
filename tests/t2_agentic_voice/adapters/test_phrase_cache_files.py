"""The phrase cache's files (adapters/phrase_cache.py, plan 003's Track B): keyed by a hash of the
text sent, the model and the voice (the design's 10.4); written whole, to a temporary name then
renamed; a file that cannot be read made anew; nothing written for a take cut short, or with
`tts.cache_phrases` off. Against `FakeTextToSpeech`, in a test's own folder."""

from __future__ import annotations

import asyncio
import io
import wave
from pathlib import Path

import pytest
from t2_agentic_voice.adapters.phrase_cache import PhraseCache, phrase_key
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.tts import TtsModel, TtsSettings, TtsVoice
from t2_agentic_voice.domain.presets import NOTICES

from tests.t2_agentic_voice.adapters.phrase_support import (
    ENGLISH,
    GREETING,
    VOICES,
    declare,
    english,
    take,
    track_a,
)
from tests.t2_agentic_voice.fakes import FakeTextToSpeech

__all__ = ["track_a"]  # Track A's stand-ins, used by every test here too

ARABIC: TtsModel = "canopylabs/orpheus-arabic-saudi"


def test_the_key_changes_with_text_model_and_voice() -> None:
    voice = VOICES["en"]
    key = phrase_key("Made up.", voice)
    assert key == phrase_key("Made up.", TtsVoice(model=voice.model, voice=voice.voice))
    others = {
        phrase_key("Made up!", voice),
        phrase_key("Made up.", TtsVoice(model=ARABIC, voice=voice.voice)),
        phrase_key("Made up.", TtsVoice(model=voice.model, voice="another")),
    }
    assert key not in others and len(others) == 3
    assert len(key) == 32 and int(key, 16) >= 0


def _read(path: Path) -> tuple[int, int, int, bytes]:
    with wave.open(io.BytesIO(path.read_bytes()), "rb") as reader:
        return (
            reader.getnchannels(),
            reader.getsampwidth(),
            reader.getframerate(),
            reader.readframes(reader.getnframes()),
        )


def test_each_phrase_is_one_whole_wav_named_by_its_key(tmp_path: Path) -> None:
    fake = FakeTextToSpeech(sample_rate=22_050)
    declare(fake, tmp_path, english())
    files = sorted(path.name for path in tmp_path.iterdir())
    assert files == sorted(f"{phrase_key(text, VOICES['en'])}.wav" for text in ENGLISH)
    greeting = tmp_path / f"{phrase_key(GREETING, VOICES['en'])}.wav"
    assert _read(greeting) == (1, 2, 22_050, take(GREETING, fake))


def test_a_stopped_write_leaves_no_half_phrase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def stopped(self: Path, target: Path) -> Path:
        raise OSError("made-up: the disk went away")

    monkeypatch.setattr(Path, "replace", stopped)
    with pytest.raises(OSError, match="made-up"):
        declare(FakeTextToSpeech(), tmp_path, english())
    assert list(tmp_path.iterdir()) == []  # no phrase, and no temporary file left


@pytest.mark.parametrize(
    "junk",
    [
        b"",
        b"made-up, no WAV",
        b"RIFF\x24\x00\x00\x00WAVEfmt ",  # cut inside its header
        "stereo",
        "odd",
    ],
)
def test_a_file_that_cannot_be_read_is_made_anew(junk: bytes | str, tmp_path: Path) -> None:
    greeting = tmp_path / f"{phrase_key(GREETING, VOICES['en'])}.wav"
    declare(FakeTextToSpeech(), tmp_path, english())
    whole = greeting.read_bytes()
    if junk == "stereo":
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(24_000)
            writer.writeframes(b"\x00" * 400)
        junk = buffer.getvalue()
    elif junk == "odd":  # half a sample short: not whole samples
        junk = whole[:-1]
    assert isinstance(junk, bytes)
    greeting.write_bytes(junk)
    fake = FakeTextToSpeech()
    cache, sent = declare(fake, tmp_path, english())
    assert (sent, fake.calls) == (1, [(GREETING, "en")])
    assert greeting.read_bytes() == whole
    assert cache.audio(GREETING, language="en").pcm16 == take(GREETING, fake)


def test_a_take_cut_short_is_kept_flagged_but_never_written(tmp_path: Path) -> None:
    """The flag reaches `ClausePlayed` through the phrase's audio; the next start asks again."""
    fake = FakeTextToSpeech(cut_short={GREETING})
    cache, _ = declare(fake, tmp_path, english())
    assert cache.audio(GREETING, language="en").cut_short
    assert not cache.audio(NOTICES["en"]["ended"], language="en").cut_short
    assert len(list(tmp_path.iterdir())) == 4
    again = FakeTextToSpeech()
    cached, sent = declare(again, tmp_path, english())
    assert (sent, again.calls) == (1, [(GREETING, "en")])
    assert not cached.audio(GREETING, language="en").cut_short
    assert len(list(tmp_path.iterdir())) == 5


@pytest.mark.parametrize("cache_phrases", [True, False])
def test_the_settings_say_whether_files_are_kept(cache_phrases: bool, tmp_path: Path) -> None:
    """`tts.cache_phrases` off: each start synthesizes every phrase, reads no file and writes
    none."""
    settings = VoiceSettings(env="test", tts=TtsSettings(cache_phrases=cache_phrases))
    declare(FakeTextToSpeech(), tmp_path / "earlier", english())
    for start in range(2):
        fake = FakeTextToSpeech()
        cache = PhraseCache.from_settings(settings, fake, folder=tmp_path / "earlier")
        sent = asyncio.run(cache.declare(english()))
        assert sent == (0 if cache_phrases else 5), start
        assert cache.audio(GREETING, language="en").pcm16 == take(GREETING, fake)
    unkept = PhraseCache.from_settings(settings, FakeTextToSpeech(), folder=tmp_path / "new")
    asyncio.run(unkept.declare(english()))
    assert (tmp_path / "new").exists() is cache_phrases
