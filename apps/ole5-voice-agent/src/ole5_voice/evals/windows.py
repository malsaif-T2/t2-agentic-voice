"""The window measures: what the first 500, 750 or 1000 ms of a clip let a model hear (plan
002's registration, "Windows").

A window is cut from the start of a variant's first segment file, so it holds the detector's
300 ms of padding before speech. Each window's transcript is kept with its measures, taken
against the variant's reference: whether anything was heard, how many words, how many of them
match the reference's first words in order, and, for a reference of one word, whether the
window holds it. Words are counted after the canonical normalization; whether a run of heard
words says a one-word reference is the matcher's call, so the spelling guide's rulings hold
here as they do for a verdict.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ole5_voice.evals.runs import Window

Normalize = Callable[[str], str]
IsRight = Callable[[str, Sequence[str]], bool]  # a `Matcher.is_right`
# A window's measures, from the variant's reference, the window's ms, its text, and whether the
# text is the clip's own answer: `measure`, with a run's normalizer and matcher (`measurer`).
Measure = Callable[[str, int, str, bool], Window]


def leading_words(reference: str, heard: str) -> int:
    """How many of the reference's first words the window heard, in order: the length of the
    run of words both texts begin with, compared as written, so a caller normalizes both
    first."""
    count = 0
    for said, got in zip(reference.split(), heard.split(), strict=False):
        if said != got:
            break
        count += 1
    return count


def measure(
    reference: str,
    ms: int,
    text: str,
    *,
    reused: bool,
    normalize: Normalize,
    is_right: IsRight,
) -> Window:
    """The window of `ms` whose transcript is `text`, with its measures against `reference`.
    `reused` marks a window at least as long as its clip, whose text is the clip's own answer
    rather than a request of its own."""
    heard = normalize(text).split()
    said = normalize(reference).split()
    holds = None
    if len(said) == 1:
        # Any run of heard words the matcher takes for the reference: a word split in two, or
        # one written another way the spelling guide accepts, still counts.
        holds = any(
            is_right(" ".join(heard[start:end]), [reference])
            for start in range(len(heard))
            for end in range(start + 1, len(heard) + 1)
        )
    return Window(
        ms=ms,
        text=text,
        empty=not heard,
        words=len(heard),
        leading_words=leading_words(" ".join(said), " ".join(heard)),
        holds_word=holds,
        reused=reused,
    )


def measurer(normalize: Normalize, is_right: IsRight) -> Measure:
    """`measure`, with a run's normalizer and its matcher's `is_right`."""

    def measured(reference: str, ms: int, text: str, reused: bool) -> Window:
        return measure(reference, ms, text, reused=reused, normalize=normalize, is_right=is_right)

    return measured
