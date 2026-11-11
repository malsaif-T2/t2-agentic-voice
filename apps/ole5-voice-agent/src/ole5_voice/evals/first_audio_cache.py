"""Run I's arm of run T (plan 007, "Run I"; `poe first-audio --clause-cache on`): the clause
cache as the replay's calls speak through it (`CachedVoice`, first_audio_replay.py), what it did
in each call (`ClauseCall`), and the run's numbers (`clause_summary`), which the scorecard and
the history line hold (first_audio_card.py, measure_lines.py).

- **The cache** is the `stores` facade's `ClauseCache` over the replay's counting voice, in the
  run's folder (`CLAUSES_DIR`). `CachedVoice` passes every call on to it and keeps whether each
  call's first look-up was a hit, the clause the reply's time to first audio waits on. Each
  call's counts are taken once it has ended (`took`), its tail of silence passed, so its takes
  are written by then. The replay's own greeting goes through the cache too, before each call:
  kept once a language, then not kept as held, and never asked for, since the call plays it as
  a fixed phrase; the progress lines the replay says at its start are kept and cleared with the
  smoke call's takes.
- **The shares.** Each look-up is one clause asked of the cache, a hit or a miss. The hits are a
  share of the clauses asked in each item's first variant in the run's order, which can hit only
  another question's clauses, and in the rest, the same question again in other words, apart.
  A recording replayed after a rate limit (first_audio_run.py) is counted apart, every attempt
  of it, and left out of the shares, since its later attempts could hit its own first one.
- **The times.** Each look-up's time, hits' and misses' apart (median, 90th percentile, most),
  every attempt's; beside them, Orpheus's own first audio, each timed turn's
  `tts_first_audio_ms`; and the timed turns whose reply's first clause was held, their count and
  their median time to first audio against the other turns'.
- **The requests per call minute:** the clauses requested (the misses, each one Orpheus request;
  the replay's own greeting and the fixed phrases left out, as a live call plays them from the
  phrase cache), then with each hit added back, over the calls' minutes.
- **The keep rule's first four conditions** (`checks`): no recording failed and no reply to a turn
  played short (a clause unsaid, whatever the cause); the first variants' hits at least 2% of their
  clauses asked; a miss's look-up at most 2 ms at the 90th percentile and 20 ms in every case;
  a hit's read at most 50 ms at the 90th percentile. The fifth, every run T target T0's dev run
  met still met, reads the targets against T0's history line.

A dev run only: `--clause-cache on` is refused for held-out, which run I does not run. Nothing
here holds a text or a key.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Final

from pydantic import Field
from t2_agentic_voice.events import AgentSpeechEnded, CallEnded, Event
from t2_agentic_voice.ports import AudioChunk
from t2_agentic_voice.stores import ClauseCache

from ole5_voice.evals.models import Model, Name
from ole5_voice.evals.scorecard import quantile

if TYPE_CHECKING:  # named in annotations only: first_audio_score.py imports this module
    from ole5_voice.evals.first_audio_score import AudioResult

FIRST_HITS_LEAST: Final = 0.02  # the registration's numbers, each the agent's own
MISS_P90_MOST_MS: Final = 2.0
MISS_MOST_MS: Final = 20.0
HIT_P90_MOST_MS: Final = 50.0
CLAUSES_DIR: Final = "clauses"  # the cache's folder in the run's
_Count = Annotated[int, Field(ge=0)]
_Ms = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class ClauseCall(Model):
    """What the clause cache did in one call (the `stores` facade's `ClauseCounts`, its times in
    milliseconds): its hits and misses, whether the first look-up was a hit (None: none was
    made), the replies to a turn that played short, the takes kept and those not kept by why, the
    files that were no take, the writes that failed, the takes the bound removed, the entries and
    megabytes held at its end, each look-up's time, and the call's length."""

    hits: _Count = 0
    misses: _Count = 0
    first_held: bool | None = None
    unsaid: _Count = 0
    kept: _Count = 0
    not_kept: dict[Name, _Count] = Field(default_factory=dict)
    unreadable: _Count = 0
    write_failures: _Count = 0
    removed: _Count = 0
    entries: _Count = 0
    megabytes: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    hit_ms: tuple[_Ms, ...] = ()
    miss_ms: tuple[_Ms, ...] = ()
    call_s: _Ms | None = None


class ClauseShare(Model):
    """The look-ups of some recordings: how many recordings, the clauses asked, the hits, and
    their share (None when none was asked)."""

    variants: _Count
    asked: _Count
    hits: _Count
    share: float | None = None


class Spread(Model):
    """Some times in milliseconds: how many, their median, 90th percentile and most."""

    count: _Count
    median_ms: float | None = None
    p90_ms: float | None = None
    most_ms: float | None = None


class ClauseSummary(Model):
    """A run's numbers for the clause cache (the module's docstring): the shares, by each item's
    first variant, the rest, both, and the recordings replayed after a rate limit; the look-ups'
    times and Orpheus's first audio; the turns whose first clause was held; the requests per call
    minute; the takes, at the end the entries and megabytes held; and the keep rule's checks."""

    first: ClauseShare
    rest: ClauseShare
    every: ClauseShare
    retried: ClauseShare
    hit_read: Spread
    miss_lookup: Spread
    tts_first_audio: Spread
    held_first: _Count
    held_first_median_ms: float | None = None
    other_median_ms: float | None = None
    call_minutes: float = Field(ge=0, allow_inf_nan=False)
    requests_per_minute: float | None = None
    asked_per_minute: float | None = None
    unsaid: _Count
    kept: _Count
    not_kept: dict[Name, _Count]
    unreadable: _Count
    write_failures: _Count
    removed: _Count
    entries: _Count
    megabytes: float = Field(ge=0, allow_inf_nan=False)
    checks: dict[Name, bool | None]


