"""Whether the caller's speech over the agent's reply stops it (the design's 3.1; plan 005's "The
starting rule"): under `interruptions.mode = "two_step"`, the session judges each transcript of an
overlap with `judge`, its window's first, then its whole overlap's when the window did not stop
the agent. Pure, with no IO: the language's words (domain/words.py), the filter for text from
silence (domain/silence.py) and the `interruptions` group's bounds come in its arguments, so
domain reads no settings group.

The rule reads a transcript in the form its words are compared in (domain/words.py's
`rule_form`), as words, each listed phrase one word (the longest first, as the prototype read
an utterance: its `voice/rules.py`, lines 119-129), beside the fixed words of
domain/interruption_words.py. Its steps, in order:

1. no words, or text from silence: go on;
2. a stop word or a word asking the agent to pause, anywhere, or the stop word as Whisper
   mishears it over the agent's voice (`_noisy_stop`; a spelling only Whisper writes for it,
   only as a whole short utterance): stop; but go on, as the agent's own words, when each stop
   or wait word heard is, exactly, a word or listed phrase of the clauses that played (no edit
   allowed), another word was heard beside them, and every word is the agent's own (step 4's
   test): its echo of a reply that said them back;
3. a repeat request, its repeat words with only polite words and listening sounds beside them
   (a repeat word in a sentence, "read" or a feast's name, asks nothing): stop, then say the
   last reply again; unless each repeat word heard, or it after waw (and), is a word or listed
   phrase of the clauses that played, when the steps after this one decide;
4. the agent's own words, every word within one edit of a word of the clauses that played (a
   word of one or two letters only as written): go on;
5. listening sounds only: go on;
6. a short output, at most `short_words` words under `short_s` of speech, none a stop, wait,
   repeat or no word, asking no question (a question mark, or a question word first): go on, so
   a listening sound Whisper misheard does not stop the agent (plan 005, Q4);
7. at least `min_words` real words, a listening sound being none: stop, a correction when the
   first is a no word; fewer: go on.

Step 2's echo and its whole spellings, and step 3's exception, changed the registered rule on
2026-11-03, after Track A's review: the agent says back what it heard, so a reply can hold any
word the caller said.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from t2_agentic_voice.core.events import InterruptionKind, InterruptionReason
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.interruption_words import (
    NOISY_ENDS,
    NOISY_LETTERS,
    NOISY_SOUNDS,
    NOISY_SPELLINGS,
    NOISY_WORDS,
    NOT_NOISY_START,
    POLITE,
    QUESTION_MARKS,
    QUESTION_WORDS,
)
from t2_agentic_voice.domain.silence import from_silence
from t2_agentic_voice.domain.text.words import holds_words
from t2_agentic_voice.domain.words import WORD_KINDS, Words, rule_form

# What the session does with the reply an overlap spoke over: stop it, stop it and say the last
# reply again, or let it go on; the agent's voice comes back after each (io.py's overlaps).
OverlapAction = Literal["stop", "repeat", "go_on"]
# Which step of the rule decided, in its order: the `Interrupted` event's `reason`
# (core/events.py), one list for both.
VerdictReason = InterruptionReason

_AND = "\u0648"  # waw, and
# The shortest word the agent's own words match within one edit; a shorter one only as written.
_FUZZY_LETTERS = 3


class Overlap(BaseModel):
    """One transcript of an overlap, as the rule judges it: its `text`; the probability Whisper
    gave that the audio holds no speech (None when the provider gave none); `speech_s`, the
    seconds of speech it was taken from; `played`, the texts of the agent's clauses that played
    within `interruptions.own_words_s` and the one playing now, which its own voice heard back
    would say; and `language`, the call's primary code, whose words apply."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    no_speech_prob: float | None = Field(default=None, ge=0, le=1)
    speech_s: float = Field(ge=0, allow_inf_nan=False)
    played: tuple[str, ...] = ()
    language: LanguageCode


class Verdict(BaseModel):
    """What the rule decided for an overlap: its `action`; the `kind` of the `Interrupted` event
    a stop gives (`false` when the reply goes on); and the step that decided (`reason`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: OverlapAction
    kind: InterruptionKind
    reason: VerdictReason


def judge(
    overlap: Overlap,
    *,
    words: Words,
    no_speech_max: float | None,
    captions: Collection[str],
    min_words: int,
    short_words: int,
    short_s: float,
) -> Verdict:
    """The rule's verdict on `overlap`, with the call language's `words` (the agent's, a team's
    additions included), the filter for text from silence (`no_speech_max`, None for off, and
    the `captions` it counts as no words, none for off) and the rule's bounds."""
    if from_silence(
        overlap.text, overlap.no_speech_prob, no_speech_max=no_speech_max, captions=captions
    ):
        return _goes_on("no_words")
    heard = rule_form(overlap.text).split()
    spoken = [rule_form(text) for text in overlap.played]
    lists = _lists(words)
    tokens = _tokens(heard, lists)
    kinds = [lists.get(token, frozenset()) for token in tokens]
    questions = QUESTION_WORDS[overlap.language]
    stops = _of_kinds(tokens, kinds, "stop", "wait")
    echo = 0 < len(stops) < len(tokens) and _said_back(stops, spoken)
    if echo and _own_words(heard, spoken):
        return _goes_on("own_words")
    if stops or _noisy_stop(tokens, kinds, questions):
        return Verdict(action="stop", kind="stop", reason="stop_word")
    repeats = _of_kinds(tokens, kinds, "repeat")
    asked = bool(repeats) and all(kind & {"repeat", "polite", "backchannel"} for kind in kinds)
    if asked and not _said_back(repeats, spoken, after_and=True):
        return Verdict(action="repeat", kind="new_words", reason="repeat_word")
    if _own_words(heard, spoken):
        return _goes_on("own_words")
    if all("backchannel" in kind for kind in kinds):
        return _goes_on("listening")
    asks = any(mark in overlap.text for mark in QUESTION_MARKS)
    asks = asks or _opens_with_question(heard[0], questions)
    listed = _held(kinds, "stop", "wait", "repeat", "no")
    if len(tokens) <= short_words and overlap.speech_s < short_s and not (listed or asks):
        return _goes_on("short_output")
    real = [kind for kind in kinds if "backchannel" not in kind]
    if len(real) >= min_words:
        said: InterruptionKind = "correction" if "no" in real[0] else "new_words"
        return Verdict(action="stop", kind=said, reason="enough_words")
    return _goes_on("too_few_words")


