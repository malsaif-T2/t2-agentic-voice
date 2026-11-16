"""`TextCall`'s injections as run S plays them (talker_call.py's `play`), with the library's real
`TextCall` on the system clock, Ole5's own talker and a fake chat model and knowledge base:
a turn said `during="agent_speaking"` lands over the reply playing, the call having gone on the
scenario's `after_s` first, and cuts it (the rehearsal's step 1, `s01`); a turn said
`at="tool_running"` lands while the earlier turn's search runs, which its words then stop, and
the talker answers it (the rehearsal's step 5, `s05`). Real time passes: each test takes a few
seconds."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from typing import Any, ClassVar

from ole5_voice.agent import talker_agent
from ole5_voice.evals.items import EVALS
from ole5_voice.evals.scenario_score import TurnCheck, checks_of
from ole5_voice.evals.scenarios import SCENARIOS_DIR, load_scenarios
from ole5_voice.evals.talker_call import Held, play
from t2_agentic_voice import Caller, LlmSettings, VoiceSettings
from t2_agentic_voice.evals import FunctionLLM, ScriptedLLM, ScriptStep, TextCall, TextTurn
from t2_agentic_voice.ports import ChatRequest, Passage

SETTINGS = VoiceSettings(env="test", llm=LlmSettings(model="openai/gpt-oss-120b"))
SCENARIOS = {s.id: s for s in load_scenarios(EVALS / SCENARIOS_DIR)}
LONG = "خطوات الاستعادة تبدأ من صفحة الدخول ثم تضغط نسيت كلمة المرور وتكتب بريدك ثم تفتح الرسالة."


class SlowKnowledgeBase:
    """A knowledge base whose search takes `seconds` on the wall clock."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.searches: list[str] = []

    async def search(
        self, query: str, *, language: str, caller: Caller, limit: int
    ) -> list[Passage]:
        self.searches.append(query)
        await asyncio.sleep(self.seconds)
        return [Passage(id="doc/chunk_001", title="A title", text="Made-up steps.", score=0.5)]


class Timed(TextCall):
    """The real `TextCall`, each injection and wait kept with when it came on the wall clock."""

    log: ClassVar[list[tuple[str, float]]] = []

    async def user(self, text: str, *, during: Any = None, at: Any = None) -> TextTurn:
        Timed.log.append((f"user {during or at or 'silent'}", time.perf_counter()))
        found = await super().user(text, during=during, at=at)
        Timed.log.append(("returned", time.perf_counter()))
        return found

    async def advance(self, seconds: float) -> None:
        Timed.log.append((f"advance {seconds:g}", time.perf_counter()))
        await super().advance(seconds)


def _answers(searched: set[str], *replies: str) -> FunctionLLM:
    """A model that searches first for a turn whose words hold one of `searched`, then answers
    each turn with the next of `replies`."""
    told = iter(replies)

    def fn(request: ChatRequest) -> Iterable[ScriptStep]:
        last = request.messages[-1]
        if last.role == "user" and request.tools and any(w in last.content for w in searched):
            return ScriptedLLM.call_tool("search_knowledge", query="the caller's question")
        return ScriptedLLM.reply(next(told, "تمام."))

    return FunctionLLM(fn)


def _play(scenario: str, kb: SlowKnowledgeBase, llm: FunctionLLM) -> Held:
    Timed.log = []
    turns = SCENARIOS[scenario].turns
    return asyncio.run(
        asyncio.wait_for(
            play(talker_agent(kb), llm, SETTINGS, turns=turns, language="ar-SA", call=Timed),
            timeout=60,
        )
    )


def _at(kind: str, nth: int = 0) -> float:
    return [at for name, at in Timed.log if name == kind][nth]


def _checked(scenario: str, held: Held) -> list[TurnCheck]:
    """The scenario's own checks of what the call did, the judge's aside."""
    turns = SCENARIOS[scenario].turns
    return list(checks_of(turns, held.turns, [None] * len(turns), "search_knowledge"))


def test_a_stop_said_over_the_reply_lands_after_the_scenarios_wait_and_cuts_it() -> None:
    """`s01`: the call goes on `after_s` (1 s) once the reply is written, then the stop word is
    said over it, at TextCall's own pace: it cuts the reply in its first clause, and the stop
    says nothing back."""
    kb = SlowKnowledgeBase(0.05)
    llm = _answers({"نسيت"}, LONG, "وبعدها.")
    held = _play("s01_password_stop_go_on", kb, llm)
    first, stop, go_on = held.turns
    # The 1 s wait is read on two clock readings; a millisecond's room keeps the clock's own
    # precision from failing it (D-090: 0.9999359 s once, under a full gate's load).
    waited = _at("user agent_speaking") - _at("advance 1")
    assert _at("advance 1") >= _at("returned") and waited >= 1.0 - 1e-3
    # Cut in its first clause (`rolled_back`, which the scenario's cut check takes as `cut`);
    # TextCall taps no audio, so the share heard of a cut clause reads 0 (the report's note).
    (cut,) = [clause for clause in first.clauses if not clause.phrase]
    assert cut.fate == "cut" and first.fate in ("cut", "rolled_back")
    assert stop.fate == "command" and go_on.fate == "answered" and go_on.said
    checks = _checked("s01_password_stop_go_on", held)
    assert checks[0].search and checks[1].cut and checks[1].search and checks[1].words
    assert checks[2].search  # the go-on searched nothing


def test_a_correction_said_while_the_search_runs_lands_in_it_and_is_answered() -> None:
    """`s05`: the correction is said once the first turn's search runs; its words take longer
    to say than the search, so the first reply begins and the correction's words cut it, and
    the talker searches again and answers it (scenarios.py's note on `cuts_reply`)."""
    kb = SlowKnowledgeBase(1.5)
    words = {"أصور", "أصدّر"}  # asawwir, asaddir
    held = _play("s05_correction", kb, _answers(words, LONG, "تقدر."))
    first, correction = held.turns
    assert _at("user tool_running") < _at("returned")  # said before the first turn returned
    assert first.fate in ("cut", "rolled_back") and len(kb.searches) == 2
    assert correction.fate == "answered" and correction.said
    checks = _checked("s05_correction", held)
    assert checks[0].search and checks[1].search is None and checks[1].language  # Q29: unchecked