class CachedVoice:
    """The replay's text-to-speech with the clause cache (the module's docstring): `cache`
    itself, as the calls speak through it, with whether each call's first look-up was a hit
    (`first`, None until one is made); a `TextToSpeech` that holds speech, as the cache is."""

    def __init__(self, cache: ClauseCache) -> None:
        self.cache = cache
        self.name, self.data_flow = cache.name, cache.data_flow
        self.first: bool | None = None

    def max_chars(self, language: str) -> int | None:
        return self.cache.max_chars(language)

    def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        return self.cache.synthesize(text, language=language)

    async def held(self, text: str, *, language: str) -> AudioChunk | None:
        found = await self.cache.held(text, language=language)
        if self.first is None:
            self.first = found is not None
        return found

    async def check_language(self, language: str) -> datetime | None:
        return await self.cache.check_language(language)

    async def aclose(self) -> None:
        """Nothing of its own: the replay drains the cache."""

    def took(self, emitted: Sequence[Event]) -> ClauseCall:
        """What the cache did in the call that emitted `emitted`, its counts then reset: the
        replies to a turn that played short read from its `AgentSpeechEnded`, its length from
        its report."""
        counts, first = self.cache.taken(), self.first
        self.first = None
        report = next((e.report for e in emitted if isinstance(e, CallEnded)), None)
        unsaid = [
            e
            for e in emitted
            if isinstance(e, AgentSpeechEnded) and e.turn_id is not None and e.played_fraction < 1
        ]
        return ClauseCall(
            hits=counts.hits,
            misses=counts.misses,
            first_held=first,
            unsaid=len(unsaid),
            kept=counts.kept,
            not_kept=dict(counts.not_kept.items()),
            unreadable=counts.unreadable,
            write_failures=counts.write_failures,
            removed=counts.removed,
            entries=counts.entries,
            megabytes=counts.megabytes,
            hit_ms=tuple(s * 1000 for s in counts.hit_s),
            miss_ms=tuple(s * 1000 for s in counts.miss_s),
            call_s=None if report is None else report.duration_s,
        )

    async def clear(self) -> None:
        await self.cache.clear()
        self.first = None


