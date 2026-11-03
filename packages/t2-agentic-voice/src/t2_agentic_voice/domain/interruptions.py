"""Whether the caller's speech over the agent's reply stops it (the design's 3.1; plan 005's "The
starting rule"): under `interruptions.mode = "two_step"`, the session judges each transcript of an
overlap with `judge`, its window's first, then its whole overlap's when the window did not stop
the agent. Pure, with no IO: the language's words (domain/words.py), the filter for text from
silence (domain/silence.py) and the `interruptions` group's bounds come in its arguments, so
domain reads no settings group.

The rule reads a transcript in the form its words are compared in (domain/words.py's
`rule_form`), as words, each listed phrase one word (the longest first, as the prototype read
an utterance: its `voice/rules.py`, lines 119-129). Its steps, in order:

1. no words, or text from silence: go on;
2. a stop word or a word asking the agent to pause, anywhere, or the stop word as Whisper
   mishears it over the agent's voice (`_noisy_stop`): stop;
3. a repeat request, its repeat words with only polite words and listening sounds beside them
   (a repeat word in a sentence, "read" or a feast's name, asks nothing): stop, then say the
   last reply again;
4. the agent's own words, every word within one edit of a word of the clauses that played (a
   word of one or two letters only as written): go on;
5. listening sounds only: go on;
6. a short output, at most `short_words` words under `short_s` of speech, none a stop, wait,
   repeat or no word, asking no question (a question mark, or a question word first): go on, so
   a listening sound Whisper misheard does not stop the agent (plan 005, Q4);
7. at least `min_words` real words, a listening sound being none: stop, a correction when the
   first is a no word; fewer: go on.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from t2_agentic_voice.core.events import InterruptionKind, InterruptionReason
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.silence import from_silence
from t2_agentic_voice.domain.words import WORD_KINDS, Words, rule_form

# What the session does with the reply an overlap spoke over: stop it, stop it and say the last
# reply again, or let it go on; the agent's voice comes back after each (io.py's overlaps).
OverlapAction = Literal["stop", "repeat", "go_on"]
# Which step of the rule decided, in its order: the `Interrupted` event's `reason`
# (core/events.py), one list for both.
VerdictReason = InterruptionReason

# The words that make an output a question when it opens with one (or with one after waw, and),
# for each language, in the rule's form: the prototype's (rules.py, lines 312-326). Not a kind
# of `Words`: a team's lists stay the five kinds.
_QUESTION_WORDS: Mapping[LanguageCode, frozenset[str]] = {
    "ar": frozenset(
        {
            "\u0643\u064a\u0641",  # kaif, how: kaf, yeh, feh
            "\u0645\u0627\u0630\u0627",  # matha, what: meem, alef, thal, alef
            "\u0644\u0645\u0627\u0630\u0627",  # limatha, why: lam, then as above
            "\u0644\u064a\u0634",  # laish, why (Saudi): lam, yeh, sheen
            "\u0644\u064a\u0647",  # laih, why: lam, yeh, heh
            "\u0645\u062a\u064a",  # mata, when: meem, teh, yeh
            "\u0648\u064a\u0646",  # wain, where (Saudi): waw, yeh, noon
            "\u0627\u064a\u0646",  # ain, where: alef, yeh, noon
            "\u0641\u064a\u0646",  # fain, where: feh, yeh, noon
            "\u0647\u0644",  # hal, is it: heh, lam
            "\u0627\u064a\u0634",  # aish, what: alef, yeh, sheen
            "\u0648\u0634",  # wish, what (Saudi): waw, sheen
            "\u0634\u0648",  # shu, what: sheen, waw
            "\u0634\u0644\u0648\u0646",  # shlon, how (Saudi): sheen, lam, waw, noon
            "\u0643\u0645",  # kam, how many: kaf, meem
            "\u0645\u064a\u0646",  # meen, who: meem, yeh, noon
            "\u0645\u0645\u0643\u0646",  # mumkin, can (you): meem, meem, kaf, noon
        }
    ),
    "en": frozenset(
        {"how", "what", "why", "where", "when", "which", "who", "can", "could", "would"}
        | {"is", "are", "do", "does", "did", "should", "will"}
    ),
}
_QUESTION_MARKS = ("?", "\u061f")  # the question mark, and the Arabic one
_AND = "\u0648"  # waw, and
# Polite words, which may stand beside a repeat request or the stop word's English spellings
# (below) without changing it: the prototype's (rules.py, line 75), but its listening sounds,
# which the lists hold. Of both languages, in the rule's form.
_POLITE = frozenset(
    {
        # law samaht, please: lam, waw; seen, meem, hah, teh
        "\u0644\u0648 \u0633\u0645\u062d\u062a",
        # min fadlak, please: meem, noon; feh, dad, lam, kaf
        "\u0645\u0646 \u0641\u0636\u0644\u0643",
        "\u064a\u0627",  # ya (calling someone): yeh, alef
        "\u0627\u0644\u062d\u064a\u0646",  # al-heen, now (Saudi): alef, lam, hah, yeh, noon
        "please",
        "now",
    }
)
# The stop word as Whisper wrote it over the agent's voice in the prototype's Arabic calls (its
# rules.py, lines 49-62 and 154-168): one or two words of at most six letters, together, one of
# them ending as the word does or one of the sounds below, the first letter of none meem (a noun
# or a participle, never the verb), with no question or no word.
_NOISY_ENDS = (
    "\u0642\u0641",  # qaf, feh
    "\u0643\u0641",  # kaf, feh
    "\u063a\u0641",  # ghain, feh
)
_NOISY_SOUNDS = frozenset(
    {
        "\u0628\u0648\u062f\u0643\u064a\u0641",  # beh, waw, dal, kaf, yeh, feh
        "\u0628\u0627\u0643\u064a\u0641",  # beh, alef, kaf, yeh, feh (also two words, joined)
        "\u0642\u062f\u0641",  # qaf, dal, feh
    }
)
_NOISY_LETTERS = 6
_NOT_NOISY_START = "\u0645"  # meem
# The stop word as Whisper wrote it in the prototype's English calls: a stop said with only
# polite words and listening sounds beside it, at most three words in all.
_NOISY_ENGLISH = frozenset({"what a gift", "what gives", "what give", "plug if", "waqif", "waqef"})
_NOISY_ENGLISH_WORDS = 3
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
    lists = _lists(words)
    tokens = _tokens(heard, lists)
    kinds = [lists.get(token, frozenset()) for token in tokens]
    questions = _QUESTION_WORDS[overlap.language]
    if _held(kinds, "stop", "wait") or _noisy_stop(tokens, kinds, questions):
        return Verdict(action="stop", kind="stop", reason="stop_word")
    if _held(kinds, "repeat") and all(kind & {"repeat", "polite", "backchannel"} for kind in kinds):
        return Verdict(action="repeat", kind="new_words", reason="repeat_word")
    if _own_words(heard, overlap.played):
        return _goes_on("own_words")
    if all("backchannel" in kind for kind in kinds):
        return _goes_on("listening")
    asks = any(mark in overlap.text for mark in _QUESTION_MARKS)
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
    `words` (a word that says nothing in that form left out), `polite` and `noisy` (the stop
    word's English spellings)."""
    held: dict[str, set[str]] = {}
    for kind in WORD_KINDS:
        for word in getattr(words, kind):
            if form := rule_form(word):
                held.setdefault(form, set()).add(kind)
    for kind, forms in (("polite", _POLITE), ("noisy", _NOISY_ENGLISH)):
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


