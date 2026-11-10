"""What run A makes of one play (plan 007's "The measurement, registered before any result"):
each turn's checks, read from the turn as heard and what the call did after it
(`action_call.TurnFound`) with the judge's answers, and the play's own.

**A turn's checks**, each None when its scenario expects nothing of it:
- `calls`: its reply called the ticket tool named, or none of them for `nothing`;
- `search`, `cut`, `language` and `in_register`, as run S's (scenario_score.py);
- `outcome`, what the call did next: a draft read back after it, whole as the caller next spoke
  (`read_back`, `read_again`), and no write confirmed by it; asked again; `ignored`, nothing
  confirmed and the read-back said over still whole at the call's end; `stopped`, nothing
  confirmed and nothing read back; the write of the action the scenario last called ended as
  `done`, `failed` or `unknown`, its sending line and then its outcome's said; `declined`,
  nothing confirmed or read back and no model request (the session's own line); `talker`, the
  same with the talker asked and heard;
- `says_number`: `whole`, the whole number of a ticket the call made in the reply's digits, or
  the turn's write `done`, whose line is Ole5's own and says it whole (tickets/lines.py, Q6:
  `TextTurn` holds no outcome line, which answers no turn); `last_four`, the last four digits
  of one of the caller's tickets made through the agent, and no whole number; `none`, no run
  of four digits or more;
- `judged`: the judge's checks of its `facts`, the scenario's passage given as what the reply
  may draw on.

**The play's**: `made`, the tickets the call made for the caller, and `others_made`, for anyone
else; `noted`, the notes it added; `action_right`, the tickets made and the notes added as the
scenario says, none for another customer, and every turn's `calls` right; `type_right`, every
ticket made of the scenario's type; the judge's checks of the last ticket's summary against
`summary_facts`. Its violations: the call's checks (`TextCall.violations`: rules A to C and the
yes rule's), and the scenario's own, a write confirmed by a turn its script gives no yes (no
`done`, `failed` or `unknown` outcome), a ticket made beyond the tickets' writes confirmed, or
a note added beyond the notes' (a write sent twice). A play passes when every check holds and
it has no violation; one with no result (`failure`) is not scored, but keeps its violations: a
call that stuck is checked on the turns said before it did, a turn still being said then taken
to confirm the write its script's yes would.
"""

from __future__ import annotations

import re
from collections.abc import Container, Sequence
from typing import Annotated, Final, Self

from pydantic import Field, model_validator
from t2_agentic_voice.languages import normalize_digits

from ole5_voice.evals.action_call import Acted, TurnFound
from ole5_voice.evals.action_scenarios import (
    ACTIONS,
    ENDED,
    ActionName,
    ActionScenario,
    ActionTurn,
    Kind,
    SaysNumber,
)
from ole5_voice.evals.judge import Checked
from ole5_voice.evals.models import Model, Name
from ole5_voice.evals.talker_data import HELD_TO, Failure, HeardTurn, Register
from ole5_voice.tickets.drafts import ADD_NOTE, MAKERS
from ole5_voice.tickets.values import TicketType

_S = Annotated[float, Field(ge=0, allow_inf_nan=False)]
# The tools a turn's `calls` names, `nothing` meaning none of them was called.
TICKET_TOOLS: Final = frozenset({*ACTIONS, "ticket_status"})
_DIGITS: Final = re.compile("[0-9]+")
NUMBER_SHAPE: Final = re.compile("[0-9]{8}82[0-9]{6}")


class TurnScore(Model):
    """One turn's checks (the module's docstring)."""

    calls: bool | None = None
    search: bool | None = None
    outcome: bool | None = None
    cut: bool | None = None
    language: bool | None = None
    in_register: bool | None = None
    says_number: bool | None = None
    judged: tuple[bool, ...] = ()
    reasons: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        found = [self.calls, self.search, self.outcome, self.cut, self.language]
        found += [self.in_register, self.says_number]
        return all(value is not False for value in found) and all(self.judged)


class ActionPlayRecord(Model):
    """One play of a scenario (the module's docstring): its turns as heard and what came after
    each, their checks, the tickets made and the notes added, the summary judged, the
    violations, whether it passed (None when it has no result), how long it took, and whether it
    was a smoke test's (kept for its violations only)."""

    scenario: Name
    kind: Kind
    repeat: int = Field(ge=1)
    rehearsal: bool
    turns: tuple[HeardTurn, ...] = ()
    found: tuple[TurnFound, ...] = ()
    checks: tuple[TurnScore, ...] = ()
    made: int = Field(default=0, ge=0)
    others_made: int = Field(default=0, ge=0)
    noted: int = Field(default=0, ge=0)
    made_types: tuple[TicketType, ...] = ()
    action_right: bool | None = None
    type_right: bool | None = None
    summary: str | None = None
    summary_judged: tuple[bool, ...] = ()
    summary_reasons: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    passed: bool | None = None
    failure: Failure | None = None
    seconds: _S = 0.0
    smoke: bool = False

    @model_validator(mode="after")
    def _scored_once_answered(self) -> Self:
        if (self.failure is None) != (self.passed is not None):
            raise ValueError("a play passes or fails exactly when nothing failed")
        return self

    @property
    def summary_faithful(self) -> bool | None:
        """Whether the judge found every summary fact in the summary; None when none was
        judged."""
        return all(self.summary_judged) if self.summary_judged else None


