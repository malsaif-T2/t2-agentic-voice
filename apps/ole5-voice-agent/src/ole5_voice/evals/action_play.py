"""The playing part of a `poe eval-actions` run (action_run.py): one play of a scenario as one
call through `action_call.act`, within `--variant-timeout-s` for each of its turns, against what
it acts on, made new for the play (action_backend.py): the mock ticket system in the play's own
folder (kept under `--out` for a dev run, in a temporary folder removed after the play for a
held-out one), the outbox, and the agent the `--agent` factory builds on the knowledge base,
the scenario's passage first, and that mock.

Then it is checked (action_score.py): the judge reads each turn that expects facts, with the
call so far as the caller heard it and the scenario's passage, the register of each reply held
to Arabic in a question of its own (judge.py's `Judge.register`), and the last ticket the call
made, its summary against the scenario's `summary_facts`, as the reply to the caller's words. A
provider's failure (in the call, its searches or a model request the talker caught) makes the
play a `provider` failure, its limit passed (or a moment the call waited for in vain) a `stuck`
one, and a judge with no valid answer, or no clear register, a `judge` one. A play with no
result keeps its violations all the same: the call's, and the scenario's own read from the turns
said before it stopped (action_score.py's `unasked`), checked before the judge is asked. When
the cap or the key's daily limit stops a request (`chat_pacing`), the play is dropped unscored
(`StopRun`), so a resumed run plays it again.
"""

from __future__ import annotations

import contextlib
import tempfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from t2_agentic_voice import ProviderError, VoiceAgent, VoiceSettings
from t2_agentic_voice.ports import KnowledgeBase

from ole5_voice.evals.action_backend import (
    CALLER,
    CUSTOMER,
    PassageFirst,
    fresh_folder,
    seed_tickets,
    seeded_mock,
    seeded_outbox,
)
from ole5_voice.evals.action_call import Acted, ActionCallFactory, act
from ole5_voice.evals.action_scenarios import ActionScenario
from ole5_voice.evals.action_score import ActionPlayRecord, checks_of, passage_numbers, unasked
from ole5_voice.evals.chat_pacing import CapReachedError, DailyLimitError, PacedChat
from ole5_voice.evals.groq_answerer import Clock
from ole5_voice.evals.judge import Checked, Judge, Registered
from ole5_voice.evals.kb_points import RecordingKnowledge
from ole5_voice.evals.talker_data import Clause, Failure, HeardTurn
from ole5_voice.evals.talker_measure import StopRun, stop_of
from ole5_voice.tickets.mock import MockTicket
from ole5_voice.tickets.system import TicketSystem

# Builds the agent a play measures, on its knowledge base and its ticket system.
AgentOf = Callable[[KnowledgeBase, TicketSystem], VoiceAgent]
# What a call that failed before any turn was read did: nothing.
_NOTHING: Final = Acted(turns=(), found=(), violations=())


