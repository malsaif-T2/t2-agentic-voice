"""What a run produces: its requests, answers and window measures, a variant's result, the
metrics, the run itself, its scorecard and its history line; and the protocols one part calls in
another (the answerer, the matcher, the scorecard writer). Built on `models.py`'s field types,
and as strict: a scorecard read back, by `eval-compare` or a person, is checked as it is read.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final, Literal, Protocol, Self

from pydantic import AfterValidator, Field, model_validator

from ole5_voice.evals.models import (
    Commit,
    Device,
    Kind,
    Language,
    Model,
    Name,
    Other,
    Sha256,
    Split,
    Variant,
)

# How one request ended: answered, a provider's failure (the library's ProviderError kinds), or
# still running at the variant's wall-clock limit.
Outcome = Literal[
    "ok", "rate_limited", "timeout", "connection_lost", "server_error", "rejected", "stuck"
]
# The scorecard's file name in a run's `--out` folder, which its history line names.
SCORECARD_FILE: Final = "scorecard.json"
# In a held-out run's scorecard, history line and comparison, a breakdown value or window group
# that covers fewer answered items than this is pooled into one group, `models.OTHER`, itself
# left out when it too covers fewer, and a rate of a group shown that is taken over fewer items
# is left out, so no held-out item's numbers are published alone (plan 002's registration,
# "Amendments", 2026-11-01). The totals are whole.
HELD_OUT_MIN_ITEMS: Final = 3
# A setting that holds a secret, by its dotted name (`groq.api_key`).
_SECRET_SETTING = re.compile(r"(^|[._])(api_key|key|secret|token|password)$")
# An install placeholder, an uppercase name between double braces, as the docs check finds one
# (`scripts/check_docs.py`, DOC-PLACEHOLDER) in every committed file, `history.jsonl` included.
_PLACEHOLDER = re.compile(r"\{\{[A-Z][A-Z0-9_]*\}\}")


def holds_placeholder(text: str) -> bool:
    """Whether `text` holds an install placeholder, which nothing in a run's history may."""
    return _PLACEHOLDER.search(text) is not None


def _no_placeholder(text: str) -> str:
    if holds_placeholder(text):
        raise ValueError("holds an install placeholder, which the docs check refuses in history")
    return text


def _shown(value: dict[str, str]) -> dict[str, str]:
    if any(_SECRET_SETTING.search(k) and v not in ("set", "not set") for k, v in value.items()):
        raise ValueError('a secret setting is shown only as "set" or "not set"')
    for setting in (*value, *value.values()):
        _no_placeholder(setting)
    return value


# Every setting a run used, resolved, by its dotted name; a secret only as "set" or "not set".
Shown = Annotated[dict[str, str], AfterValidator(_shown)]
# Text a run writes into the committed history, which is never edited.
Plain = Annotated[str, AfterValidator(_no_placeholder)]


class Request(Model):
    """One request an answerer made for a variant, and how it ended."""

    segment: int = Field(ge=0)
    attempt: int = Field(ge=1)
    latency_ms: float = Field(ge=0)
    billed_seconds: float = Field(ge=0)
    outcome: Outcome


class Window(Model):
    """What was heard in the first `ms` of a variant's first segment, with the registration's
    measures of it, which the runner takes with Track E's `windows.py`."""

    ms: int = Field(gt=0)
    text: str
    empty: bool  # nothing heard, after normalization
    words: int = Field(ge=0)  # the words heard, after normalization
    leading_words: int = Field(ge=0)  # how many of them match the reference's first, in order
    holds_word: bool | None = None  # set only for a one-word reference: whether it was heard
    reused: bool = False  # as long as the clip: the clip's own answer, not sent again

    @model_validator(mode="after")
    def _counts_agree(self) -> Self:
        if self.empty != (self.words == 0) or self.leading_words > self.words:
            raise ValueError("an empty window has no words, and its leading words are among them")
        return self


class SegmentAnswer(Model):
    """What came back for one segment of a variant of several (a take the detector split)."""

    text: str
    language: str | None = None
    confidence: float | None = None  # the provider's own scale (Whisper's mean log-probability)
    no_speech_prob: float | None = Field(default=None, ge=0, le=1)