def _goes_on(reason: VerdictReason) -> Verdict:
    """The verdict that lets the reply go on, for `reason`."""
    return Verdict(action="go_on", kind="false", reason=reason)


def _lists(words: Words) -> dict[str, frozenset[str]]:
    """Each phrase the rule reads, in its form, with the kinds that hold it: the five kinds of
    `words` (a word that says nothing in that form left out), `polite` and `noisy` (the
    spellings only Whisper writes for the stop word)."""
    held: dict[str, set[str]] = {}
    for kind in WORD_KINDS:
        for word in getattr(words, kind):
            if form := rule_form(word):
                held.setdefault(form, set()).add(kind)
    for kind, forms in (("polite", POLITE), ("noisy", NOISY_SPELLINGS)):
        for form in forms:
            held.setdefault(form, set()).add(kind)
    return {form: frozenset(kinds) for form, kinds in held.items()}


def _tokens(heard: Sequence[str], lists: Mapping[str, object]) -> list[str]:
    """`heard`'s words, each listed phrase one word, the longest that starts at a word first."""
    longest = max(len(phrase.split()) for phrase in lists)
    tokens: list[str] = []
    at = 0
    while at < len(heard):
        sizes = range(min(longest, len(heard) - at), 1, -1)
        size = next((size for size in sizes if " ".join(heard[at : at + size]) in lists), 1)
        tokens.append(" ".join(heard[at : at + size]))
        at += size
    return tokens


def _held(kinds: Iterable[frozenset[str]], *wanted: str) -> bool:
    """Whether a word of `kinds` is of one of the `wanted` kinds."""
    return any(kind.intersection(wanted) for kind in kinds)


def _of_kinds(tokens: Sequence[str], kinds: Sequence[frozenset[str]], *wanted: str) -> list[str]:
    """The words of `tokens` of one of the `wanted` kinds, `kinds` holding each one's."""
    return [token for token, kind in zip(tokens, kinds, strict=True) if kind.intersection(wanted)]


def _said_back(listed: Iterable[str], spoken: Sequence[str], *, after_and: bool = False) -> bool:
    """Whether each word or listed phrase of `listed` is, exactly, whole words of one of the
    `spoken` clauses (in the rule's form), or with `after_and` is too when written after waw
    (and): what the agent's echo of a reply that said it back holds."""
    starts = ("", _AND) if after_and else ("",)
    return all(
        any(holds_words(text, start + word) for text in spoken for start in starts)
        for word in listed
    )


def _noisy_stop(
    tokens: Sequence[str], kinds: Sequence[frozenset[str]], questions: Collection[str]
) -> bool:
    """Whether the words are the stop word as Whisper mishears it over the agent's voice: a
    spelling only Whisper writes for it (`NOISY_SPELLINGS`), with only polite words and
    listening sounds beside it; or one or two short Arabic words that end as it does or sound as
    it did (`NOISY_ENDS`, `NOISY_SOUNDS`), with no question or no word."""
    beside = all(kind & {"noisy", "polite", "backchannel"} for kind in kinds)
    if len(tokens) <= NOISY_WORDS and beside and _held(kinds, "noisy"):
        return True
    joined = "".join(token.replace(" ", "") for token in tokens)
    if len(tokens) > 2 or len(joined) > NOISY_LETTERS:
        return False
    if any(token in questions or "no" in kind for token, kind in zip(tokens, kinds, strict=True)):
        return False
    return joined in NOISY_SOUNDS or any(
        token in NOISY_SOUNDS
        or (token.endswith(NOISY_ENDS) and not token.startswith(NOT_NOISY_START))
        for token in tokens
    )


def _opens_with_question(first: str, questions: Collection[str]) -> bool:
    """Whether `first`, an output's first word, is a question word, or one after waw (and)."""
    return first in questions or (first.startswith(_AND) and first[1:] in questions)


def _own_words(heard: Sequence[str], spoken: Iterable[str]) -> bool:
    """Whether every word of `heard` is the agent's own: a word of the `spoken` clauses (in the
    rule's form), or one edit from one when it has at least `_FUZZY_LETTERS` letters."""
    said = {word for text in spoken for word in text.split()}
    return bool(said) and all(
        word in said
        or (len(word) >= _FUZZY_LETTERS and any(_one_edit(word, other) for other in said))
        for word in heard
    )


def _one_edit(first: str, second: str) -> bool:
    """Whether `first` becomes `second` by one letter changed, added or removed, or none."""
    if len(first) == len(second):
        return sum(a != b for a, b in zip(first, second, strict=True)) <= 1
    shorter, longer = sorted((first, second), key=len)
    if len(longer) - len(shorter) != 1:
        return False
    at = 0
    while at < len(shorter) and shorter[at] == longer[at]:
        at += 1
    return shorter[at:] == longer[at + 1 :]
