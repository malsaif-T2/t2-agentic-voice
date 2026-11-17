"""What a run of the flight agent's scripted calls keeps (evals/run.py): a record per play and the
scorecard; the session's line in the app's run history is history.py's.

- **A play's record** (`PlayRecord`): its scenario and repeat, whether every check held, the
  checks it failed by name and turn (checks.py's `Failed`, as `outcome@3`), why it could not go
  on, the call's violations, and each turn as heard (its words, its tools and each call's
  arguments as sent, the clauses the guard blocked) for reading a failure by hand, with no
  replay. A smoke play's record is marked `smoke` and never scored; a record kept before the
  calls and the blocked clauses were kept still loads, with them empty. A lean play (`--agent
  lean`) is scored by its outcomes, its violations the lean ones too, with its measures
  (lean_checks.py).
- **The scorecard** (`Scorecard`, `scorecard.json` and `scorecard.md`): the run, each scenario's
  plays and passes (passed when at least two of its three plays hold every check, `PASS_SHARE`;
  `all_plays` says whether it held in every play, the rule for a target among the long-call
  checks), the plays failing each check, its violations counted per play, the scenarios skipped
  for a capability that does not play yet, and the totals; `held` is the hard constraint, no
  violation in any play, the smoke play's among them; a lean run's scenarios hold their
  measures' means. The run names the agent played (`RunInfo.agent`, `scripted` or `lean`), so
  the two compare by scenario; a run kept before is the scripted agent's.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from t2_agentic_voice.evals import ModelSpend

from flight_voice.evals.call import PlayRead, Stuck
from flight_voice.evals.checks import Failed, failures, own, said
from flight_voice.evals.lean_checks import Measures, lean_failures, lean_violations, measures
from flight_voice.evals.lean_checks import mean_measures as means
from flight_voice.evals.scenarios import Scenario, Split
from flight_voice.settings import AgentKind

# The share of a scenario's plays in which every check must hold for it to pass: two of three.
PASS_SHARE: Final = 2 / 3
# Why a session stopped before its end: the smoke play, the cap, the key's day, an interrupt.
Stopped = Literal["smoke_failed", "cap", "daily_limit", "interrupted"]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CallKept(_Model):
    """A tool call as the talker sent it: the tool's name and the arguments it wrote."""

    tool: str
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class TurnKept(_Model):
    """One turn as the caller heard it: its words (the runtime's lines among them), the
    talker's own words, the tools its reply called (and each call as sent, `calls`), its fate,
    the texts of the clauses the guard blocked, never said, and for a lean play the talker's
    clauses as written (`written`, digits and all: its `max_words` counts them); a stop's is
    empty."""

    heard: str = ""
    own: str = ""
    tools: tuple[str, ...] = ()
    fate: str = ""
    calls: tuple[CallKept, ...] = ()
    blocked_texts: tuple[str, ...] = ()
    written: tuple[str, ...] = ()


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
    measures: Measures | None = None  # the lean agent's (lean_checks.py)


def _named(failed: Failed) -> str:
    return failed.check if failed.turn is None else f"{failed.check}@{failed.turn}"


def record_of(
    scenario: Scenario,
    repeat: int,
    read: PlayRead,
    seconds: float,
    *,
    smoke: bool = False,
    agent: AgentKind = "scripted",
) -> PlayRecord:
    """The record of one play of `scenario` by `agent`, what it did `read`: the lean agent's
    scored by its outcomes, with its measures (lean_checks.py)."""
    lean = agent == "lean"
    found = lean_failures(scenario, read) if lean else failures(scenario, read)
    turns = tuple(
        TurnKept()
        if t is None
        else TurnKept(
            heard=said(t.heard),
            own=said(own(t.heard)),
            tools=tuple(c.tool for c in t.tools),
            fate=t.fate,
            calls=tuple(CallKept(tool=c.tool, arguments=dict(c.arguments)) for c in t.tools),
            blocked_texts=t.blocked_texts,
            written=t.written if lean else (),
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
        violations=(*read.violations, *lean_violations(read)) if lean else read.violations,
        seconds=round(seconds, 3),
        turns=turns,
        measures=measures(read) if lean else None,
    )


class RunInfo(_Model):
    """What a run is, written before anything is sent; a resumed run must be the same."""

    name: str
    started_at: datetime
    commit: str
    split: Split
    agent: AgentKind = "scripted"
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
    measures: dict[str, float] = Field(default_factory=dict)  # the lean agent's, their means


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
        measures=means([p.measures for p in plays]),
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