class Answer(Model):
    """What an answerer returned for one variant. Whisper's confidence and no-speech estimate are
    kept, so a silence rule (the prototype's: a no-speech estimate above 0.6 with a confidence
    below -0.4) can be scored again on stored scorecards, without a new request (D-021)."""

    variant: Name
    # The segments' transcripts, joined with a space; None when only the windows were sent.
    text: str | None = None
    language: str | None = None
    # For a variant of several segments, the means of theirs, each weighted by its length.
    confidence: float | None = None
    no_speech_prob: float | None = Field(default=None, ge=0, le=1)
    segments: tuple[SegmentAnswer, ...] = ()  # each segment's own, for a variant of several
    requests: tuple[Request, ...] = ()
    windows: tuple[Window, ...] = ()
    # An infrastructure failure, which is not an answer: left out of every rate, and listed.
    failure: Literal["provider", "stuck"] | None = None


class AnswerRequest(Model):
    """What the runner hands an answerer for one variant."""

    segments: tuple[Path, ...] = Field(min_length=1)  # its audio files, resolved
    language: str | None  # the hint sent ("ar", "en"), from the item's label
    windows_ms: tuple[int, ...] = ()


class VariantResult(Model):
    """One variant scored: its strata, its reference, its answer and the verdict. It has a
    verdict exactly when it was judged and answered: `right` is None for an infrastructure
    failure (`answer.failure`) and in a run that sent only the windows (`judged` false)."""

    item: Name
    variant: Name
    split: Split
    kind: Kind
    language: Language
    device: Device
    want: Name | None = None  # the item's
    tags: tuple[Name, ...] = ()
    reference: str
    alternatives: tuple[str, ...] = ()
    terms: tuple[str, ...] = ()  # the item's product terms (`Item.terms`), for term recall
    answer: Answer
    judged: bool = True
    right: bool | None

    @model_validator(mode="after")
    def _verdict_fits(self) -> Self:
        unjudged = not self.judged or self.answer.failure is not None
        if unjudged != (self.right is None) or (not unjudged and self.answer.text is None):
            raise ValueError("a variant has a verdict exactly when it was judged and answered")
        return self


class Metrics(Model):
    """The numbers of a run, or of one stratum of it; a rate is None where nothing counts."""

    items: int = Field(ge=0)  # the items its answered variants are of (no failure's)
    variants: int = Field(ge=0)
    right: int = Field(ge=0)
    failures: int = Field(ge=0)  # infrastructure failures; an unjudged variant is not one
    accuracy: float | None = None
    wer: float | None = None
    cer: float | None = None
    term_recall: float | None = None
    id_recall: float | None = None  # over the items of `models.TICKET_KIND`
    silence_share: float | None = None  # of the empty-reference variants, those with output
    silence_chars: int = Field(default=0, ge=0)
    requests: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    latency_median_ms: float | None = None
    latency_p90_ms: float | None = None
    billed_seconds: float = Field(default=0, ge=0)
    cost_usd: float = Field(default=0, ge=0)  # billed hours times the run's price per hour

    @model_validator(mode="after")
    def _items_fit(self) -> Self:
        answered = self.variants - self.failures
        if self.items > answered or (self.items == 0) != (answered == 0):
            raise ValueError("a group's items are those of its answered variants, one or more")
        return self


class WindowMetrics(Model):
    """The window measures of one window length over the clips of one language and `want`
    label, as counts and sums, so every breakdown adds up. A held-out run keeps these, and no
    variant; its groups of one length that cover fewer than `HELD_OUT_MIN_ITEMS` items are
    pooled as one, whose `language` is `OTHER` and `want` None, and a group's one-word clips
    are counted only when they are of that many items too."""

    ms: int = Field(gt=0)
    language: Language | Other
    want: Name | None = None
    items: int = Field(ge=0)  # the items its clips are of
    clips: int = Field(ge=0)
    empty: int = Field(ge=0)
    reused: int = Field(ge=0)
    words: int = Field(ge=0)  # heard, after normalization
    leading_words: int = Field(ge=0)
    reference_words: int = Field(ge=0)  # so the share of leading words can be taken
    one_word_clips: int = Field(ge=0)  # the clips whose reference is one word
    holds_word: int = Field(ge=0)  # of those, the windows that hold it

    @model_validator(mode="after")
    def _items_fit(self) -> Self:
        if self.items > self.clips or (self.items == 0) != (self.clips == 0):
            raise ValueError("a window group's items are those of its clips, one or more")
        return self


# Why a run is made: written into the committed history, which is never edited.
Note = Annotated[Plain, Field(min_length=1)]


class RunInfo(Model):
    """What a run was: when, at which commit, with which answerer, settings and data, and why.
    A held-out run is never traced."""

    name: Name
    started_at: datetime
    commit: Commit  # with `+` when the tree was dirty
    answerer: Name
    model: Plain | None = None
    split: Split
    settings: Shown
    price_per_hour_usd: float = Field(ge=0, allow_inf_nan=False)  # `--price-per-hour`
    data_digest: Sha256
    note: Note
    windows_ms: tuple[int, ...] = ()
    traced: bool = False

    @model_validator(mode="after")
    def _held_out_untraced(self) -> Self:
        if self.split == "held-out" and self.traced:
            raise ValueError("a held-out run is never traced")
        return self