def _share(results: Sequence[AudioResult]) -> ClauseShare:
    calls = [each for result in results for each in result.clause_cache]
    hits = sum(each.hits for each in calls)
    asked = hits + sum(each.misses for each in calls)
    return ClauseShare(
        variants=len(results), asked=asked, hits=hits, share=hits / asked if asked else None
    )


def _spread(times: Iterable[float]) -> Spread:
    ordered = sorted(times)
    return Spread(
        count=len(ordered),
        median_ms=quantile(ordered, 0.5),
        p90_ms=quantile(ordered, 0.9),
        most_ms=ordered[-1] if ordered else None,
    )


def _at_most(value: float | None, bound: float) -> bool | None:
    return None if value is None else value <= bound


def clause_summary(results: Sequence[AudioResult]) -> ClauseSummary:
    """The run's numbers for the clause cache from its recordings' results, in the run's order
    (the module's docstring)."""
    seen: set[str] = set()
    first: list[AudioResult] = []
    rest: list[AudioResult] = []
    for result in results:  # an item's first variant is first even when it was replayed
        if result.attempts == 1:
            (rest if result.item in seen else first).append(result)
        seen.add(result.item)
    once = [*first, *rest]
    calls = [each for result in results for each in result.clause_cache]
    timed = [
        (r.timed, r.clause_cache[-1]) for r in results if r.timed is not None and r.clause_cache
    ]
    held = sorted(t.ttfa_ms for t, c in timed if c.first_held and t.ttfa_ms is not None)
    other = sorted(t.ttfa_ms for t, c in timed if not c.first_held and t.ttfa_ms is not None)
    minutes = sum(each.call_s or 0.0 for each in calls) / 60
    misses = sum(each.misses for each in calls)
    asked = misses + sum(each.hits for each in calls)
    not_kept: dict[str, int] = {}
    for each in calls:
        for why, count in each.not_kept.items():
            not_kept[why] = not_kept.get(why, 0) + count
    shares = _share(first)
    hit_read = _spread(ms for each in calls for ms in each.hit_ms)
    miss_lookup = _spread(ms for each in calls for ms in each.miss_ms)
    unsaid = sum(each.unsaid for each in calls)
    last = calls[-1] if calls else ClauseCall()
    failed = any(result.failure is not None for result in results)
    enough = None if shares.share is None else shares.share >= FIRST_HITS_LEAST
    return ClauseSummary(
        first=shares,
        rest=_share(rest),
        every=_share(once),
        retried=_share([result for result in results if result.attempts > 1]),
        hit_read=hit_read,
        miss_lookup=miss_lookup,
        tts_first_audio=_spread(
            ms for turn, _ in timed if (ms := turn.tts_first_audio_ms) is not None
        ),
        held_first=sum(bool(c.first_held) for _, c in timed),
        held_first_median_ms=quantile(held, 0.5),
        other_median_ms=quantile(other, 0.5),
        call_minutes=minutes,
        requests_per_minute=misses / minutes if minutes else None,
        asked_per_minute=asked / minutes if minutes else None,
        unsaid=unsaid,
        kept=sum(each.kept for each in calls),
        not_kept=dict(sorted(not_kept.items())),
        unreadable=sum(each.unreadable for each in calls),
        write_failures=sum(each.write_failures for each in calls),
        removed=sum(each.removed for each in calls),
        entries=last.entries,
        megabytes=last.megabytes,
        checks={
            "none_failed": not failed and unsaid == 0,
            "first_variant_hits": enough,
            "miss_p90": _at_most(miss_lookup.p90_ms, MISS_P90_MOST_MS),
            "miss_most": _at_most(miss_lookup.most_ms, MISS_MOST_MS),
            "hit_p90": _at_most(hit_read.p90_ms, HIT_P90_MOST_MS),
        },
    )
