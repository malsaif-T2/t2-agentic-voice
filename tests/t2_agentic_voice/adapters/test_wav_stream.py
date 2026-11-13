"""A streamed WAV read whatever its chunk boundaries (adapters/wav_stream.py):
the audio in whole samples, the sample rate read from the header, the formats refused, and the
silence before the speech measured, and trimmed only with `trim` on. The prototype's
`WavStream` and `Trimmer` were read as specs, never run
(Ole5-chatbot/src/ole5_chat/voice/tts.py, lines 43-78 and 101-133)."""

from __future__ import annotations

import struct

import pytest
from t2_agentic_voice.adapters.wav_stream import WavError, WavStream

from tests.t2_agentic_voice.adapters.tts_support import (
    STREAMED,
    pieces,
    silence,
    tone,
    wav,
)

FRAME = 960 * 2  # 40 ms at 24 kHz, in bytes
# 0.48 s of silence (12 frames), then 0.5 s of speech, then 0.2 s of silence.
SPOKEN = silence(0.48) + tone(0.5) + silence(0.2)


def _read(stream: bytes, size: int, *, trim: bool = False) -> tuple[bytes, WavStream]:
    """`stream` fed in pieces of `size` bytes, then finished: the audio and the reader."""
    reader = WavStream(trim=trim)
    audio = b"".join(reader.feed(piece) for piece in pieces(stream, size))
    return audio + reader.finish(), reader


def test_any_cut_of_the_stream_gives_the_same_audio() -> None:
    """Groq's chunks split anywhere, a sample or a chunk's head included: every cut into two,
    and pieces of one byte to an odd size, give the audio whole, each piece in whole samples."""
    pcm = tone(0.05) + silence(0.01)
    stream = wav(pcm)
    for cut in range(len(stream) + 1):
        reader = WavStream()
        first, second = reader.feed(stream[:cut]), reader.feed(stream[cut:])
        assert (len(first) % 2, len(second) % 2) == (0, 0)
        assert first + second + reader.finish() == pcm, cut
    for size in (1, 3, 7, 4096):
        assert _read(stream, size)[0] == pcm


@pytest.mark.parametrize("rate", [8_000, 16_000, 22_050, 24_000, 48_000])
def test_the_sample_rate_is_read_never_assumed(rate: int) -> None:
    audio, reader = _read(wav(tone(0.1, rate), rate=rate), 5)
    assert (reader.sample_rate, len(audio)) == (rate, len(tone(0.1, rate)))
    assert reader.audio_s == pytest.approx(0.1, abs=1 / rate)


@pytest.mark.parametrize("data_size", [0, 4, STREAMED])
def test_every_byte_after_the_data_head_is_audio_whatever_its_size(data_size: int) -> None:
    """A WAV streamed before its length is known gives no true size (the prototype's reading)."""
    pcm = tone(0.1)
    assert _read(wav(pcm, data_size=data_size), 512)[0] == pcm


def test_chunks_before_the_audio_are_skipped_and_the_extensible_format_read() -> None:
    pcm = tone(0.02)
    chunks = ((b"LIST", b"odd"), (b"fact", b"\x00\x00\x00\x00"), (b"junk", b""))
    extensible = wav(pcm, tag=0xFFFE, fmt_extra=b"\x16\x00" + b"\x00" * 22, chunks=chunks)
    assert _read(extensible, 2)[0] == pcm


FMT = struct.pack("<HHIIHH", 1, 1, 24_000, 48_000, 2, 16)
REFUSED = [
    (b"RIFX" + wav(b"")[4:], "the answer is not a WAV stream"),
    (wav(b"")[:8] + b"AVI " + wav(b"")[12:], "the answer is not a WAV stream"),
    (wav(b"", channels=2), "the WAV stream is not mono 16-bit PCM"),
    (wav(b"", bits=8), "the WAV stream is not mono 16-bit PCM"),
    (wav(b"", bits=32, tag=3), "the WAV stream is not mono 16-bit PCM"),  # float
    (wav(b"", rate=0), "the WAV stream is not mono 16-bit PCM"),
    (b"RIFF\xff\xff\xff\xffWAVEfmt \x0e\x00\x00\x00" + FMT[:14], "format is cut short"),
    (b"RIFF\xff\xff\xff\xffWAVEdata\x00\x00\x00\x00", "audio came before its format"),
]