def acting(turns: Sequence[ActionTurn], n: int) -> ActionName | None:
    """The action the scenario last called by turn `n`, whose write turn `n`'s outcome is."""
    for turn in reversed(turns[: n + 1]):
        for name in ACTIONS:
            if turn.calls == name:
                return name
    return None


def outcome_held(turns: Sequence[ActionTurn], acted: Acted, n: int) -> bool | None:
    """Whether the call did after turn `n` what its scenario expects (the module's docstring);
    None when it expects nothing."""
    wanted, found, heard = turns[n].outcome, acted.found[n], acted.turns[n]
    if wanted is None:
        return None
    still = not found.confirmed
    if wanted in ENDED:
        action = acting(turns, n)
        return action is not None and found.ended.get(action) == wanted
    if wanted in ("read_back", "read_again"):
        return found.read_back and still
    if wanted == "asked_again":
        return found.asked_again and still
    if wanted == "ignored":
        return still and n > 0 and acted.found[n - 1].kept
    quiet = still and not found.read_back
    if wanted == "stopped":
        return quiet
    if wanted == "declined":
        return quiet and heard.model_requests == 0
    return quiet and heard.model_requests > 0 and bool(heard.said)  # `talker`


def number_said(
    text: str,
    wanted: SaysNumber,
    *,
    made: Sequence[str],
    mine: Sequence[str],
    known: Sequence[str],
    done: bool,
) -> bool:
    """Whether `text`, a reply as heard, says of a ticket number what `wanted` says (the
    module's docstring): `made` the numbers the call made, `mine` those of the caller's tickets
    made through the agent (a seed's or the call's), `known` every number the play knows, and
    `done` whether the turn's write was done, its line said."""
    runs = _DIGITS.findall(normalize_digits(text))
    joined = "".join(runs)
    if wanted == "whole":
        return done or any(number in joined for number in made)
    if wanted == "last_four":
        whole = any(number in joined for number in known)
        return not whole and any(number[-4:] in runs for number in mine)
    return not any(len(run) >= 4 for run in runs)


def _heard_text(turn: HeardTurn) -> str:
    return " ".join(clause.text for clause in turn.clauses if clause.fate != "unplayed")


def checks_of(
    scenario: ActionScenario,
    acted: Acted,
    judged: Sequence[Checked | None],
    registers: Sequence[Register | None],
    *,
    tool: str,
    numbers: tuple[Sequence[str], Sequence[str], Sequence[str]],
) -> tuple[TurnScore, ...]:
    """Each turn's checks (the module's docstring): `judged` and `registers` the judge's for
    each turn (None where not asked), `tool` the knowledge tool's name, `numbers` the play's
    (`made`, `mine` and `known`, as `number_said` takes them)."""
    made, mine, known = numbers
    found = []
    for n, turn in enumerate(scenario.turns):
        heard, checked = acted.turns[n], judged[n]
        earlier = acted.turns[n - 1] if n else None
        called = {use.tool for use in heard.tools} & TICKET_TOOLS
        held = turn.held_registers()
        action = acting(scenario.turns, n)
        done = action is not None and acted.found[n].ended.get(action) == "done"
        said = None
        if turn.says_number is not None:
            text = _heard_text(heard)
            said = number_said(text, turn.says_number, made=made, mine=mine, known=known, done=done)
        found.append(
            TurnScore(
                calls=None
                if turn.calls is None
                else (not called if turn.calls == "nothing" else turn.calls in called),
                search=None if turn.search is None else heard.searched(tool) == turn.search,
                outcome=outcome_held(scenario.turns, acted, n),
                cut=earlier.fate in ("cut", "rolled_back") if turn.cuts_reply and earlier else None,
                language=(
                    None if turn.language is None else heard.written_in(HELD_TO[turn.language][0])
                ),
                in_register=registers[n] in held if held else None,
                says_number=said,
                judged=checked.holds or () if checked else (),
                reasons=checked.reasons if checked else (),
            )
        )
    return tuple(found)


def _writes(scenario: ActionScenario, acted: Acted, names: Container[str | None]) -> int:
    """The writes of the actions `names` the call's turns confirmed; for a call that stuck, with
    those its turns still being said would confirm by their script's yes."""
    writes = sum(name in names for after in acted.found for name in after.confirmed)
    read = len(acted.found)
    return writes + sum(
        scenario.turns[n].outcome in ENDED and acting(scenario.turns, n) in names
        for n in range(read, min(read + acted.unread, len(scenario.turns)))
    )


def unasked(scenario: ActionScenario, acted: Acted, made: int, noted: int = 0) -> tuple[str, ...]:
    """The scenario's own violations (the module's docstring): `made` the tickets the call made,
    for anyone, and `noted` the notes it added; for a call that stuck, on the turns said before
    it did."""
    found = []
    for n, (turn, after) in enumerate(zip(scenario.turns, acted.found, strict=False), start=1):
        if after.confirmed and turn.outcome not in ENDED:
            names = ", ".join(after.confirmed)
            found.append(f"turn {n} confirmed {names}, though its script gives it no yes")
    if made > (writes := _writes(scenario, acted, MAKERS)):
        found.append(f"the call made {made} tickets, and its turns confirmed {writes}")
    if noted > (notes := _writes(scenario, acted, (ADD_NOTE,))):
        found.append(f"the call added {noted} notes, and its turns confirmed {notes}")
    return tuple(found)


def passage_numbers(scenario: ActionScenario) -> tuple[str, ...]:
    """The ticket-shaped numbers the scenario's passage holds."""
    return tuple(NUMBER_SHAPE.findall(scenario.passage or ""))
