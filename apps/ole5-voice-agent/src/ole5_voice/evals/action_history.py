"""The history line of run A (evaluation.md, "Run history"): one `ActionLine` for each session of
a `poe eval-actions` run (`action_line`), marked by its `kind`, `actions`. It counts what that
session sent (every request, the smoke test's and the judge's included), so the history's spend
adds up over a run spread over days; its numbers are the scorecard's after that session.

Strict as every history line: a held-out run's line holds no scenario's count, and a secret
setting is shown only as set or not set. Every line, a held-out run's too, holds the run's
stray count (`stray_characters`, D-084): the characters the library's stray-script filter took
out of, or rewrote in, what the talker wrote in the plays its scorecard keeps, an aggregate.
The shared history reads a line through `run_lines.AnyLine`, which names each kind it takes:
until it names this one, a run refuses to start (`run_folder.history_accepts`), so no line is
written the history cannot read back.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ole5_voice.evals.action_card import ActionScorecard, Share
from ole5_voice.evals.models import Commit, Model, Name, Sha256, Split
from ole5_voice.evals.runs import SCORECARD_FILE, Note, Shown
from ole5_voice.evals.talker_data import ModelName
from ole5_voice.evals.talker_score import PriceShown, Session

_Share = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
_Usd = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class ActionLine(Model):
    """One line of `history.jsonl` for a session of a `poe eval-actions` run: its model, the
    judge's, the split, how many times each scenario was played, the registered metrics and
    whether each target held, the hard constraint and the violations, the stray count, whether
    the run passed, each dev scenario's passing plays, and the session's requests, tokens,
    prices and cost."""

    kind: Literal["actions"] = "actions"
    time: datetime
    commit: Commit
    run: Name
    model: ModelName
    judge_model: ModelName
    settings: Shown
    split: Split
    repeats: int = Field(ge=1)
    scenarios: int = Field(ge=0)
    plays: int = Field(ge=0)
    failures: int = Field(ge=0)
    action: _Share | None
    type: _Share | None
    summary: _Share | None
    language: _Share | None
    violations: int = Field(ge=0)
    stray_characters: int = Field(default=0, ge=0)
    held: bool | None
    targets: dict[Name, bool | None]
    targets_met: bool | None
    passed_run: bool | None
    passed: dict[Name, int]  # each dev scenario's passing plays
    requests: dict[ModelName, int]
    tokens: dict[ModelName, int]
    prices: dict[ModelName, PriceShown]
    estimate_usd: _Usd
    cost_usd: _Usd
    session: int = Field(ge=1)
    stopped: Name | None
    scorecard: str
    data_digest: Sha256
    note: Note
    complete: bool

    @model_validator(mode="after")
    def _held_out_aggregates_only(self) -> Self:
        if self.split == "held-out" and self.passed:
            raise ValueError("a held-out run's line holds no scenario's count")
        return self


def _share(found: Share | None) -> float | None:
    return None if found is None else found.share


def action_line(card: ActionScorecard, session: Session, number: int, scenarios: int) -> ActionLine:
    """The history line of session `number` (from 1) of a run of A over `scenarios`."""
    run, totals = card.run, card.totals
    return ActionLine(
        time=session.started_at,
        commit=run.commit,
        run=run.name,
        model=run.model,
        judge_model=run.judge_model,
        settings=run.settings,
        split=run.split,
        repeats=run.repeats,
        scenarios=scenarios,
        plays=totals.plays,
        failures=totals.failures,
        action=_share(totals.action),
        type=_share(totals.type),
        summary=_share(totals.summary),
        language=_share(totals.language),
        violations=totals.violations,
        stray_characters=totals.stray_characters,
        held=card.held,
        targets=card.targets,
        targets_met=card.targets_met,
        passed_run=card.passed,
        passed={count.scenario: count.passed for count in card.scenarios},
        requests={spend.model: spend.requests for spend in session.spend},
        tokens={spend.model: spend.input_tokens + spend.output_tokens for spend in session.spend},
        prices=run.prices,
        estimate_usd=run.estimate_usd,
        cost_usd=session.cost_usd,
        session=number,
        stopped=session.stopped,
        scorecard=SCORECARD_FILE,
        data_digest=run.data_digest,
        note=run.note,
        complete=card.complete,
    )
