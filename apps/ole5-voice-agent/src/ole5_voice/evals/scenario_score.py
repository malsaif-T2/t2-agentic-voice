"""What run S produces (plan 006's registration, S): each play of a scenario, checked turn by
turn, and the scorecard with each scenario's target.

A turn's checks are read from what the call did (`checks_of`): the knowledge tool called or not,
the earlier reply cut, the reply's language (its own words' script, `talker_data.HELD_TO`) and
its words; the judge's checks of its facts and of what it repeats or continues; and the register
of its Arabic, the judge's answer to the register's question of its own, against those it is
held to (`ScriptTurn.held_registers`, the owner's Q24). A play passes when every check
of every turn holds and the output guard found no violation in the call. A scenario meets its
target when it passed in every play if it is one of the rehearsal's, and in at least two of
three otherwise (`needed`); a play with no result (`failure`) is not scored, and a scenario with
fewer scored plays than the run's repeats has no verdict yet. Scenarios are not split: they name
dev items only (`scenarios.problems`), so a play's turns are kept whole.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ole5_voice.evals.judge import Checked
from ole5_voice.evals.models import Commit, Model, Name, Sha256
from ole5_voice.evals.runs import Note, Plain, Shown
from ole5_voice.evals.scenarios import Scenario, ScriptTurn
from ole5_voice.evals.talker_data import HELD_TO, Failure, HeardTurn, ModelName, Register
from ole5_voice.evals.talker_score import PriceShown, Session, Stopped

_S = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class TurnCheck(Model):
    """One turn's checks: each None when the scenario expects nothing of it; `judged` the
    judge's, in the order of the turn's expectations; `in_register` whether the judge's register
    of its Arabic is one it is held to."""

    search: bool | None = None
    cut: bool | None = None
    language: bool | None = None
    words: bool | None = None
    judged: tuple[bool, ...] = ()
    reasons: tuple[str, ...] = ()
    in_register: bool | None = None

    @property
    def passed(self) -> bool:
        found = (self.search, self.cut, self.language, self.words, self.in_register)
        return all(value is not False for value in found) and all(self.judged)


class PlayRecord(Model):
    """One play of a scenario: its turns as the call heard them, their checks, the guard's
    violations, whether it passed (None when it has no result), and how long it took."""

    scenario: Name
    repeat: int = Field(ge=1)
    rehearsal: bool
    turns: tuple[HeardTurn, ...] = ()
    checks: tuple[TurnCheck, ...] = ()
    violations: int = Field(default=0, ge=0)
    passed: bool | None = None
    failure: Failure | None = None
    seconds: _S = 0.0

    @model_validator(mode="after")
    def _scored_once_answered(self) -> Self:
        if (self.failure is None) != (self.passed is not None):
            raise ValueError("a play passes or fails exactly when nothing failed")
        return self


class ScenarioCount(Model):
    """One scenario's plays: how many were scored and passed, how many failed, how many it
    needs, and whether it met its target (None until every play is scored)."""

    scenario: Name
    rehearsal: bool
    plays: int = Field(ge=0)
    passed: int = Field(ge=0)
    failures: int = Field(ge=0)
    needed: int = Field(ge=1)
    met: bool | None


class ScenarioRun(Model):
    """What a run of S was: the kept arm and its model, the judge's, the settings, prices, cap
    and data, how many times each scenario plays, and why it was made."""

    name: Name
    started_at: datetime
    commit: Commit
    arm: Name
    model: Plain
    judge_model: Plain
    settings: Shown
    prices: dict[ModelName, PriceShown]
    cap_usd: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    data_digest: Sha256
    note: Note
    repeats: int = Field(ge=1)
    smoke_only: bool = False


class ScenarioScorecard(Model):
    """Run S's scorecard (the module's docstring)."""

    run: ScenarioRun
    speakers: Literal["one speaker"] = "one speaker"  # the owner alone (D-006)
    complete: bool
    stopped: Stopped | None
    sessions: tuple[Session, ...]
    scenarios: tuple[ScenarioCount, ...]
    targets_met: bool | None
    violations: int = Field(ge=0)
    cost_usd: _S
    plays: tuple[PlayRecord, ...] = ()


def needed(rehearsal: bool, repeats: int) -> int:
    """The plays a scenario must pass: all of them for the rehearsal's, two of three for any
    other."""
    return repeats if rehearsal else math.ceil(2 * repeats / 3)


def checks_of(
    turns: Sequence[ScriptTurn],
    heard: Sequence[HeardTurn],
    judged: Sequence[Checked | None],
    tool: str,
    registers: Sequence[Register | None] = (),
) -> tuple[TurnCheck, ...]:
    """Each turn's checks (the module's docstring); `judged` the judge's, None for a turn
    whose scenario expects nothing the judge reads; `registers` the judge's register of each
    turn's reply, None for one not asked (every one, when not given)."""
    asked = list(registers) or [None] * len(turns)
    found = []
    for n, (turn, reply, checked) in enumerate(zip(turns, heard, judged, strict=True)):
        earlier = heard[n - 1] if n else None
        held = turn.held_registers()
        found.append(
            TurnCheck(
                search=None if turn.search is None else reply.searched(tool) == turn.search,
                cut=earlier.fate in ("cut", "rolled_back") if turn.cuts_reply and earlier else None,
                language=(
                    None if turn.language is None else reply.written_in(HELD_TO[turn.language][0])
                ),
                words=None if turn.max_words is None else reply.words <= turn.max_words,
                judged=checked.holds or () if checked else (),
                reasons=checked.reasons if checked else (),
                in_register=asked[n] in held if held else None,
            )
        )
    return tuple(found)


def scorecard(
    run: ScenarioRun,
    scenarios: Sequence[Scenario],
    plays: Sequence[PlayRecord],
    *,
    complete: bool,
    stopped: Stopped | None,
    sessions: Sequence[Session],
) -> ScenarioScorecard:
    """The scorecard of `plays`, each scenario counted against its target."""
    counts = []
    for scenario in scenarios:
        own = [play for play in plays if play.scenario == scenario.id]
        scored = [play for play in own if play.passed is not None]
        wanted = needed(scenario.rehearsal, run.repeats)
        passed = sum(bool(play.passed) for play in scored)
        counts.append(
            ScenarioCount(
                scenario=scenario.id,
                rehearsal=scenario.rehearsal,
                plays=len(scored),
                passed=passed,
                failures=len(own) - len(scored),
                needed=wanted,
                met=passed >= wanted if len(scored) >= run.repeats else None,
            )
        )
    verdicts = [count.met for count in counts]
    return ScenarioScorecard(
        run=run,
        complete=complete,
        stopped=stopped,
        sessions=tuple(sessions),
        scenarios=tuple(counts),
        targets_met=None if None in verdicts or not verdicts else all(verdicts),
        violations=sum(play.violations for play in plays),
        cost_usd=sum(session.cost_usd for session in sessions),
        plays=tuple(plays),
    )