def _noisy_stop(
    tokens: Sequence[str], kinds: Sequence[frozenset[str]], questions: Collection[str]
) -> bool:
    """Whether the words are the stop word as Whisper mishears it over the agent's voice: an
    English spelling of it, with polite words and listening sounds beside it; or one or two
    short Arabic words that end as it does or sound as it did (`_NOISY_ENDS`, `_NOISY_SOUNDS`),
    with no question or no word."""
    beside = all(kind & {"noisy", "polite", "backchannel"} for kind in kinds)
    if len(tokens) <= _NOISY_ENGLISH_WORDS and beside and _held(kinds, "noisy"):
        return True
    joined = "".join(token.replace(" ", "") for token in tokens)
    if len(tokens) > 2 or len(joined) > _NOISY_LETTERS:
        return False
    if any(token in questions or "no" in kind for token, kind in zip(tokens, kinds, strict=True)):
        return False
    return joined in _NOISY_SOUNDS or any(
        token in _NOISY_SOUNDS
        or (token.endswith(_NOISY_ENDS) and not token.startswith(_NOT_NOISY_START))
        for token in tokens
    )


def _opens_with_question(first: str, questions: Collection[str]) -> bool:
    """Whether `first`, an output's first word, is a question word, or one after waw (and)."""
    return first in questions or (first.startswith(_AND) and first[1:] in questions)


def _own_words(heard: Sequence[str], played: Iterable[str]) -> bool:
    """Whether every word of `heard` is the agent's own: a word of the `played` clauses, or one
    edit from one when it has at least `_FUZZY_LETTERS` letters."""
    said = {word for text in played for word in rule_form(text).split()}
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
