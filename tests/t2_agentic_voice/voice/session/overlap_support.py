"""What the overlap tests share (plan 005's Track B): settings under `interruptions.mode =
"two_step"`, a fake of the starting rule, and a call whose echo plays when the caller speaks.

The rule is Track A's (domain/interruptions.py's `judge`), built in parallel, so these tests never
run it: `FakeRule` stands in for it, patched where the session calls it (overlap.py), and gives
each text the verdict a test scripts for it, so a test drives each verdict through the session.
The texts are written for the tests, none a golden item's.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.interruptions import Overlap, Verdict
from t2_agentic_voice.domain.words import Words
from t2_agentic_voice.voice.session.session_events import TranscriptPart

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import HEARD, greeted, turn

# The verdicts the rule gives, one of each step a test needs.
STOP = Verdict(action="stop", kind="stop", reason="stop_word")
NEW_WORDS = Verdict(action="stop", kind="new_words", reason="enough_words")
CORRECTION = Verdict(action="stop", kind="correction", reason="enough_words")
REPEAT = Verdict(action="repeat", kind="new_words", reason="repeat_word")
LISTENING = Verdict(action="go_on", kind="false", reason="listening")
OWN_WORDS = Verdict(action="go_on", kind="false", reason="own_words")
SHORT = Verdict(action="go_on", kind="false", reason="short_output")
NO_WORDS = Verdict(action="go_on", kind="false", reason="no_words")

# The caller's texts, written for these tests.
STOP_TEXT = "made-up halting phrase"
NEW_TEXT = "made-up fresh request of several words"
REPEAT_TEXT = "made-up asking it again"
LISTENING_TEXT = "made-up listening sound"
SHORT_TEXT = "made-up short"
FAILING_TEXT = "made-up text the rule fails on"  # the fake raises on it, as a bug would
SCRIPT: dict[str, Verdict] = {
    STOP_TEXT: STOP,
    NEW_TEXT: NEW_WORDS,
    REPEAT_TEXT: REPEAT,
    LISTENING_TEXT: LISTENING,
    SHORT_TEXT: SHORT,
}


def two_step(settings: VoiceSettings, **interruptions: Any) -> VoiceSettings:
    """`settings` under `interruptions.mode = "two_step"`, with any other bound given."""
    group = settings.interruptions.model_copy(update={"mode": "two_step", **interruptions})
    return settings.model_copy(update={"interruptions": group})


class FakeRule:
    """The starting rule as a test scripts it: the verdict `script` gives a text, RuntimeError
    for `FAILING_TEXT`, or, for any other, no words for an empty text and too few words
    otherwise; each overlap it judged is kept (`judged`), with the rest of what it was given
    (`given`)."""

    def __init__(self, script: Mapping[str, Verdict] = SCRIPT) -> None:
        self.script = dict(script)
        self.judged: list[Overlap] = []
        self.given: list[dict[str, Any]] = []

    def __call__(
        self,
        overlap: Overlap,
        *,
        words: Words,
        no_speech_max: float | None,
        captions: Collection[str],
        min_words: int,
        short_words: int,
        short_s: float,
    ) -> Verdict:
        self.judged.append(overlap)
        self.given.append(
            {
                "words": words,
                "no_speech_max": no_speech_max,
                "captions": tuple(captions),
                "bounds": (min_words, short_words, short_s),
            }
        )
        if overlap.text == FAILING_TEXT:
            raise RuntimeError(FAILING_TEXT)
        if overlap.text in self.script:
            return self.script[overlap.text]
        return (
            NO_WORDS
            if not overlap.text
            else Verdict(action="go_on", kind="false", reason="too_few_words")
        )

    @property
    def texts(self) -> list[str]:
        return [each.text for each in self.judged]


async def echo_playing(io: FakeSessionIO) -> None:
    """The call is greeted, the caller's turn 0 is heard, and its echo (reply 1: the cached
    frame, then the heard words) begins to play: its frame's first audio queued."""
    await greeted(io)
    await turn(io, 0, HEARD)
    await io.clause_queued(1, 0)
    await io.clock.advance(0.2)


async def overlap_part(
    io: FakeSessionIO,
    turn_id: int,
    text: str,
    *,
    part: TranscriptPart = "overlap",
    audio_s: float = 0.9,
) -> None:
    """The overlap's `part` (its window or its whole overlap) is asked for and heard."""
    await io.transcribing(turn_id, audio_s=audio_s, part=part)
    await io.clock.advance(0.2)
    await io.transcribed(turn_id, text, language="en", part=part)
