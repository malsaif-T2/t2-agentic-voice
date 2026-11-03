"""What the interruption rule's tests share (test_interruptions.py, test_interruptions_echo.py):
the rule's verdict on a text as (action, kind, reason), with a preset's words and the
`interruptions` group's defaults, and the verdicts they expect. Nothing here is a golden-set
item's."""

from __future__ import annotations

from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.interruptions import Overlap, VerdictReason, judge
from t2_agentic_voice.domain.words import PRESET_WORDS, Words

STOP = ("stop", "stop", "stop_word")
REPEAT = ("repeat", "new_words", "repeat_word")
NEW_WORDS = ("stop", "new_words", "enough_words")
CORRECTION = ("stop", "correction", "enough_words")


def went_on(reason: VerdictReason) -> tuple[str, str, str]:
    return ("go_on", "false", reason)


def judged(
    text: str,
    language: LanguageCode = "en",
    *,
    speech_s: float = 2.0,
    played: tuple[str, ...] = (),
    words: Words | None = None,
    no_speech_prob: float | None = None,
    no_speech_max: float | None = None,
    captions: tuple[str, ...] = (),
    min_words: int = 2,
) -> tuple[str, str, str]:
    """The rule's verdict on `text`, as (action, kind, reason), with the preset's words of
    `language` unless `words` are given, and the `interruptions` group's defaults."""
    overlap = Overlap(
        text=text,
        no_speech_prob=no_speech_prob,
        speech_s=speech_s,
        played=played,
        language=language,
    )
    found = judge(
        overlap,
        words=words or PRESET_WORDS[language],
        no_speech_max=no_speech_max,
        captions=captions,
        min_words=min_words,
        short_words=2,
        short_s=1.6,
    )
    return (found.action, found.kind, found.reason)