@pytest.mark.parametrize(("stream", "message"), REFUSED)
def test_a_stream_that_is_not_mono_16_bit_pcm_is_refused(stream: bytes, message: str) -> None:
    reader = WavStream()
    with pytest.raises(WavError) as raised:
        reader.feed(stream + tone(0.01))
    assert message in str(raised.value)
    assert "\\x" not in str(raised.value) and "RIFF" not in str(raised.value)  # no bytes shown


@pytest.mark.parametrize("cut", [0, 5, 12, 30, 44])
def test_a_stream_that_ends_before_its_audio_is_refused(cut: int) -> None:
    reader = WavStream()
    assert reader.feed(wav(tone(0.01))[:cut]) == b""
    with pytest.raises(WavError, match="ended before its audio"):
        reader.finish()
    with pytest.raises(WavError, match="not given its format"):
        WavStream().sample_rate  # noqa: B018 - the property's refusal
    assert (WavStream().audio_s, WavStream().leading_silence_s) == (0.0, None)


def test_half_a_sample_left_at_the_end_is_dropped() -> None:
    reader = WavStream()
    assert reader.feed(wav(b"\x01\x02\x03")) == b"\x01\x02"
    assert reader.finish() == b""


@pytest.mark.parametrize("size", [1, 333, FRAME, 65_536])
def test_untrimmed_the_audio_passes_as_it_comes_and_its_leading_silence_is_measured(
    size: int,
) -> None:
    audio, reader = _read(wav(SPOKEN), size)
    assert audio == SPOKEN
    assert reader.leading_silence_s == pytest.approx(0.48)
    assert reader.speech_s == pytest.approx(0.7)
    assert reader.audio_s == pytest.approx(1.18)


def test_untrimmed_the_first_audio_comes_before_any_speech() -> None:
    """With the trim off nothing is held back: the first piece of silence plays at once."""
    reader = WavStream()
    head = wav(b"")
    assert reader.feed(head + silence(0.01)) == silence(0.01)
    assert reader.leading_silence_s is None


@pytest.mark.parametrize("size", [1, 333, FRAME, 65_536])
def test_trimmed_the_silence_before_the_speech_is_dropped_but_its_last_40_ms(size: int) -> None:
    audio, reader = _read(wav(SPOKEN), size, trim=True)
    assert audio == SPOKEN[11 * FRAME :]  # the 12th silent frame kept, then the speech on
    assert reader.leading_silence_s == pytest.approx(0.48)
    assert reader.audio_s == pytest.approx(1.18)  # what was received, before the trim


def test_trimmed_a_hiss_under_the_floor_counts_as_silence() -> None:
    hissed = tone(0.2, level=100) + tone(0.2)  # about -50 dBFS, then speech
    audio, reader = _read(wav(hissed), 100, trim=True)
    assert audio == hissed[4 * FRAME :]
    assert reader.leading_silence_s == pytest.approx(0.2)


def test_trimmed_silence_alone_gives_no_audio_and_no_speech() -> None:
    audio, reader = _read(wav(silence(0.5)), 1000, trim=True)
    assert (audio, reader.leading_silence_s, reader.speech_s) == (b"", None, 0.0)
    assert reader.audio_s == pytest.approx(0.5)


@pytest.mark.parametrize("trim", [True, False])
def test_speech_only_in_the_last_part_of_a_frame_is_found_at_the_end(trim: bool) -> None:
    """The last piece is shorter than a frame: it is scanned once the stream has ended."""
    pcm = silence(0.08) + tone(0.01)  # two silent frames, then a quarter of one, loud
    audio, reader = _read(wav(pcm), 4096, trim=trim)
    assert audio == (pcm[FRAME:] if trim else pcm)
    assert reader.leading_silence_s == pytest.approx(0.08)
