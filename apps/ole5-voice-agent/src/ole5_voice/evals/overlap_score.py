"""The scorer of `poe overlap` (plan 005's registration, the arm O): each overlap clip's verdict
judged against what its kind should do, its stop timed, and the run's numbers and targets.

**What each should do** (the registration's Data): a stop word or a word asking the agent to
pause (`stop_word`), a request of any kind, a confirmation or a correction over a reply stops
the agent; a repeat request stops it and says the last reply again; a listening sound, silence,
noise or the agent's own echo (`echo_only`) lets it go on (`EXPECTED`). A verdict is right when
its action is that; a clip whose speech opened no overlap, or that nothing decided, went on. The
set is every variant tagged `over-assistant` of a kind with an expected action, and every
variant of a kind the script records over a reply, or alone and the replay feeds over one
(`FED_OVER_REPLY`: its stop, repeat and listening items, its corrections, silence, noise and
the echo).

**The stop time**, for a variant that stopped the agent: from the owner's mark of its word's end
(the first of `turn_ends_ms`) to the last agent audio frame sent; with no mark, from the speech
detector's stop, reported apart. **The requests** that decide an overlap are its window's and its
whole overlap's; the turn's own, when one went, is spent but decides none. Medians and 90th
percentiles as plan 002 took them (type 7, `scorecard.quantile`), by kind, language and device,
and in a dev run by item (overlap_card.py, the scorecard). A held-out run's numbers are
aggregates only (`HELD_OUT_MIN_ITEMS`), as `poe eot`'s are, and a target over fewer items is
withheld.

**The targets** (the registration's, Q3; `targets`): at most 2 requests decide any overlap; on
the marked stop words that stopped, a median of at most 700 ms, a 90th percentile of at most
1,000 ms and none over 1,500 ms; at least 90% of the stop words, and of the requests over a
reply, stop the agent; at most 10% of the listening sounds do, and no silence, noise or echo.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Final, Literal

from pydantic import Field

from ole5_voice.evals.models import Device, Kind, Language, Model, Name, Split
from ole5_voice.evals.runs import HELD_OUT_MIN_ITEMS
from ole5_voice.evals.scorecard import quantile

# What the session does with the reply a clip spoke over (the library's `OverlapAction`).
Action = Literal["stop", "repeat", "go_on"]
# Which of a turn's speech-to-text requests one was (the library's `RequestPart`).
Part = Literal["window", "overlap", "turn"]
OVER_ASSISTANT: Final = "over-assistant"  # the tag of a take that began over the assistant
EXPECTED: Final[dict[str, Action]] = {
    "stop_word": "stop",
    "request": "stop",
    "short_request": "stop",
    "paused_request": "stop",
    "ticket_number": "stop",
    "confirmation": "stop",
    "correction": "stop",
    "repeat_request": "repeat",
    "listening_sound": "go_on",
    "silence": "go_on",
    "noise": "go_on",
    "echo_only": "go_on",
}
FED_OVER_REPLY: Final = frozenset(
    {
        "stop_word",
        "repeat_request",
        "listening_sound",
        "correction",
        "silence",
        "noise",
        "echo_only",
    }
)
_STOP_WORDS: Final = frozenset({"stop_word"})
_REQUESTS: Final = frozenset(k for k, a in EXPECTED.items() if a != "go_on") - _STOP_WORDS
_QUIET: Final = frozenset({"silence", "noise", "echo_only"})
_LISTENING: Final = frozenset({"listening_sound"})


def in_set(kind: str, tags: Collection[str]) -> bool:
    """Whether a variant of an item of `kind`, tagged `tags`, is an overlap clip of the set."""
    return kind in EXPECTED and (OVER_ASSISTANT in tags or kind in FED_OVER_REPLY)


class Heard(Model):
    """One speech-to-text request of a clip's call (the library's `OverlapRequest`), in ms from
    the clip's start, kept so a revised rule is scored again offline."""

    part: Part
    sent_ms: float
    answered_ms: float | None = None
    audio_s: float = Field(ge=0)
    text: str | None = None
    no_speech_prob: float | None = Field(default=None, ge=0, le=1)
    failure: str | None = None


class Verdict(Model):
    """What came of a clip over a reply, as its answerer gave it (the library's
    `OverlapReplay`): whether an overlap opened, the verdict and the part that decided it, every
    request, and when the speech stopped and the agent's last audio frame was sent."""

    opened: bool
    action: Action | None = None
    kind: str | None = None  # the `Interrupted` event's kind
    reason: str | None = None  # the rule's step
    decided_by: Part | None = None
    requests: tuple[Heard, ...] = ()
    speech_stop_ms: float | None = None
    last_audio_ms: float | None = None


class Judged(Model):
    """A verdict judged: whether it is its kind's action, whether the agent stopped, how many
    requests decided the overlap, and, for a stop, its time from the mark or, with none, from
    the speech detector's stop."""

    right: bool
    stopped: bool
    overlap_requests: int = Field(ge=0)
    from_mark_ms: float | None = None
    from_detector_ms: float | None = None


