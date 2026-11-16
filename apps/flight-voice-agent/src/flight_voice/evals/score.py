"""What a run of the flight agent's scripted calls keeps (evals/run.py): a record per play, the
scorecard, and the session's line in the app's run history.

- **A play's record** (`PlayRecord`): its scenario and repeat, whether every check held, the
  checks it failed by name and turn (checks.py's `Failed`, as `outcome@3`), why it could not go
  on, the call's violations, and each turn as heard (its words and tools) for reading a failure
  by hand. A smoke play's record is marked `smoke` and never scored.
- **The scorecard** (`Scorecard`, `scorecard.json` and `scorecard.md`): the run, each scenario's
  plays and passes (passed when every check holds in at least two of three plays, `PASS_SHARE`;
  `all_plays` says whether it held in every play, the rule for a target among the long-call
  checks), the plays failing each check, its violations counted per play, the scenarios skipped
  for a capability that does not play yet, and the totals; `held` is the hard constraint, no
  violation in any play, the smoke play's among them.
- **The history line** (`HistoryLine`), one a session, appended to the app's
  `evals/history.jsonl`: the library's day counter (`requests_today`) reads its `time` and its
  `requests`, each model's requests that session, so a run of either app counts the key's day.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from t2_agentic_voice.evals import ModelSpend

from flight_voice.evals.call import PlayRead, Stuck
from flight_voice.evals.checks import Failed, failures, own, said
from flight_voice.evals.scenarios import Scenario, Split

# The share of a scenario's plays in which every check must hold for it to pass: two of three.
PASS_SHARE: Final = 2 / 3
# Why a session stopped before its end: the smoke play, the cap, the key's day, an interrupt.
Stopped = Literal["smoke_failed", "cap", "daily_limit", "interrupted"]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TurnKept(_Model):
    """One turn as the caller heard it: its words (the runtime's lines among them), the
    talker's own words, the tools its reply called, and its fate; a stop's is empty."""

    heard: str = ""
    own: str = ""
    tools: tuple[str, ...] = ()
    fate: str = ""


class PlayRecord(_Model):
    """One play's record (the module's docstring)."""

    scenario: str
    repeat: int = Field(ge=0)
    smoke: bool = False
    passed: bool
    failed: tuple[str, ...] = ()
    failure: Stuck | None = None
    violations: tuple[str, ...] = ()
    seconds: float = Field(ge=0)
    turns: tuple[TurnKept, ...] = ()


def _named(failed: Failed) -> str:
    return failed.check if failed.turn is None else f"{failed.check}@{failed.turn}"


def record_of(
    scenario: Scenario, repeat: int, read: PlayRead, seconds: float, *, smoke: bool = False
) -> PlayRecord:
    """The record of one play of `scenario`, what it did `read`."""
    found = failures(scenario, read)
    turns = tuple(
        TurnKept()
        if t is None
        else TurnKept(
            heard=said(t.heard),
            own=said(own(t.heard)),
            tools=tuple(c.tool for c in t.tools),
            fate=t.fate,
        )
        for t in read.turns
    )
    return PlayRecord(
        scenario=scenario.id,
        repeat=repeat,
        smoke=smoke,
        passed=not found,
        failed=tuple(_named(f) for f in found),
        failure=read.failure,
        violations=read.violations,
        seconds=round(seconds, 3),
        turns=turns,
    )


class RunInfo(_Model):
    """What a run is, written before anything is sent; a resumed run must be the same."""

    name: str
    started_at: datetime
    commit: str
    split: Split
    model: str
    effort: str
    repeats: int
    cap_usd: float
    input_budget_tokens: int
    estimate_usd: float
    prices: dict[str, str]
    limits: dict[str, str]
    data: tuple[str, ...]  # the scenarios' ids, in order


class Session(_Model):
    """One session of a run: when it began, at which commit (the run's, or a later one adding
    only history lines), why it stopped (None when it ran to its end), the plays it recorded,
    and what it spent."""

    started_at: datetime
    commit: str
    stopped: Stopped | None = None
    plays: int = 0
    spend: tuple[ModelSpend, ...] = ()
    cost_usd: float = 0.0


class ScenarioCard(_Model):
    """One scenario's result (the module's docstring); `passed` None until it has its plays."""

    id: str
    kind: str
    plays: int = 0
    passes: int = 0
    passed: bool | None = None
    all_plays: bool | None = None
    violations: tuple[int, ...] = ()
    failed: dict[str, int] = Field(default_factory=dict)
    skipped: tuple[str, ...] = ()


class Totals(_Model):
    """The run's counts: scenarios, those played and passed, those skipped, plays, violations."""

    scenarios: int
    played: int
    passed: int
    skipped: int
    plays: int
    violations: int


