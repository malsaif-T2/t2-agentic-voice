"""Text from silence (plan 005's filter, rule F): words Whisper writes for audio that holds no
speech, which count as no words, for an overlap (domain/interruptions.py) and for a turn. A
transcript is text from silence when Whisper's probability that the audio holds no speech is
above `stt.no_speech_max` (unset: never), or when it is one of the captions Whisper invents for
silence or noise (`CAPTIONS`, used only under `stt.caption_filter`). Both are off by default
until the registered rule F sets them (GP-18); the scorers' own measure of text from silence is
domain/scoring.py's. Pure, with no IO.

The caption list is empty until plan 005's Track A writes it from the prototype's (its `stt.py`,
lines 35-54); until then `from_silence` raises.
"""

from __future__ import annotations

from collections.abc import Collection

# The captions Whisper invents for silence or noise, as written, matched whole after the
# canonical normalization.
CAPTIONS: tuple[str, ...] = ()


def from_silence(
    text: str,
    no_speech_prob: float | None,
    *,
    no_speech_max: float | None,
    captions: Collection[str],
) -> bool:
    """Whether `text`, with the provider's `no_speech_prob` (None when it gave none), is text
    from silence: the probability above `no_speech_max` (None: the threshold is off), or the
    text one of `captions` (empty: the list is off)."""
    raise NotImplementedError("the filter for text from silence is plan 005's Track A's to build")