def judge(expected: Action, verdict: Verdict, word_end_ms: float | None) -> Judged:
    """`verdict` judged against `expected`, its stop timed from `word_end_ms` when marked."""
    action = verdict.action if verdict.opened and verdict.action is not None else "go_on"
    stopped, last, speech_stop = action != "go_on", verdict.last_audio_ms, verdict.speech_stop_ms
    from_mark = from_detector = None
    if stopped and last is not None:
        if word_end_ms is not None:
            from_mark = last - word_end_ms
        elif speech_stop is not None:
            from_detector = last - speech_stop
    return Judged(
        right=action == expected,
        stopped=stopped,
        overlap_requests=sum(request.part != "turn" for request in verdict.requests),
        from_mark_ms=from_mark,
        from_detector_ms=from_detector,
    )


class OverlapResult(Model):
    """One clip of an overlap run: its strata, what it should do, the reply it was played over
    (`reply_known`: the texts that played over it in its recording, else a text no clip holds),
    its mark, how many calls it took (a rate limit's, run again), its verdict and its judging."""

    item: Name
    variant: Name
    split: Split
    kind: Kind
    language: Language
    device: Device
    expected: Action
    reply: tuple[str, ...] = Field(min_length=1)
    reply_known: bool
    word_end_ms: float | None = None
    attempts: int = Field(default=1, ge=1)
    verdict: Verdict
    judged: Judged


class OverlapMetrics(Model):
    """The numbers of a set of clips: its items and variants, those right; those that should
    stop and those that did, those that should go on and those that stopped; the most requests
    that decided an overlap and their mean over the overlaps; and the stop times, from the mark
    and from the detector, each's count, median and 90th percentile (the mark's also its
    largest)."""

    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    right: int = Field(ge=0)
    should_stop: int = Field(ge=0)
    stopped: int = Field(ge=0)
    should_go_on: int = Field(ge=0)
    false_stops: int = Field(ge=0)
    requests_max: int | None = None
    requests_mean: float | None = None
    marked: int = Field(ge=0)
    marked_median_ms: float | None = None
    marked_p90_ms: float | None = None
    marked_max_ms: float | None = None
    detected: int = Field(ge=0)
    detected_median_ms: float | None = None
    detected_p90_ms: float | None = None


def metrics(results: Sequence[OverlapResult]) -> OverlapMetrics:
    """The numbers of `results`."""
    stop = [r for r in results if r.expected != "go_on"]
    go_on = [r for r in results if r.expected == "go_on"]
    counts = [r.judged.overlap_requests for r in results if r.verdict.opened]
    marked = sorted(r.judged.from_mark_ms for r in results if r.judged.from_mark_ms is not None)
    detected = sorted(
        r.judged.from_detector_ms for r in results if r.judged.from_detector_ms is not None
    )
    return OverlapMetrics(
        items=len({r.item for r in results}),
        variants=len(results),
        right=sum(r.judged.right for r in results),
        should_stop=len(stop),
        stopped=sum(r.judged.stopped for r in stop),
        should_go_on=len(go_on),
        false_stops=sum(r.judged.stopped for r in go_on),
        requests_max=max(counts, default=None),
        requests_mean=sum(counts) / len(counts) if counts else None,
        marked=len(marked),
        marked_median_ms=quantile(marked, 0.5),
        marked_p90_ms=quantile(marked, 0.9),
        marked_max_ms=marked[-1] if marked else None,
        detected=len(detected),
        detected_median_ms=quantile(detected, 0.5),
        detected_p90_ms=quantile(detected, 0.9),
    )


class Target(Model):
    """One target of the registration: its value on the run, over `items` items, its bound,
    and whether it holds (None when no clip, or in a held-out run too few items, give it)."""

    name: Name
    items: int = Field(ge=0)
    value: float | None
    bound: float
    at_most: bool  # the value holds at or under the bound; else at or over it
    holds: bool | None


def targets(results: Sequence[OverlapResult], *, held_out: bool) -> tuple[Target, ...]:
    """The registration's targets on `results`."""

    def of(kinds: Collection[str] | None) -> list[OverlapResult]:
        return [r for r in results if kinds is None or r.kind in kinds]

    def share(group: Sequence[OverlapResult]) -> float | None:
        return sum(r.judged.stopped for r in group) / len(group) if group else None

    words = metrics(of(_STOP_WORDS))
    rows: list[tuple[str, list[OverlapResult], float | None, float, bool]] = [
        ("requests_per_overlap", of(None), _float(metrics(of(None)).requests_max), 2, True),
        ("stop_word_median_ms", of(_STOP_WORDS), words.marked_median_ms, 700, True),
        ("stop_word_p90_ms", of(_STOP_WORDS), words.marked_p90_ms, 1000, True),
        ("stop_word_max_ms", of(_STOP_WORDS), words.marked_max_ms, 1500, True),
        ("stop_words_heard", of(_STOP_WORDS), share(of(_STOP_WORDS)), 0.9, False),
        ("requests_heard", of(_REQUESTS), share(of(_REQUESTS)), 0.9, False),
        ("listening_false_stops", of(_LISTENING), share(of(_LISTENING)), 0.1, True),
        ("quiet_false_stops", of(_QUIET), _float(metrics(of(_QUIET)).false_stops), 0, True),
    ]
    found = []
    for name, group, value, bound, at_most in rows:
        items = len({r.item for r in group})
        if (held_out and items < HELD_OUT_MIN_ITEMS) or not group:
            value = None
        holds = None if value is None else (value <= bound if at_most else value >= bound)
        found.append(
            Target(name=name, items=items, value=value, bound=bound, at_most=at_most, holds=holds)
        )
    return tuple(found)


def _float(value: int | None) -> float | None:
    return None if value is None else float(value)