@dataclass
class ActionPlaying:
    """One run's playing: the agent's factory, the call's settings, the paced model, the
    recorded knowledge base, the judge, the knowledge tool's name, each turn's limit, the call,
    the clock, and the folder each play's mock is kept in (None: kept nowhere)."""

    agent: AgentOf
    paced: PacedChat
    settings: VoiceSettings
    knowledge: RecordingKnowledge
    judge: Judge
    search_tool: str
    timeout_s: float
    call: ActionCallFactory
    clock: Clock
    kept: Path | None

    async def play(self, scenario: ActionScenario, repeat: int, *, name: str) -> ActionPlayRecord:
        """One play of `scenario`, its mock's folder named `name`, checked; StopRun when the
        cap or the day's limit stopped it."""
        began, mark = self.clock(), len(self.knowledge.searches)
        failed = self.paced.spend.failures()
        failure: Failure | None = None
        acted: Acted | None = None
        with self._folder(name) as folder:
            mock = seeded_mock(folder, scenario)
            try:
                acted = await self._acted(scenario, mock)
            except TimeoutError:
                failure = "stuck"
            except ProviderError:
                failure = "provider"
            seeds = {ticket.id for ticket in seed_tickets(scenario)}
            made = [ticket for ticket in mock.listed() if ticket.id not in seeds]
            noted = sum(len(ticket.notes) for ticket in mock.listed())  # a seed holds none
        if self.paced.stopped is not None:
            raise StopRun(self.paced.stopped)
        searches = self.knowledge.searches[mark:]
        failure = failure or (acted.failure if acted is not None else None)
        if any(search.failed for search in searches) or self.paced.spend.failures() > failed:
            failure = failure or "provider"
        own = unasked(scenario, acted or _NOTHING, len(made), noted)
        if acted is None or failure is not None:
            return self._record(
                scenario, repeat, began, acted, own=own, failure=failure or "provider"
            )
        return await self._scored(scenario, repeat, began, acted, made, own, noted=noted)

    @contextlib.contextmanager
    def _folder(self, name: str) -> Iterator[Path]:
        if self.kept is not None:
            yield fresh_folder(self.kept, name)
            return
        with tempfile.TemporaryDirectory(prefix="ole5-run-a-", ignore_cleanup_errors=True) as held:
            yield Path(held) / name

    async def _acted(self, scenario: ActionScenario, mock: TicketSystem) -> Acted:
        agent = self.agent(PassageFirst(self.knowledge, scenario.passage), mock)
        try:
            return await act(
                agent,
                self.paced,
                self.settings,
                turns=scenario.turns,
                language=scenario.language,
                caller=CALLER,
                outbox=await seeded_outbox(scenario),
                call=self.call,
                limit_s=self.timeout_s,
                whole_s=self.timeout_s * len(scenario.turns),
            )
        except (CapReachedError, DailyLimitError) as error:
            raise StopRun(stop_of(error)) from None

    def _record(
        self,
        scenario: ActionScenario,
        repeat: int,
        began: float,
        acted: Acted | None,
        *,
        own: Sequence[str] = (),
        **fields: Any,
    ) -> ActionPlayRecord:
        """The play's record: the call as heard, its violations and `own`'s, `fields`, how long
        it took, and what the stray-script filter took out of what the talker wrote."""
        return ActionPlayRecord(
            scenario=scenario.id,
            kind=scenario.kind,
            repeat=repeat,
            rehearsal=scenario.rehearsal,
            turns=acted.turns if acted else (),
            found=acted.found if acted else (),
            violations=(*(acted.violations if acted else ()), *own),
            seconds=max(self.clock() - began, 0.0),
            stray_characters=acted.stray_characters if acted else 0,
            **fields,
        )

    async def _scored(
        self,
        scenario: ActionScenario,
        repeat: int,
        began: float,
        acted: Acted,
        made: Sequence[MockTicket],
        own: Sequence[str],
        *,
        noted: int,
    ) -> ActionPlayRecord:
        """The play checked (the module's docstring), `own` the scenario's own violations and
        `noted` the notes the call added; a `judge` failure when the judge gave no valid
        answer."""
        judged = await self._judged(scenario, acted)
        registered = [
            await self._register(turn.held_registers() != frozenset(), heard)
            for turn, heard in zip(scenario.turns, acted.turns, strict=True)
        ]
        mine = [ticket for ticket in made if ticket.customer_email == CUSTOMER]
        summary = await self._summary(scenario, mine)
        unclear = any(found is not None and found.arabic is None for found in registered)
        if unclear or any(c is not None and c.holds is None for c in (*judged, summary)):
            return self._record(scenario, repeat, began, acted, own=own, failure="judge")
        callers = [seed.number for seed in scenario.seed if seed.through_agent]
        numbers = (
            [ticket.number for ticket in mine],
            [*callers, *(ticket.number for ticket in mine)],
            [
                *(seed.number for seed in scenario.seed),
                *(ticket.number for ticket in made),
                *passage_numbers(scenario),
            ],
        )
        registers = [found.arabic if found else None for found in registered]
        checks = checks_of(
            scenario, acted, judged, registers, tool=self.search_tool, numbers=numbers
        )
        action_right = (
            len(mine) == scenario.made
            and len(made) == len(mine)
            and noted == scenario.noted
            and all(check.calls is not False for check in checks)
        )
        type_right = (
            None
            if scenario.ticket_type is None or not mine
            else all(ticket.type == scenario.ticket_type for ticket in mine)
        )
        holds = summary.holds or () if summary else ()
        verdicts = (action_right, type_right, all(holds))
        passed = all(check.passed for check in checks) and all(v is not False for v in verdicts)
        return self._record(
            scenario,
            repeat,
            began,
            acted,
            own=own,
            checks=checks,
            made=len(mine),
            others_made=len(made) - len(mine),
            noted=noted,
            made_types=tuple(ticket.type for ticket in mine),
            action_right=action_right,
            type_right=type_right,
            summary=mine[-1].summary if summary is not None else None,
            summary_judged=holds,
            summary_reasons=summary.reasons if summary else (),
            passed=passed and not own and not acted.violations,
        )

    async def _judged(self, scenario: ActionScenario, acted: Acted) -> list[Checked | None]:
        found: list[Checked | None] = []
        points = (scenario.passage,) if scenario.passage else ()
        for n, (turn, heard) in enumerate(zip(scenario.turns, acted.turns, strict=True)):
            if not turn.facts:
                found.append(None)
                continue
            before = [(t.says, h) for t, h in zip(scenario.turns[:n], acted.turns[:n], strict=True)]
            found.append(
                await self._checked(
                    before=before, asked=turn.says, turn=heard, facts=turn.facts, points=points
                )
            )
        return found

    async def _summary(
        self, scenario: ActionScenario, mine: Sequence[MockTicket]
    ) -> Checked | None:
        """The judge's checks of the last ticket the call made for the caller, its summary as
        the reply to the caller's words; None when there is none, or no fact to check."""
        if not mine or not scenario.summary_facts:
            return None
        written = Clause(
            text=mine[-1].summary, language=scenario.language, fate="played", played_fraction=1
        )
        return await self._checked(
            before=[],
            asked=" ".join(turn.says for turn in scenario.turns),
            turn=HeardTurn(fate="answered", clauses=(written,)),
            facts=scenario.summary_facts,
            points=(),
        )

    async def _checked(
        self,
        *,
        before: list[tuple[str, HeardTurn]],
        asked: str,
        turn: HeardTurn,
        facts: Sequence[str],
        points: Sequence[str],
    ) -> Checked:
        try:
            return await self.judge.checks(
                before=before, asked=asked, turn=turn, expectations=facts, points=points
            )
        except ProviderError:
            return Checked()
        except (CapReachedError, DailyLimitError) as error:
            raise StopRun(stop_of(error)) from None

    async def _register(self, asked: bool, reply: HeardTurn) -> Registered | None:
        """The judge's register of `reply`, when its turn holds it to Arabic (`asked`)."""
        if not asked:
            return None
        try:
            return await self.judge.register(reply)
        except ProviderError:
            return Registered()
        except (CapReachedError, DailyLimitError) as error:
            raise StopRun(stop_of(error)) from None
