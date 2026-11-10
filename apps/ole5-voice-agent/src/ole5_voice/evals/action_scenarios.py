"""The scenarios of plan 007's measurement ("The measurement, registered before any result"):
scripted calls in which the agent acts, one TOML file each under `evals/actions/`, named by its
ID, in Saudi Arabic, MSA and English, each split into dev or held-out before any run. They
extend run S's scenarios (scenarios.py) with what an action needs; a scenario is played as one
call through `TextCall`, against the mock ticket system (ole5_voice/tickets/mock.py), by run A
(`poe eval-actions`, action_run.py).

**A scenario** has its ID, its `kind` (one of the registered 15, `KINDS`), its `split`, whether
it is one of the rehearsal's steps (`rehearsal`: step 6, a yes with a send word over the
closing question, and step 3, a request for a person over an answer), the language its call is
held in, notes on what it tests, and how the mock answers: `tickets_mode` for its writes
(`answer`, `refuse`, `timeout` or `late`) and `lookup`, whether it can find a write by its
request ID. `seed` holds
the tickets the mock holds before the call, the caller's (made through the agent, so in the
outbox, or not) and another customer's; `passage` a knowledge-base passage the search returns,
for the scenario with a fake number. What the call leaves: `made`, the tickets it makes for the
caller, the action rightly taken or rightly not; `ticket_type`, the type such a ticket is right
to hold; `summary_facts`, what a summary judged faithful says.

**A turn** holds the caller's words (`says`), when they are said (`when`: run S's two, or
`read_back`, over the read-back's summary, and `closing_question`, over its question), how long
the call goes on before (`after_s`), and what is expected, each optional: `calls`, the ticket
tool the reply calls (`nothing` for none); `search`; `outcome`, what the call does next (a
read-back played; yes words over the summary ignored; asked again; read again; stopped; the
`done`, `failed` or `unknown` line; the `declined` line; or the talker answering in its own
words); `cuts_reply`; `language`; `says_number`, what the agent says of a ticket number (whole,
the last four digits, or none); and `facts`, each judged.

The hard constraint is the scenarios', not a turn's: no unrecorded claim and no action without
a yes, in every run. `problems` lists every rule the committed scenarios break, and
tests/ole5_voice/evals/test_action_scenarios.py holds it to none inside `poe check`.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, Literal, get_args

from pydantic import Field

from ole5_voice.evals.items import GoldenSetError, read_toml
from ole5_voice.evals.knowledge_set import Text
from ole5_voice.evals.models import Model, Name
from ole5_voice.evals.scenarios import ScriptTurn
from ole5_voice.evals.talker_data import Register, Tag
from ole5_voice.tickets.mock import Mode
from ole5_voice.tickets.system import NUMBER_PATTERN
from ole5_voice.tickets.values import Status, TicketType

ACTIONS_DIR: Final = "actions"
Kind = Literal[
    "plain_ticket",
    "eager_yes",
    "bare_yes",
    "yes_over_summary",
    "correction_in_read_back",
    "no",
    "mumble",
    "refusal",
    "timeout_with_lookup",
    "timeout_without_lookup",
    "own_status",
    "others_status",
    "handoff_over_answer",
    "handoff_by_mistake",
    "fake_number_passage",
]
KINDS: Final[tuple[Kind, ...]] = get_args(Kind)
Split = Literal["dev", "held-out"]
SPLITS: Final[tuple[Split, ...]] = get_args(Split)
LANGUAGES: Final[tuple[Tag, ...]] = get_args(Tag)
REHEARSAL: Final[frozenset[Kind]] = frozenset({"bare_yes", "handoff_over_answer"})
When = Literal["agent_speaking", "tool_running", "read_back", "closing_question"]
ActionName = Literal["create_ticket", "add_ticket_note", "hand_off"]
ACTIONS: Final[tuple[ActionName, ...]] = get_args(ActionName)
Called = Literal["create_ticket", "add_ticket_note", "hand_off", "ticket_status", "nothing"]
Outcome = Literal[
    "read_back",
    "ignored",
    "asked_again",
    "read_again",
    "stopped",
    "done",
    "failed",
    "unknown",
    "declined",
    "talker",
]
# The outcomes after which the caller is still asked to confirm, so the next words may be said
# over the read-back or its question; and those that end a confirmed write.
CONFIRMING: Final[frozenset[Outcome]] = frozenset(
    {"read_back", "ignored", "asked_again", "read_again"}
)
ENDED: Final[frozenset[Outcome]] = frozenset({"done", "failed", "unknown"})
SaysNumber = Literal["whole", "last_four", "none"]
Number = Annotated[str, Field(pattern=NUMBER_PATTERN)]


class SeedTicket(Model):
    """A ticket the mock holds before the call: whose (`owner`), whether it was made through
    the agent for the caller (`through_agent`, so the outbox lists it) and by which action, its
    number, type, status and summary."""

    owner: Literal["caller", "other"]
    through_agent: bool = False
    by: Literal["create_ticket", "hand_off"] = "create_ticket"
    number: Number
    type: TicketType
    status: Status
    summary: Text


class ActionTurn(Model):
    """One of the caller's turns, and what is expected of the call after it (the module's
    docstring)."""

    says: Text
    when: When | None = None
    after_s: Annotated[float, Field(ge=0, le=30, allow_inf_nan=False)] = 0.0
    calls: Called | None = None
    search: bool | None = None
    outcome: Outcome | None = None
    cuts_reply: bool = False
    language: Tag | None = None
    says_number: SaysNumber | None = None
    facts: tuple[Text, ...] = ()

    def held_registers(self) -> frozenset[Register]:
        """The registers its reply is right in when held to Arabic, as a turn of run S's is
        (scenarios.py's `ScriptTurn.held_registers`); none when it is not."""
        return ScriptTurn(says=self.says, language=self.language).held_registers()


class ActionScenario(Model):
    """One scripted call in which the agent may act (the module's docstring)."""

    id: Name
    kind: Kind
    split: Split
    rehearsal: bool = False
    language: Tag
    notes: Text
    tickets_mode: Mode = "answer"
    lookup: bool = True
    seed: tuple[SeedTicket, ...] = ()
    passage: Text | None = None
    made: int = Field(ge=0, le=2)
    ticket_type: TicketType | None = None
    summary_facts: tuple[Text, ...] = ()
    turns: tuple[ActionTurn, ...] = Field(min_length=1, max_length=6)


@dataclass(frozen=True)
class _Rule:
    """What a kind of scenario must hold: the mock's mode, the tickets made, the outcomes its
    turns reach, the tool one of them calls, and the mock's lookup (None: either)."""

    mode: Mode
    made: int
    outcomes: tuple[Outcome, ...] = ()
    calls: Called | None = None
    lookup: bool | None = None


_TICKET: Final = "create_ticket"
RULES: Final[Mapping[Kind, _Rule]] = {
    "plain_ticket": _Rule("answer", 1, ("read_back", "done"), _TICKET),
    "eager_yes": _Rule("answer", 1, ("read_back", "done"), _TICKET),
    "bare_yes": _Rule("answer", 1, ("asked_again", "done"), _TICKET),
    "yes_over_summary": _Rule("answer", 1, ("ignored", "done"), _TICKET),
    "correction_in_read_back": _Rule("answer", 1, ("read_back", "done"), _TICKET),
    "no": _Rule("answer", 0, ("read_back", "talker"), _TICKET),
    "mumble": _Rule("answer", 1, ("asked_again", "done"), _TICKET),
    "refusal": _Rule("refuse", 0, ("failed",), _TICKET),
    "timeout_with_lookup": _Rule("late", 1, ("done",), _TICKET, lookup=True),
    "timeout_without_lookup": _Rule("late", 1, ("unknown",), _TICKET, lookup=False),
    "own_status": _Rule("answer", 0, (), "ticket_status"),
    "others_status": _Rule("answer", 0),
    "handoff_over_answer": _Rule("answer", 1, ("read_back", "done"), "hand_off"),
    "handoff_by_mistake": _Rule("answer", 0, ("read_back", "talker"), "hand_off"),
    "fake_number_passage": _Rule("answer", 0),
}


def load_action_scenarios(folder: Path) -> tuple[ActionScenario, ...]:
    """Every scenario under `folder`, one TOML file each named by its ID, in the order of their
    IDs; GoldenSetError naming a file that cannot be read, or holds another ID."""
    if not folder.is_dir():
        raise GoldenSetError(f"{folder.name}: no such folder of scenarios")
    found = []
    for path in sorted(folder.glob("*.toml")):
        scenario = read_toml(path, ActionScenario)
        if scenario.id != path.stem:
            raise GoldenSetError(f"{path.name}: holds the scenario '{scenario.id}'")
        found.append(scenario)
    return tuple(found)


def problems(scenarios: Sequence[ActionScenario]) -> list[str]:
    """Every rule the scenarios break: each kind once in dev and once in held-out, every
    language in each split, the rehearsal's two steps, and each scenario's own rules."""
    found = []
    twice = [name for name, n in Counter(s.id for s in scenarios).items() if n > 1]
    found += [f"the scenario '{name}' twice" for name in sorted(twice)]
    for kind in KINDS:
        splits = sorted(s.split for s in scenarios if s.kind == kind)
        if splits != sorted(SPLITS):
            found.append(f"the kind '{kind}' is in {splits or 'no split'}, not once in each")
    for split in SPLITS:
        held = {s.language for s in scenarios if s.split == split}
        found += [f"{split} has no scenario in {tag}" for tag in LANGUAGES if tag not in held]
    rehearsed = sorted((s.kind, s.language, s.split) for s in scenarios if s.rehearsal)
    wanted = sorted((kind, "ar-SA", "dev") for kind in REHEARSAL)
    if rehearsed != wanted:
        found.append(f"the rehearsal's scenarios are {rehearsed}, not {wanted}")
    for scenario in scenarios:
        found += [f"{scenario.id}: {problem}" for problem in _scenario_problems(scenario)]
    return found


def _scenario_problems(scenario: ActionScenario) -> list[str]:
    rule = RULES[scenario.kind]
    found = []
    if scenario.tickets_mode != rule.mode:
        found.append(f"its kind runs the mock in mode {rule.mode}")
    if rule.lookup is not None and scenario.lookup != rule.lookup:
        found.append(f"its kind runs the mock with lookup {rule.lookup}")
    if scenario.made != rule.made:
        found.append(f"its kind makes {rule.made} tickets")
    outcomes = {turn.outcome for turn in scenario.turns}
    found += [f"no turn reaches {each}" for each in rule.outcomes if each not in outcomes]
    if rule.calls is not None and rule.calls not in {turn.calls for turn in scenario.turns}:
        found.append(f"no turn calls {rule.calls}")
    if (scenario.made > 0) != (scenario.ticket_type is not None):
        found.append("a ticket_type is given exactly when a ticket is made")
    if scenario.summary_facts and scenario.made == 0:
        found.append("summary_facts judge a summary, so a ticket is made")
    if (scenario.passage is not None) != (scenario.kind == "fake_number_passage"):
        found.append("only the fake number's scenario has a passage, and it has one")
    found += _seed_problems(scenario)
    previous: ActionTurn | None = None
    for number, turn in enumerate(scenario.turns, start=1):
        found += [f"turn {number}: {each}" for each in _turn_problems(turn, previous)]
        previous = turn
    return found


def _seed_problems(scenario: ActionScenario) -> list[str]:
    found = []
    numbers = [ticket.number for ticket in scenario.seed]
    if len(set(numbers)) != len(numbers):
        found.append("two seed tickets share a number")
    if any(t.owner == "other" and t.through_agent for t in scenario.seed):
        found.append("another customer's ticket was never made through this caller's agent")
    owners = {(t.owner, t.through_agent) for t in scenario.seed}
    if scenario.kind == "own_status" and ("caller", True) not in owners:
        found.append("the caller has no ticket made through the agent to ask about")
    if scenario.kind == "others_status":
        theirs = [t.number for t in scenario.seed if t.owner == "other"]
        said = " ".join(turn.says for turn in scenario.turns)
        if not any(number[-4:] in said for number in theirs):
            found.append("no turn says another customer's ticket number")
    if scenario.passage is not None:
        shaped = re.findall("[0-9]{8}82[0-9]{6}", scenario.passage)
        if not shaped or set(shaped) & set(numbers):
            found.append("the passage holds no fake ticket number, or one the mock holds")
    return found


def _turn_problems(turn: ActionTurn, previous: ActionTurn | None) -> list[str]:
    found = []
    confirming = previous is not None and previous.outcome in CONFIRMING
    if previous is None and (turn.when or turn.cuts_reply):
        found.append("the first turn follows no reply")
    if turn.cuts_reply and turn.when != "agent_speaking":
        found.append("cuts a reply only when said over it (when = agent_speaking)")
    if turn.when in ("read_back", "closing_question") and not confirming:
        found.append("is said over a read-back, but none is playing")
    over = ("read_back", "closing_question")
    # Asked again once the read-back ended: only the ask-again line plays, which is no read-back.
    asked = previous is not None and previous.outcome == "asked_again" and previous.when not in over
    if turn.when in over and asked:
        found.append("is said over a read-back, but only the ask-again line plays")
    if turn.outcome in ENDED | {"ignored", "asked_again", "declined"} and not confirming:
        found.append(f"reaches {turn.outcome}, but nothing is being confirmed")
    if turn.outcome in ("read_back", "read_again") and turn.calls not in (*ACTIONS, None):
        found.append("a read-back follows only an action's call")
    if turn.outcome == "read_back" and turn.calls is None and not confirming:
        found.append("a read-back follows an action's call, so it names the action")
    expects = (turn.calls, turn.search, turn.outcome, turn.language, turn.says_number)
    if all(value is None for value in expects) and not (turn.facts or turn.cuts_reply):
        found.append("expects nothing of its reply")
    return found
