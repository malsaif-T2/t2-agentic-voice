"""The playing part of a `poe eval-scenarios` run (`scenario_run.py`): one play of a scenario as
one call through `talker_call.play`, within `--variant-timeout-s` for each of its turns, then
checked turn by turn (`scenario_score.checks_of`), the judge reading each turn that expects facts
or what it follows, with the call so far as the caller heard it, and asked the register of each
reply held to Arabic in a question of its own (judge.py's `Judge.register`). A provider's
failure, in the call, its searches or a model request the talker caught, makes the play a
`provider` failure, its limit passed (or a moment the call waited for in vain) a `stuck` one, and
a judge with no valid answer, or no clear register, a `judge` one. When the cap or the key's
daily limit stops a request (`chat_pacing`), the play is dropped unscored (`StopRun`), so a
resumed run plays it again.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass

from t2_agentic_voice import ProviderError, VoiceAgent, VoiceSettings

from ole5_voice.evals.chat_pacing import CapReachedError, DailyLimitError, PacedChat
from ole5_voice.evals.groq_answerer import Clock
from ole5_voice.evals.judge import Checked, Judge, Registered
from ole5_voice.evals.kb_points import KnowledgeData, RecordingKnowledge
from ole5_voice.evals.knowledge_set import KnowledgeItem
from ole5_voice.evals.scenario_score import PlayRecord, TurnCheck, checks_of
from ole5_voice.evals.scenarios import Scenario, ScriptTurn
from ole5_voice.evals.talker_call import CallFactory, Held, play
from ole5_voice.evals.talker_data import Failure, HeardTurn
from ole5_voice.evals.talker_measure import StopRun, stop_of


@dataclass
class Playing:
    """One run's playing: the agent, the call's settings, the paced model, the recorded
    knowledge base, the data, the judge, and the knowledge tool's name."""

    agent: VoiceAgent
    paced: PacedChat
    settings: VoiceSettings
    knowledge: RecordingKnowledge
    data: KnowledgeData
    judge: Judge
    search_tool: str
    timeout_s: float
    call: CallFactory
    clock: Clock

    async def play(self, scenario: Scenario, repeat: int) -> PlayRecord:
        """One play of `scenario`, checked; StopRun when the cap or the day's limit stopped
        it."""
        began, mark = self.clock(), len(self.knowledge.searches)
        failed = self.paced.spend.failures()
        failure: Failure | None = None
        held: Held | None = None
        try:
            limit = self.timeout_s * len(scenario.turns)
            held = await asyncio.wait_for(self._played(scenario), limit)
        except TimeoutError:
            failure = "stuck"
        except ProviderError:
            failure = "provider"
        if self.paced.stopped is not None:
            raise StopRun(self.paced.stopped)
        searches = self.knowledge.searches[mark:]
        if any(search.failed for search in searches) or self.paced.spend.failures() > failed:
            failure = failure or "provider"
        if held is None or failure is not None:
            return self._record(scenario, repeat, began, held=held, failure=failure or "provider")
        judged = await self._judged(scenario, held)
        pairs = zip(scenario.turns, held.turns, strict=True)
        registered = [await self._register(turn, reply) for turn, reply in pairs]
        unclear = any(found is not None and found.arabic is None for found in registered)
        if unclear or any(checked is not None and checked.holds is None for checked in judged):
            return self._record(scenario, repeat, began, held=held, failure="judge")
        registers = [found.arabic if found else None for found in registered]
        checks = checks_of(scenario.turns, held.turns, judged, self.search_tool, registers)
        passed = all(check.passed for check in checks) and held.violations == 0
        return self._record(scenario, repeat, began, held=held, checks=checks, passed=passed)

    def _record(
        self,
        scenario: Scenario,
        repeat: int,
        began: float,
        *,
        held: Held | None = None,
        checks: tuple[TurnCheck, ...] = (),
        passed: bool | None = None,
        failure: Failure | None = None,
    ) -> PlayRecord:
        return PlayRecord(
            scenario=scenario.id,
            repeat=repeat,
            rehearsal=scenario.rehearsal,
            turns=held.turns if held else (),
            checks=checks,
            violations=held.violations if held else 0,
            passed=passed,
            failure=failure,
            seconds=max(self.clock() - began, 0.0),
        )

    async def _played(self, scenario: Scenario) -> Held:
        try:
            return await play(
                self.agent,
                self.paced,
                self.settings,
                turns=scenario.turns,
                language=scenario.language,
                call=self.call,
                limit_s=self.timeout_s,
            )
        except (CapReachedError, DailyLimitError) as error:
            raise StopRun(stop_of(error)) from None

    async def _judged(self, scenario: Scenario, held: Held) -> list[Checked | None]:
        items: Mapping[str, KnowledgeItem] = self.data.items
        found: list[Checked | None] = []
        for n, (turn, reply) in enumerate(zip(scenario.turns, held.turns, strict=True)):
            expectations = turn.expectations(items)
            if not expectations:
                found.append(None)
                continue
            points = self.data.evidence(items[turn.item]).points if turn.item else ()
            before = [(t.says, h) for t, h in zip(scenario.turns[:n], held.turns[:n], strict=True)]
            try:
                checked = await self.judge.checks(
                    before=before,
                    asked=turn.says,
                    turn=reply,
                    expectations=expectations,
                    points=points,
                )
            except ProviderError:
                checked = Checked()
            except (CapReachedError, DailyLimitError) as error:
                raise StopRun(stop_of(error)) from None
            found.append(checked)
        return found

    async def _register(self, turn: ScriptTurn, reply: HeardTurn) -> Registered | None:
        """The judge's register of `reply`, when `turn` holds it to Arabic; None otherwise."""
        if turn.held_register() is None:
            return None
        try:
            return await self.judge.register(reply)
        except ProviderError:
            return Registered()
        except (CapReachedError, DailyLimitError) as error:
            raise StopRun(stop_of(error)) from None
