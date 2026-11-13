"""The history lines of runs K and S (evaluation.md, "Run history"): one `TalkerLine` for each
session of a `poe eval-talker` run (`talker_line`), one `ScenarioLine` for each session of a
`poe eval-scenarios` run (`scenario_line`), each marked by its `kind`. A session's line counts
what that session sent (every request, the smoke test's and the judge's included), so the
history's spend adds up over a run spread over days; its numbers are the scorecard's after that
session, over every variant so far.

Strict as every history line: a held-out run's breakdowns hold no group of fewer than
`HELD_OUT_MIN_ITEMS` items, and a secret setting is shown only as set or not set. The shared
history reads a line through `run_lines.AnyLine`, which names each kind it takes: until it names
these two, a run refuses to start (`run_folder.history_accepts`), so no line is written that the
history cannot read back.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ole5_voice.evals.models import Commit, Model, Name, Sha256, Split
from ole5_voice.evals.runs import SCORECARD_FILE, ModelName, Note, Shown, check_groups
from ole5_voice.evals.scenario_score import ScenarioScorecard
from ole5_voice.evals.talker_score import (
    PriceShown,
    Rate,
    Session,
    TalkerScorecard,
    requests_of,
    tokens_of,
)

_Share = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
_Usd = Annotated[float, Field(ge=0, allow_inf_nan=False)]
_S = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class TalkerCount(Model):
    """One stratum value of a run of K: its items and variants, its failures, and its shares
    of right answers (answerable items) and of passing verdicts (every kind), by item."""

    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    failures: int = Field(ge=0)
    answers: _Share | None
    passed: _Share | None


class TalkerLine(Model):
    """One line of `history.jsonl` for a session of a `poe eval-talker` run (the module's
    docstring): its arm and models, the registered metrics by item (the reply language's by
    variant), the guard's blocks and violations, the first clause's median, whether each target
    held, the numbers by stratum value, and the session's requests, tokens, prices and cost."""

    kind: Literal["talker"] = "talker"
    time: datetime
    commit: Commit
    run: Name
    arm: Name
    model: ModelName
    judge_model: ModelName
    settings: Shown
    split: Split
    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    failures: int = Field(ge=0)
    answers: _Share | None
    honest: _Share | None
    retrieval: _Share | None
    retrieval_raw: _Share | None
    search: _Share | None
    language: _Share | None
    words_median: _S | None
    first_clause_median_s: _S | None  # on the wall clock, the tools' time in it
    own_first_clause_median_s: _S | None = None  # the model's own, the keep rule's (Q15)
    blocked: int = Field(ge=0)
    violations: int = Field(ge=0)
    targets: dict[Name, bool | None]
    breakdowns: dict[str, dict[str, TalkerCount]]  # by language and by kind
    requests: dict[ModelName, int]
    tokens: dict[ModelName, int]  # read and written
    prices: dict[ModelName, PriceShown]
    cost_usd: _Usd  # this session's
    session: int = Field(ge=1)
    stopped: Name | None
    scorecard: str
    data_digest: Sha256
    note: Note
    complete: bool

    @model_validator(mode="after")
    def _held_out_groups(self) -> Self:
        counts = [value.items for values in self.breakdowns.values() for value in values.values()]
        check_groups(self.split, self.items, counts, "stratum values")
        return self


class ScenarioLine(Model):
    """One line of `history.jsonl` for a session of a `poe eval-scenarios` run: its model, the
    judge's, how many times each scenario was played and how many passed, whether every
    scenario met its target, the guard's violations, and the session's requests, tokens,
    prices and cost."""

    kind: Literal["scenarios"] = "scenarios"
    time: datetime
    commit: Commit
    run: Name
    model: ModelName
    judge_model: ModelName
    settings: Shown
    repeats: int = Field(ge=1)
    scenarios: int = Field(ge=0)
    plays: int = Field(ge=0)
    failures: int = Field(ge=0)
    passed: dict[Name, int]  # each scenario's passing plays
    targets_met: bool | None
    violations: int = Field(ge=0)
    requests: dict[ModelName, int]
    tokens: dict[ModelName, int]
    prices: dict[ModelName, PriceShown]
    cost_usd: _Usd
    session: int = Field(ge=1)
    stopped: Name | None
    scorecard: str
    data_digest: Sha256
    note: Note
    complete: bool


def _share(found: Rate | None) -> float | None:
    return None if found is None else found.item_rate


def talker_line(card: TalkerScorecard, session: Session, number: int) -> TalkerLine:
    """The history line of session `number` (from 1) of a run of K, its numbers the scorecard's
    after that session."""
    run, totals = card.run, card.totals
    return TalkerLine(
        time=session.started_at,
        commit=run.commit,
        run=run.name,
        arm=run.arm,
        model=run.model,
        judge_model=run.judge_model,
        settings=run.settings,
        split=run.split,
        items=totals.items,
        variants=totals.variants,
        failures=totals.failures,
        answers=_share(totals.answers),
        honest=_share(totals.honest),
        retrieval=_share(totals.retrieval),
        retrieval_raw=_share(totals.retrieval_raw),
        search=_share(totals.search),
        language=None if totals.language is None else totals.language.rate,
        words_median=totals.words_median,
        first_clause_median_s=totals.first_clause_median_s,
        own_first_clause_median_s=totals.own_first_clause_median_s,
        blocked=totals.blocked,
        violations=totals.violations,
        targets=card.targets,
        breakdowns={
            stratum: {
                value: TalkerCount(
                    items=m.items,
                    variants=m.variants,
                    failures=m.failures,
                    answers=_share(m.answers),
                    passed=_share(m.passed),
                )
                for value, m in values.items()
            }
            for stratum, values in card.breakdowns.items()
        },
        requests=requests_of(session),
        tokens=tokens_of(session),
        prices=run.prices,
        cost_usd=session.cost_usd,
        session=number,
        stopped=session.stopped,
        scorecard=SCORECARD_FILE,
        data_digest=run.data_digest,
        note=run.note,
        complete=card.complete,
    )


def scenario_line(card: ScenarioScorecard, session: Session, number: int) -> ScenarioLine:
    """The history line of session `number` (from 1) of a run of S."""
    run = card.run
    return ScenarioLine(
        time=session.started_at,
        commit=run.commit,
        run=run.name,
        model=run.model,
        judge_model=run.judge_model,
        settings=run.settings,
        repeats=run.repeats,
        scenarios=len(card.scenarios),
        plays=sum(count.plays for count in card.scenarios),
        failures=sum(count.failures for count in card.scenarios),
        passed={count.scenario: count.passed for count in card.scenarios},
        targets_met=card.targets_met,
        violations=card.violations,
        requests=requests_of(session),
        tokens=tokens_of(session),
        prices=run.prices,
        cost_usd=session.cost_usd,
        session=number,
        stopped=session.stopped,
        scorecard=SCORECARD_FILE,
        data_digest=run.data_digest,
        note=run.note,
        complete=card.complete,
    )
