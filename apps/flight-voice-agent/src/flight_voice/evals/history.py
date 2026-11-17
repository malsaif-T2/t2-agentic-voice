"""The history line of a run of the flight agent's scripted calls (`HistoryLine`), one a session,
appended to the app's `evals/history.jsonl` (evals/run.py): the library's day counter
(`requests_today`) reads its `time` and its `requests`, each model's requests that session, so a
run of either app counts the key's day. It names the agent played (`scripted` or `lean`, D-113),
so the two compare by scenario; a line kept before is the scripted agent's.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from flight_voice.evals.scenarios import Split
from flight_voice.evals.score import Scorecard, Session, Stopped
from flight_voice.settings import AgentKind


class HistoryLine(BaseModel):
    """One session's line in the app's run history (the module's docstring)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["flights"] = "flights"
    time: datetime
    run: str
    agent: AgentKind = "scripted"
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
        agent=run.agent,
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
