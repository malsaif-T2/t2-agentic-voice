"""The scenarios of run S (plan 006's registration, "Data"): ten scripted calls, one TOML file
each under `evals/scenarios/`, named by its ID, from the rehearsal and from the owner's word on
flexibility. Scripted calls stand in for a model playing the caller (the plan's Q3).

A scenario has its ID, whether it is one of the rehearsal's steps (`rehearsal`: such a scenario
passes in 3 of 3 runs, any other in 2 of 3), the language its call is held in, notes on what it
tests (never what the data holds), and its turns. A turn holds the caller's words (`says`), when
they are said (`when`: `agent_speaking`, over the reply playing; `tool_running`, while the reply's
search runs; unset, once the agent is silent), how long the call goes on before (`after_s`), and
what is expected of the reply, each optional:

- `search`: the knowledge tool called (true) or not (false);
- `cuts_reply`: the words cut the earlier turn's reply (no expectation says a correction
  cancelled a search: TextCall speaks a turn's words at a calm pace, so a real search has ended
  before they are heard);
- `language`: the tag the reply is held to, read from its own words' script
  (`talker_data.HELD_TO`), and held to Arabic its register too, judged (`REGISTER_CHECKS`);
  `max_words`: the most words the reply says;
- `facts`: what the reply must say or do, each judged; `item`, a dev item of the knowledge set,
  whose expected points' text the judge reads, and whose key facts are the turn's when it names
  none (a held-out item is never named, so no scenario's result shows one);
- `follows`: the reply `repeats` the earlier one, or `continues` it from where it was cut,
  judged (`FOLLOWS` says each in the judge's words).

`problems` lists every rule the committed scenarios break, and
tests/ole5_voice/evals/test_scenarios.py holds it to none inside `poe check`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import Field

from ole5_voice.evals.items import GoldenSetError, read_toml
from ole5_voice.evals.knowledge_set import KnowledgeItem, Text
from ole5_voice.evals.models import Model, Name
from ole5_voice.evals.talker_data import Tag

SCENARIOS_DIR: Final = "scenarios"
SCENARIO_COUNT: Final = 10  # the registration's ten scripted calls
REHEARSAL_COUNT: Final = 6  # the rehearsal's steps 1, 2, 3, 4, 5 and 7
When = Literal["agent_speaking", "tool_running"]
Follows = Literal["repeats", "continues"]
FOLLOWS: Final[Mapping[Follows, str]] = {
    "repeats": "Says again, in short, what the earlier reply said that the caller heard.",
    "continues": (
        "Goes on from where the earlier reply was cut, with what the caller had not heard yet, "
        "and does not start over from the beginning."
    ),
}
# What the judge checks of a reply held to Arabic, beside its words' script.
REGISTER_CHECKS: Final[Mapping[Tag, str]] = {
    "ar-SA": (
        "Speaks Arabic in the Saudi dialect, not in Modern Standard Arabic (English product "
        "terms among it are fine)."
    ),
    "ar": "Speaks Modern Standard Arabic, not a dialect.",
}


class ScriptTurn(Model):
    """One of the caller's turns in a scenario, and what its reply is expected to do."""

    says: Text
    when: When | None = None
    after_s: Annotated[float, Field(ge=0, le=30, allow_inf_nan=False)] = 0.0
    search: bool | None = None
    cuts_reply: bool = False
    language: Tag | None = None
    max_words: int | None = Field(default=None, ge=0)
    item: Name | None = None
    facts: tuple[Text, ...] = ()
    follows: Follows | None = None

    def expectations(self, items: Mapping[str, KnowledgeItem]) -> tuple[str, ...]:
        """What the judge checks the reply against: its facts (or its item's key facts), then
        what it follows and the register of its Arabic, in the judge's words."""
        facts = self.facts or (items[self.item].key_facts if self.item else ())
        follows = (FOLLOWS[self.follows],) if self.follows else ()
        register = REGISTER_CHECKS.get(self.language) if self.language else None
        return (*facts, *follows, *((register,) if register else ()))


class Scenario(Model):
    """One scripted call (the module's docstring)."""

    id: Name
    rehearsal: bool
    language: Tag
    notes: Text
    turns: tuple[ScriptTurn, ...] = Field(min_length=1, max_length=6)


def load_scenarios(folder: Path) -> tuple[Scenario, ...]:
    """Every scenario under `folder`, one TOML file each named by its ID, in the order of their
    IDs; GoldenSetError naming a file that cannot be read, or holds another ID."""
    if not folder.is_dir():
        raise GoldenSetError(f"{folder.name}: no such folder of scenarios")
    found = []
    for path in sorted(folder.glob("*.toml")):
        scenario = read_toml(path, Scenario)
        if scenario.id != path.stem:
            raise GoldenSetError(f"{path.name}: holds the scenario '{scenario.id}'")
        found.append(scenario)
    return tuple(found)


def problems(scenarios: Sequence[Scenario], items: Sequence[KnowledgeItem]) -> list[str]:
    """Every rule the scenarios break against the knowledge set's `items`."""
    found = []
    if len(scenarios) != SCENARIO_COUNT:
        found.append(f"{len(scenarios)} scenarios, not the registered {SCENARIO_COUNT}")
    if (rehearsal := sum(s.rehearsal for s in scenarios)) != REHEARSAL_COUNT:
        found.append(f"{rehearsal} of the rehearsal's scenarios, not {REHEARSAL_COUNT}")
    twice = [name for name, n in Counter(s.id for s in scenarios).items() if n > 1]
    found += [f"the scenario '{name}' twice" for name in sorted(twice)]
    by_id = {item.id: item for item in items}
    for scenario in scenarios:
        for number, turn in enumerate(scenario.turns, start=1):
            where = f"{scenario.id}, turn {number}"
            found += [f"{where}: {problem}" for problem in _turn_problems(turn, number, by_id)]
    return found


def _turn_problems(turn: ScriptTurn, number: int, items: Mapping[str, KnowledgeItem]) -> list[str]:
    found = []
    if number == 1 and (turn.when or turn.cuts_reply or turn.follows):
        found.append("the first turn follows no reply")
    if turn.cuts_reply and turn.when != "agent_speaking":
        found.append("cuts a reply only when said over it (when = agent_speaking)")
    if turn.item is not None:
        item = items.get(turn.item)
        if item is None:
            found.append(f"names '{turn.item}', which the knowledge set does not hold")
        elif item.split != "dev":
            found.append(f"names '{turn.item}', a held-out item, whose answers are read as counts")
    expects = (turn.search, turn.language, turn.max_words, turn.follows)
    if all(value is None for value in expects) and not (turn.facts or turn.item or turn.cuts_reply):
        found.append("expects nothing of its reply")
    return found