class Scorecard(_Model):
    """The run's scorecard (the module's docstring)."""

    run: RunInfo
    complete: bool
    stopped: Stopped | None
    held: bool
    scenarios: tuple[ScenarioCard, ...]
    totals: Totals
    sessions: tuple[Session, ...]
    cost_usd: float


def needed(repeats: int) -> int:
    """The passing plays a scenario of `repeats` plays needs: two of three."""
    return math.ceil(repeats * PASS_SHARE - 1e-9)


def _card(
    scenario: Scenario, plays: Sequence[PlayRecord], repeats: int, skip: tuple[str, ...]
) -> ScenarioCard:
    passes = sum(p.passed for p in plays)
    checks = Counter(name.partition("@")[0] for p in plays for name in set(p.failed))
    done = len(plays) >= repeats and not skip
    return ScenarioCard(
        id=scenario.id,
        kind=scenario.kind,
        plays=len(plays),
        passes=passes,
        passed=passes >= needed(repeats) if done else None,
        all_plays=passes == len(plays) if done else None,
        violations=tuple(len(p.violations) for p in plays),
        failed=dict(sorted(checks.items())),
        skipped=skip,
    )


def scorecard(
    info: RunInfo,
    scenarios: Sequence[tuple[Scenario, tuple[str, ...]]],
    records: Sequence[PlayRecord],
    *,
    stopped: Stopped | None,
    sessions: Sequence[Session],
) -> Scorecard:
    """The scorecard of `records` over `scenarios`, each with the needs that skip it."""
    scored = [r for r in records if not r.smoke]
    cards = tuple(
        _card(s, [r for r in scored if r.scenario == s.id], info.repeats, skip)
        for s, skip in scenarios
    )
    played = [c for c in cards if not c.skipped]
    complete = stopped is None and all(c.plays >= info.repeats for c in played)
    violations = sum(len(r.violations) for r in records)
    return Scorecard(
        run=info,
        complete=complete,
        stopped=stopped,
        held=violations == 0,
        scenarios=cards,
        totals=Totals(
            scenarios=len(cards),
            played=len(played),
            passed=sum(c.passed is True for c in played),
            skipped=len(cards) - len(played),
            plays=len(scored),
            violations=violations,
        ),
        sessions=tuple(sessions),
        cost_usd=round(sum(s.cost_usd for s in sessions), 6),
    )


class HistoryLine(_Model):
    """One session's line in the app's run history (the module's docstring)."""

    kind: Literal["flights"] = "flights"
    time: datetime
    run: str
    commit: str
    split: Split
    model: str
    effort: str
    session: int
    complete: bool
    stopped: Stopped | None
    plays: int
    passed: int
    played: int
    violations: int
    cost_usd: float
    requests: dict[str, int]


def history_line(card: Scorecard, session: Session, number: int) -> HistoryLine:
    """The line of the run's `number`th session, `session`, its scorecard `card`."""
    run = card.run
    return HistoryLine(
        time=session.started_at,
        run=run.name,
        commit=run.commit,
        split=run.split,
        model=run.model,
        effort=run.effort,
        session=number,
        complete=card.complete,
        stopped=card.stopped,
        plays=card.totals.plays,
        passed=card.totals.passed,
        played=card.totals.played,
        violations=card.totals.violations,
        cost_usd=card.cost_usd,
        requests={s.model: s.requests for s in session.spend},
    )
