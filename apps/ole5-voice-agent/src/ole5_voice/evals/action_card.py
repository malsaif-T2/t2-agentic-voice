"""Run A's scorecard (plan 007's "The measurement, registered before any result"): the run, its
sessions, the registered metrics over every scored play, whether each target held, the hard
constraint, and, for a dev run, each scenario's plays and the plays themselves.

- **The metrics**: the right action taken or rightly not taken (`action`, by play), the
  ticket's type right (`type`, by play that made one of a scenario that names its type), the
  summary judged faithful (`summary`, by play whose summary was judged), and the reply's
  language right (`language`, by turn held to one: its words' script and, held to Arabic, its
  register). A play with no result is counted apart and left out of each.
- **The targets** (`TARGETS`), registered on held-out and shown for dev too: each share at
  least its target, None until it has a play.
- **The hard constraint**: no unrecorded claim and no action without a yes, in every play
  (`ActionPlayRecord.violations`), one with no result, the smoke test's and an unfinished
  held-out run's included (`dropped`, those the card keeps no play of). One violation fails the
  run (`passed` False), whatever else it scored; a run passes when it is complete, has none, and
  meets every target (a smoke test alone neither passes nor fails).
- **A scenario** of a dev run meets its target as run S's does (scenario_score.py's `needed`):
  in every play for the rehearsal's, in two of three for any other.
- **The stray count** (D-084): the characters the library's stray-script filter took out of, or
  rewrote in, what the talker wrote, counted and never scored: each play's in its record, each
  dev scenario's summed over its plays, and the run's over every play (`stray_characters`).

A held-out run's scorecard holds the aggregates only: no play and no scenario's count, refused
as it is read otherwise, as run K's is (held-out is read once).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Annotated, Final, Self

from pydantic import Field, model_validator

from ole5_voice.evals.action_scenarios import ActionScenario, Kind
from ole5_voice.evals.action_score import ActionPlayRecord
from ole5_voice.evals.models import Commit, Model, Name, Sha256, Split
from ole5_voice.evals.runs import ModelName, Note, Plain, Shown
from ole5_voice.evals.scenario_score import needed
from ole5_voice.evals.talker_score import PriceShown, Session, Stopped

_Usd = Annotated[float, Field(ge=0, allow_inf_nan=False)]
TARGETS: Final[Mapping[str, float]] = {
    "action": 0.95,
    "type": 0.85,
    "summary": 0.85,
    "language": 0.90,
}


class Share(Model):
    """How many of `of` were right, and their share."""

    right: int = Field(ge=0)
    of: int = Field(ge=1)
    share: float = Field(ge=0, le=1, allow_inf_nan=False)


def share(values: Iterable[bool | None]) -> Share | None:
    """The share of True among `values`, None left out; None when none is left."""
    counted = [value for value in values if value is not None]
    if not counted:
        return None
    right = sum(counted)
    return Share(right=right, of=len(counted), share=right / len(counted))


class ActionMetrics(Model):
    """The registered metrics over the plays so far (the module's docstring), the plays scored
    and those with no result, the violations of every play, those the card keeps no play of
    included, and the stray count of every play it keeps."""

    plays: int = Field(ge=0)
    failures: int = Field(ge=0)
    action: Share | None = None
    type: Share | None = None
    summary: Share | None = None
    language: Share | None = None
    violations: int = Field(default=0, ge=0)
    stray_characters: int = Field(default=0, ge=0)


def metrics(plays: Sequence[ActionPlayRecord], *, dropped: int = 0) -> ActionMetrics:
    """The metrics of `plays` (the module's docstring), `dropped` the violations of plays they
    leave out."""
    scored = [play for play in plays if play.failure is None]
    language = [
        check.language is True and check.in_register is not False
        for play in scored
        for check in play.checks
        if check.language is not None
    ]
    return ActionMetrics(
        plays=len(scored),
        failures=len(plays) - len(scored),
        action=share(play.action_right for play in scored),
        type=share(play.type_right for play in scored),
        summary=share(play.summary_faithful for play in scored),
        language=share(language),
        violations=dropped + sum(len(play.violations) for play in plays),
        stray_characters=sum(play.stray_characters for play in plays),
    )


def targets(totals: ActionMetrics) -> dict[str, bool | None]:
    """Whether each registered target held, None for a metric with no play."""
    found = {name: getattr(totals, name) for name in TARGETS}
    return {
        name: None if value is None else value.share >= TARGETS[name]
        for name, value in found.items()
    }


class ScenarioPasses(Model):
    """One scenario's plays in a dev run: how many were scored and passed, how many failed, how
    many it needs, whether it met its target (None until every play is scored), and the stray
    count of its plays."""

    scenario: Name
    kind: Kind
    rehearsal: bool
    plays: int = Field(ge=0)
    passed: int = Field(ge=0)
    failures: int = Field(ge=0)
    needed: int = Field(ge=1)
    met: bool | None
    stray_characters: int = Field(default=0, ge=0)


class ActionRun(Model):
    """What a run of A was: its arm and model, the judge's, the split, the settings, prices,
    cap and the dry estimate of its most spend, the data, how many times each scenario plays,
    and why it was made."""

    name: Name
    started_at: datetime
    commit: Commit
    arm: Name
    model: Plain
    judge_model: Plain
    split: Split
    settings: Shown
    prices: dict[ModelName, PriceShown]
    cap_usd: _Usd
    estimate_usd: _Usd
    data_digest: Sha256
    note: Note
    repeats: int = Field(ge=1)
    smoke_only: bool = False


class ActionScorecard(Model):
    """Run A's scorecard (the module's docstring)."""

    run: ActionRun
    complete: bool
    stopped: Stopped | None
    sessions: tuple[Session, ...]
    totals: ActionMetrics
    targets: dict[Name, bool | None]
    targets_met: bool | None
    held: bool | None  # the hard constraint, None before any play
    passed: bool | None
    cost_usd: _Usd
    scenarios: tuple[ScenarioPasses, ...] = ()
    plays: tuple[ActionPlayRecord, ...] = ()

    @model_validator(mode="after")
    def _held_out_aggregates_only(self) -> Self:
        if self.run.split == "held-out" and (self.plays or self.scenarios):
            raise ValueError("a held-out run's scorecard holds its aggregates only")
        return self


def _passes(
    scenarios: Sequence[ActionScenario], plays: Sequence[ActionPlayRecord], repeats: int
) -> tuple[ScenarioPasses, ...]:
    counts = []
    for scenario in scenarios:
        own = [play for play in plays if play.scenario == scenario.id]
        scored = [play for play in own if play.passed is not None]
        wanted = needed(scenario.rehearsal, repeats)
        passed = sum(bool(play.passed) for play in scored)
        counts.append(
            ScenarioPasses(
                scenario=scenario.id,
                kind=scenario.kind,
                rehearsal=scenario.rehearsal,
                plays=len(scored),
                passed=passed,
                failures=len(own) - len(scored),
                needed=wanted,
                met=passed >= wanted if len(scored) >= repeats else None,
                stray_characters=sum(play.stray_characters for play in own),
            )
        )
    return tuple(counts)


def scorecard(
    run: ActionRun,
    scenarios: Sequence[ActionScenario],
    plays: Sequence[ActionPlayRecord],
    *,
    complete: bool,
    stopped: Stopped | None,
    sessions: Sequence[Session],
    dropped: int = 0,
) -> ActionScorecard:
    """The scorecard of `plays`, the split's `scenarios` counted for a dev run, `dropped` the
    violations of the plays it keeps none of (the module's docstring)."""
    totals = metrics(plays, dropped=dropped)
    found = targets(totals)
    met = None if None in found.values() else all(found.values())
    held = None if not plays and not totals.violations else totals.violations == 0
    passed = False if held is False else (met if complete and not run.smoke_only else None)
    dev = run.split == "dev"
    return ActionScorecard(
        run=run,
        complete=complete,
        stopped=stopped,
        sessions=tuple(sessions),
        totals=totals,
        targets=found,
        targets_met=met,
        held=held,
        passed=passed,
        cost_usd=sum(session.cost_usd for session in sessions),
        scenarios=_passes(scenarios, plays, run.repeats) if dev else (),
        plays=tuple(plays) if dev else (),
    )
