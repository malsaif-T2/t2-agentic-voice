"""What run A checks before anything is sent (action_run.py), beside what runs K and S share
(talker_args.py):

- **The scenarios**, read from `evals/actions/` and refused when one cannot be read or the set
  breaks a rule (`action_scenarios.problems`).
- **The agent**: the `--agent` factory, given each play's knowledge base and ticket system
  (Ole5's is `ole5_voice.agent:talker_agent`, given them as `tickets=`), refused when it builds
  no `VoiceAgent`, or one without the knowledge tool, the three ticket actions and
  `ticket_status`. It is built once before the run, on a mock it never uses.
- **The dry estimate** of the run's most spend, with no request (`most_usd`): for each play, each
  turn's most talker requests (`TALKER_REQUESTS`), the judge's most for each turn's facts, its
  register when it is held to Arabic, and the summary (`JUDGE_ATTEMPTS` each), one request on
  an uncertain overlap for each turn said over the agent (`OVERLAP`), and one of the yes rule's
  check (`CHECK`, D-082) for each turn that answers a read-back once its summary played (the
  turn after one whose outcome still confirms, not said over the summary): the lists leave some
  of those unplaced, which ones is the library's reading, so each counts, as each overlap does;
  every request reading `--input-budget-tokens` and writing its model's most. The run is
  refused when what it
  spent and the estimate of what is left pass `--cap-usd`, and a held-out run, which is never
  resumed, when its requests would pass a model's daily limit (`check_estimate`).
- **Held-out read once**: whether the shared history holds a complete held-out run of A
  (`held_out_done`).
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Final

from t2_agentic_voice import VoiceAgent, get_logger
from t2_agentic_voice.evals import consent_check_request, uncertain_overlap_request
from t2_agentic_voice.ports import KnowledgeBase

from ole5_voice.evals.action_scenarios import (
    ACTIONS,
    CONFIRMING,
    ActionScenario,
    load_action_scenarios,
)
from ole5_voice.evals.action_scenarios import problems as scenario_problems
from ole5_voice.evals.chat_pacing import OUTPUT_BUDGET, PacedChat
from ole5_voice.evals.history import read_history
from ole5_voice.evals.items import GoldenSetError
from ole5_voice.evals.judge import JUDGE_ATTEMPTS
from ole5_voice.evals.talker_measure import TALKER_REQUESTS
from ole5_voice.evals.worktree import refused
from ole5_voice.tickets.mock import MockTicketSystem
from ole5_voice.tickets.status import TICKET_STATUS
from ole5_voice.tickets.system import TicketSystem

# The tools besides the knowledge tool an agent of run A has: the actions and the status tool.
TICKET_TOOLS: Final = (*ACTIONS, TICKET_STATUS)
# The request a call's session sends on an overlap the interruption rule leaves uncertain
# (`VoiceAgent.ask_on_uncertain_overlaps`): its model and bound, the library's; and when a
# turn is said over the agent, so that one may be sent.
OVERLAP: Final = uncertain_overlap_request("-", "-")
OVER: Final = frozenset({"agent_speaking", "read_back", "closing_question"})
# The request a call's session sends on an answer to a read-back that the yes rule's lists leave
# unplaced (`VoiceAgent.ask_on_unlisted_answers`, D-082): its model and bound, the library's.
CHECK: Final = consent_check_request("-", "-", "-")
_UNUSED: Final = Path("run-a-probe")  # the folder of the mock the check builds, never used
log = get_logger(__name__)


def load_scenarios(folder: Path) -> tuple[ActionScenario, ...]:
    """The scenarios under `folder` (the module's docstring)."""
    try:
        found = load_action_scenarios(folder)
    except GoldenSetError as error:
        raise refused(f"the scenarios cannot be read ({error})", "fix them; `poe check`") from None
    if broken := scenario_problems(found):
        raise refused(f"the scenarios break {len(broken)} rule(s), first: {broken[0]}", "fix them")
    return found


@dataclass(frozen=True)
class AgentFactory:
    """The `--agent` factory `spec` names, `factory`, as each play calls it: on its knowledge
    base and its ticket system; refused when it builds no `VoiceAgent`."""

    factory: Callable[..., object]
    spec: str

    def __call__(self, kb: KnowledgeBase, tickets: TicketSystem) -> VoiceAgent:
        agent = self.factory(kb, tickets=tickets)
        if not isinstance(agent, VoiceAgent):
            raise refused(f"--agent {self.spec} gave no VoiceAgent", "name the agent's factory")
        return agent


def checked_agent(make: AgentFactory, kb: KnowledgeBase, search_tool: str) -> VoiceAgent:
    """The agent `make` builds on `kb` and an unused mock, refused when it lacks the knowledge
    tool `search_tool` or a ticket tool."""
    agent = make(kb, MockTicketSystem(_UNUSED))
    names = {tool.name for tool in agent.tools}
    if lacking := [name for name in (search_tool, *TICKET_TOOLS) if name not in names]:
        raise refused(
            f"the agent has no tool {', '.join(lacking)}",
            "give the factory of an agent with its knowledge tool and the ticket tools",
        )
    return agent


def _asked(scenario: ActionScenario) -> int:
    """The judge's questions of one play of `scenario`, each asked `JUDGE_ATTEMPTS` times at
    most: each turn's facts and register, and the summary."""
    turns = sum(bool(t.facts) + bool(t.held_registers()) for t in scenario.turns)
    return turns + bool(scenario.summary_facts)


def _answers(scenario: ActionScenario) -> int:
    """The turns of `scenario` that answer a read-back once its summary played: each after a
    turn whose outcome still confirms, but one said over the summary, which counts for
    nothing."""
    return sum(
        before.outcome in CONFIRMING and turn.when != "read_back"
        for before, turn in pairwise(scenario.turns)
    )


def asks(args: argparse.Namespace, scenario: ActionScenario) -> tuple[tuple[str, int, int], ...]:
    """The most requests one play of `scenario` sends, each model's with the most each writes:
    the talker's, the judge's, an uncertain overlap's for each turn said over the agent, and the
    yes rule's check for each turn that answers a read-back (`_answers`)."""
    over = sum(turn.when in OVER for turn in scenario.turns)
    return (
        (args.model, TALKER_REQUESTS * len(scenario.turns), args.max_output_tokens),
        (args.judge_model, JUDGE_ATTEMPTS * _asked(scenario), args.judge_max_output_tokens),
        (OVERLAP.model, over, OVERLAP.max_output_tokens or OUTPUT_BUDGET),
        (CHECK.model, _answers(scenario), CHECK.max_output_tokens or OUTPUT_BUDGET),
    )


def requests_of(args: argparse.Namespace, plays: Sequence[ActionScenario]) -> Mapping[str, int]:
    """The most requests `plays` send to each model."""
    found: Counter[str] = Counter()
    for scenario in plays:
        for model, n, _ in asks(args, scenario):
            found[model] += n
    return found


def most_usd(args: argparse.Namespace, paced: PacedChat, plays: Sequence[ActionScenario]) -> float:
    """The most `plays` spend (the module's docstring), at the run's prices; a model with no
    price is never sent a request (`chat_pacing`)."""
    prices, read = paced.spend.prices, args.input_budget_tokens
    return sum(
        n * prices[model].of(read, written)
        for scenario in plays
        for model, n, written in asks(args, scenario)
        if model in prices
    )


def check_estimate(
    args: argparse.Namespace,
    paced: PacedChat,
    plays: Sequence[ActionScenario],
    *,
    whole_day: bool,
) -> None:
    """The run refused when what it spent and the most `plays` spend pass the cap, and, with
    `whole_day` (a held-out run), when their requests would pass a model's daily limit."""
    most, spent = most_usd(args, paced, plays), paced.spend.cost_usd()
    log.info("run_estimate", plays=len(plays), most_usd=round(most, 4), spent_usd=round(spent, 4))
    if spent + most > args.cap_usd:
        raise refused(
            f"its most spend, {most:.4f} USD, with {spent:.4f} spent, passes --cap-usd "
            f"{args.cap_usd:g}",
            "lower --input-budget-tokens or --max-output-tokens, or raise the cap within the "
            "plan's",
        )
    for model, n in requests_of(args, plays).items() if whole_day else ():
        if (pacer := paced.pacers.get(model)) is None:
            continue
        if (left := pacer.limits.rpd - pacer.today) < n:
            raise refused(
                f"{model}'s daily limit leaves {left} requests today, and the run may send {n}",
                "run it on a day with room, since a held-out run is never resumed",
            )


def held_out_done(history: Path) -> bool:
    """Whether the shared history at `history` holds a complete held-out run of A."""
    if not history.exists():
        return False
    return any(
        getattr(line, "kind", None) == "actions"
        and getattr(line, "split", None) == "held-out"
        and getattr(line, "complete", False)
        for line in read_history(history)
    )
