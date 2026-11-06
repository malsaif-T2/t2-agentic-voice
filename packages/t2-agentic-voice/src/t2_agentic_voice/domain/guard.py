"""The output guard's ID rule (the design's 8.2, rule B; plan 006): a pure function with no IO,
run on every clause the talker writes before it goes to text-to-speech, and on a card's text
before it is shown. The runtime's own templates (greetings, notices, progress lines, fixed
phrases) are never checked.

What `check_ids` does, for the track that builds it:

- **Normalize first:** the canonical Arabic normalizer (domain/text/arabic.py), Arabic-Indic and
  Persian digits made ASCII, and runs of digit words in Arabic and English («أربعة خمسة اثنين
  واحد», "four five two one") collapsed into digits (domain/text/digits.py). The prompt tells
  the talker to write numbers as digits, and the speaking rules turn them into words after the
  guard, so the guard sees digits.
- **ID-shaped** is a run of `guard.min_id_digits` digits or more after normalizing, or a match
  of one of `guard.id_patterns`.
- **Evidence:** each ID-shaped token passes only when it appears in the evidence seen this call:
  the call's record, the results of its tools (passages included) and the caller's own heard
  words, normalized the same way. The current year and the next (`year`, `year + 1`) pass with
  none, since the prompt holds the current date.
- **The verdict:** `IdVerdict(passed=True)` when every token passes; otherwise not passed, with
  the tokens that had no evidence, which go to the talker's history as a developer note and
  never to the caller. What a blocked clause drops is `guard.on_block`'s, and the session's
  (a fixed phrase, a `GuardBlocked` event).

Claims (rule A) and the text after an action call (rule C) come with the actions.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.settings.guard import GuardSettings


class IdVerdict(BaseModel):
    """What rule B made of a clause: whether it `passed`, and when not, the ID-shaped tokens it
    holds with no evidence (`unsupported`), as normalized."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    unsupported: tuple[str, ...] = ()


def check_ids(
    clause: str, *, evidence: Iterable[str], settings: GuardSettings, year: int
) -> IdVerdict:
    """Rule B on `clause`: every ID-shaped token in it must appear in `evidence`, the texts seen
    this call that may hold one (the record, the tools' results, the caller's heard words), or
    be `year` or the next (the module's docstring)."""
    raise NotImplementedError("the guard's ID rule is plan 006's Track B")