def _too_small(split: Split, counts: Iterable[int]) -> bool:
    """Whether a held-out run's groups, given by the items each covers, hold one too small."""
    return split == "held-out" and any(items < HELD_OUT_MIN_ITEMS for items in counts)


class Scorecard(Model):
    """A run's scorecard. A held-out run's holds aggregates only, no variant, and no group of
    fewer than `HELD_OUT_MIN_ITEMS` items; every variant is of the run's split; all are refused
    as it is read. Built with the constructor or `model_validate`, never
    `model_copy(update=...)`, which skips the checks."""

    run: RunInfo
    speakers: Literal["one speaker"] = "one speaker"  # the owner alone (D-006)
    complete: bool
    totals: Metrics
    breakdowns: dict[str, dict[str, Metrics]]  # by language, device, kind and split
    windows: tuple[WindowMetrics, ...] = ()
    violations: int = Field(default=0, ge=0)
    violations_reason: str = "no hard constraint applies to speech-to-text"
    variants: tuple[VariantResult, ...] = ()

    @model_validator(mode="after")
    def _held_out_aggregates_only(self) -> Self:
        if self.run.split == "held-out" and (self.variants or self.run.traced):
            raise ValueError("a held-out run's scorecard holds aggregates only, and is untraced")
        groups = [m.items for values in self.breakdowns.values() for m in values.values()]
        groups += [window.items for window in self.windows]
        if any(items > self.totals.items for items in groups):
            raise ValueError("a group covers no more items than the run's totals")
        if _too_small(self.run.split, groups):
            raise ValueError(
                f"a held-out run's groups each cover at least {HELD_OUT_MIN_ITEMS} items"
            )
        if any(result.split != self.run.split for result in self.variants):
            raise ValueError("a scorecard holds only its own split's variants")
        keys = [(result.item, result.variant) for result in self.variants]
        if len(set(keys)) != len(keys):
            raise ValueError("a scorecard scores each variant once")
        return self


class StratumValue(Model):
    """A stratum value's accuracy in a history line, and the items it covers."""

    items: int = Field(ge=0)
    accuracy: float | None


class HistoryLine(Model):
    """One line of `history.jsonl` (evaluation.md, "Run history"). A held-out run's holds no
    stratum value of fewer than `HELD_OUT_MIN_ITEMS` items, refused as it is read."""

    time: datetime
    commit: Commit
    run: Name
    answerer: Name
    model: Plain | None = None
    settings: Shown
    split: Split
    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    accuracy: float | None
    violations: int = Field(ge=0)
    billed_seconds: float = Field(ge=0)
    price_per_hour_usd: float = Field(ge=0, allow_inf_nan=False)  # so the spend adds up
    cost_usd: float = Field(ge=0)
    latency_median_ms: float | None
    breakdowns: dict[str, dict[str, StratumValue]]  # each stratum value's accuracy and items
    scorecard: str  # the scorecard's file name, `SCORECARD_FILE`
    data_digest: Sha256
    note: Note
    complete: bool

    @model_validator(mode="after")
    def _held_out_groups(self) -> Self:
        counts = [value.items for values in self.breakdowns.values() for value in values.values()]
        if any(items > self.items for items in counts):
            raise ValueError("a stratum value covers no more items than the run")
        if _too_small(self.split, counts):
            raise ValueError(
                f"a held-out run's stratum values each cover at least {HELD_OUT_MIN_ITEMS} items"
            )
        return self


class Answerer(Protocol):
    """Gives one variant's answer: the `reference` answerer, the `groq` one, ..."""

    name: str

    async def answer(self, variant: Variant, request: AnswerRequest) -> Answer:
        """The answer for `variant`, from its audio in `request`; a provider's failure after
        the last attempt is an answer with `failure="provider"`, not an exception."""


class Matcher(Protocol):
    """Judges an output against a variant's references, under the spelling guide."""

    def is_right(self, output: str, references: Sequence[str]) -> bool:
        """Whether `output` says one of `references` (the reference and its alternatives);
        TypeError when `references` is a str rather than a sequence of texts."""


class ScorecardWriter(Protocol):
    """Builds a run's scorecard from its results, and writes it into the run's folder."""

    def __call__(
        self, run: RunInfo, results: Sequence[VariantResult], *, complete: bool, out: Path
    ) -> Scorecard:
        """The scorecard of `results`, also written as `out / SCORECARD_FILE`."""
