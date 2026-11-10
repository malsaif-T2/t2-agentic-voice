"""What run A's tests share (test_action_*.py): the committed scenarios, an oracle talker that
does what each scenario's turn expects of it, on the library's `FunctionLLM`, a judge that
answers every check, a fake knowledge base, and the parts a run is built from, its call the real
`TextCall` on its virtual clock. Nothing is sent, and no stand-in replaces the session's
read-back, the yes rule, the guard or the action runner.

**The oracle** answers an overlap the interruption rule left uncertain with stop for words its
turn says cut the reply, go on otherwise. It finds the caller's words of each request among the
scenarios' turns: a turn whose scenario expects a ticket tool calls it, as a model writes a call
(`create_ticket` and `hand_off` with the caller's words as the summary and the scenario's type,
`ticket_status` with the digits the caller said); a turn expecting a search, or the first of a
scenario with a passage, searches; any other answers in its language, claiming nothing. A tool's
result is answered from it: a status by each ticket's last four digits, a search shortly.
`says` replaces the answer to the words given; `failing` makes the judge's checks of a request
holding the words given fail, and `unanswered` its answer to one no valid answer.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from ole5_voice.agent import talker_agent
from ole5_voice.evals.action_card import ActionRun
from ole5_voice.evals.action_run import ActionParts
from ole5_voice.evals.action_scenarios import ACTIONS_DIR, ActionScenario, load_action_scenarios
from ole5_voice.evals.factories import load_factory
from ole5_voice.evals.judge import REGISTER_SYSTEM
from ole5_voice.evals.run_parts import DATA
from ole5_voice.evals.talker_data import script_of
from pydantic import BaseModel
from t2_agentic_voice import VoiceAgent
from t2_agentic_voice.evals import (
    FakeKnowledgeBase,
    FunctionLLM,
    ScriptedLLM,
    ScriptStep,
    TextCall,
    uncertain_overlap_request,
)
from t2_agentic_voice.ports import (
    ChatEvent,
    ChatRequest,
    DataFlow,
    Done,
    Passage,
    TextDelta,
    Usage,
)

from tests.ole5_voice.evals.run_support import FakeClock, FakeGit, World
from tests.ole5_voice.evals.samples import WHEN

ROOT = Path(__file__).resolve().parents[3]
COMMITTED = ROOT / "apps" / "ole5-voice-agent" / "evals" / ACTIONS_DIR
TALKER: Final = "openai/gpt-oss-120b"
JUDGE: Final = "llama-3.3-70b-versatile"
SEARCH: Final = "search_knowledge"
AGENT: Final = "ole5_voice.agent:talker_agent"
KB: Final = "ole5_voice.fake:kb"
NO_TICKETS: Final = "ole5_voice.fake:no_tickets"  # Ole5's talker with no ticket tool
FLOW = DataFlow(provider="none", processed_in="the test", stored_in="nowhere", retention="none")
USAGE = Usage(input_tokens=100, output_tokens=20)
GUIDE = Passage(
    id="guide/chunk_001", title="A guide", text="Open the menu, then the item.", score=1
)
# What the oracle says, by the language of the call: words that claim nothing and hold no digit.
PLAIN: Final = {
    "en": "Okay. How else can I help you today?",
    "ar-SA": "طيب، وش تبي أساعدك فيه بعد؟",
    "ar": "حسنا، كيف يمكنني مساعدتك أيضا؟",
}
ANSWER: Final = {
    "en": "To do that, open the menu, choose the item you need, then confirm the step.",
    "ar-SA": "تقدر تسويها من القائمة، تختار اللي تبيه وبعدين تأكد الخطوة لما يطلبها منك.",
    "ar": "يمكنك ذلك من القائمة، اختر ما تحتاجه ثم أكد الخطوة عندما يطلب منك ذلك.",
}
_DIGITS = re.compile("[0-9]{4,16}")
# The instruction of the request a session sends on an overlap the rule left uncertain.
OVERLAP_SYSTEM: Final = uncertain_overlap_request("-", "-").messages[0].content
_DATA = re.compile(r'<data tool="[a-z_]+">')  # a tool's result, as the talker frames it


def said(text: str) -> list[ScriptStep]:
    """A model's answer that says `text`, its usage reported."""
    return [*ScriptedLLM.reply(text, usage=USAGE)]


def calls(name: str, **arguments: Any) -> list[ScriptStep]:
    """A model's answer that calls the tool `name` with `arguments`, its usage reported."""
    return [*ScriptedLLM.call_tools((name, arguments), usage=USAGE)]


def committed() -> tuple[ActionScenario, ...]:
    return load_action_scenarios(COMMITTED)


def made_up_run(split: str = "dev", repeats: int = 1) -> ActionRun:
    """A made-up run of A, for a scorecard built in a test."""
    return ActionRun(
        name="a-dev",
        started_at=WHEN,
        commit="ab" * 20,
        arm="a1",
        model=TALKER,
        judge_model=JUDGE,
        split=split,  # type: ignore[arg-type]
        settings={"llm.model": TALKER},
        prices={},
        cap_usd=1.5,
        estimate_usd=0.7,
        data_digest="cd" * 32,
        note="made up",
        repeats=repeats,
    )


class Oracle:
    """The talker's fake model's answers (the module's docstring)."""

    def __init__(self, scenarios: Sequence[ActionScenario]) -> None:
        self.turns = {
            turn.says: (scenario, n)
            for scenario in scenarios
            for n, turn in enumerate(scenario.turns)
        }
        self.says: dict[str, Sequence[ScriptStep]] = {}
        self.heard: list[str] = []

    def __call__(self, request: ChatRequest) -> list[ScriptStep]:
        if request.messages[0].content == OVERLAP_SYSTEM:
            return self._overlap(request.messages[-1].content)
        users = [m.content for m in request.messages if m.role == "user"]
        words = next((w for u in reversed(users) if (w := self._words(u)) is not None), None)
        asked = max(n for n, m in enumerate(request.messages) if m.role == "user")
        results = [m.content for m in request.messages[asked:] if _DATA.match(m.content)]
        if results:
            return said(self._from_result(results[-1], words))
        if words is None:
            return said(PLAIN["en" if script_of(users[-1]) == "en" else "ar-SA"])
        self.heard.append(words)
        if words in self.says:
            return list(self.says[words])
        scenario, n = self.turns[words]
        return self._to(scenario, n)

    def _overlap(self, asked: str) -> list[ScriptStep]:
        """The word on an overlap the rule left uncertain: stop for words a turn says cut the
        reply, go on for any other."""
        words = asked.rpartition("The caller said over it:\n")[2]
        found = self.turns.get(words)
        cuts = found is not None and found[0].turns[found[1]].cuts_reply
        return said("stop" if cuts else "go_on")

    def _words(self, message: str) -> str | None:
        """The caller's words a user message holds, a session's note after them, when they
        are a turn's or `says`'s; None otherwise."""
        known = [
            w for w in (*self.says, *self.turns) if message == w or message.startswith(f"{w} [")
        ]
        return max(known, key=len, default=None)

    def _to(self, scenario: ActionScenario, n: int) -> list[ScriptStep]:
        turn = scenario.turns[n]
        summary = " ".join(turn.says.split())[:200]
        if turn.calls == "create_ticket":
            kind = scenario.ticket_type or "Issue"
            return calls("create_ticket", summary=summary, type=kind, priority="Medium")
        if turn.calls == "hand_off":
            return calls("hand_off", summary=summary)
        if turn.calls == "ticket_status":
            found = _DIGITS.findall(turn.says)
            return calls("ticket_status", **({"number": found[-1]} if found else {}))
        if turn.search or (scenario.passage is not None and n == 0):
            return calls(SEARCH, query=turn.says)
        return said(PLAIN[turn.language or scenario.language])

    def _from_result(self, content: str, words: str | None) -> str:
        language = "en"
        if words is not None and words in self.turns:
            scenario, n = self.turns[words]
            language = scenario.turns[n].language or scenario.language
        body = content[content.index(">") + 1 : content.rindex("</data>")]
        data: Any = json.loads(body)
        if not isinstance(data.get("tickets"), list):
            return ANSWER[language]
        if language == "en":
            told = [f"Your ticket ending {t['ends_in']} is {t['status']}." for t in data["tickets"]]
        else:
            told = [
                f"تذكرتك اللي تنتهي بـ {t['ends_in']} حالتها {t['status']}."
                for t in data["tickets"]
            ]
        return " ".join(told) or PLAIN[language]


class OracleChat:
    """The run's chat model: the judge's requests answered here, every check holding but where
    `failing` names words its request holds, and a register question `msa` for Arabic (right
    for both Arabic tags); the talker's through the library's `FunctionLLM` on the oracle."""

    name = "oracle"
    data_flow = FLOW

    def __init__(self, oracle: Oracle) -> None:
        self.oracle = oracle
        self.talker = FunctionLLM(oracle)
        self.failing: set[str] = set()
        self.unanswered: set[str] = set()
        self.requests: list[ChatRequest] = []
        self.closed = False

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        self.requests.append(request)
        if request.model != JUDGE:
            async for event in self.talker.stream(request):
                yield event
            return
        asked = request.messages[-1].content
        if request.messages[0].content == REGISTER_SYSTEM:
            text = "msa" if script_of(asked) == "ar" else "none"
        elif any(words in asked for words in self.unanswered):
            text = "No answer."
        else:
            expectations = asked.split("The expectations:")[1].strip().splitlines()
            holds = not any(words in asked for words in self.failing)
            checks = [{"holds": holds, "reason": "Made up."}] * len(expectations)
            text = json.dumps({"checks": checks})
        for event in (TextDelta(text=text), USAGE, Done(finish_reason="stop")):
            yield event

    async def aclose(self) -> None:
        self.closed = True


def virtual(agent: VoiceAgent, **given: Any) -> TextCall:
    """The library's `TextCall` as run A builds it, on its virtual clock, so no time passes."""
    return TextCall(agent, **{**given, "clock": "virtual"})


class Lines:
    """Stands in for the shared history's appender: keeps each line and its path."""

    def __init__(self) -> None:
        self.lines: list[tuple[BaseModel, Path]] = []

    def __call__(self, line: BaseModel, path: Path) -> None:
        self.lines.append((line, path))


@dataclass
class ActionSetup:
    """A run's world, the committed scenarios in its data, and the fakes it is built from, to
    read back after `main`."""

    world: World
    oracle: Oracle = field(default_factory=lambda: Oracle(committed()))
    kb: FakeKnowledgeBase = field(default_factory=lambda: FakeKnowledgeBase([GUIDE]))
    clock: FakeClock = field(default_factory=FakeClock)
    lines: Lines = field(default_factory=Lines)
    accepts: bool = True
    held_out_run: bool = False
    call: Callable[..., Any] = virtual
    chat: OracleChat = field(init=False)

    def __post_init__(self) -> None:
        self.chat = OracleChat(self.oracle)

    def out(self, name: str = "a-dev") -> Path:
        return self.world.main / "ignored" / name

    def load(self, spec: str) -> Callable[..., object]:
        if spec == NO_TICKETS:
            return lambda kb, tickets: talker_agent(kb)
        return (lambda env_file: self.kb) if spec == KB else load_factory(spec)

    def parts(self) -> ActionParts:
        return ActionParts(
            folder=self.world.top,
            git=self.world.git,
            chat=lambda settings: self.chat,
            load_factory=self.load,
            append_line=self.lines,
            history_accepts=lambda line: self.accepts,
            requests_today=lambda path, day: Counter(),
            now=lambda: WHEN,
            clock=self.clock,
            sleep=self.clock.sleep,
            action_call=self.call,
            held_out_run=lambda path: self.held_out_run,
        )

    def argv(self, *extra: str, out: str = "a-dev", split: str = "dev") -> list[str]:
        found = ["--arm", "a1", "--split", split, "--max-output-tokens", "1024"]
        found += ["--timeout-s", "8", "--judge-model", JUDGE, "--judge-max-output-tokens", "300"]
        found += ["--price", f"{TALKER}=0.15/0.60", "--price", f"{JUDGE}=0.59/0.79"]
        for flag, n in (("--rpm", 30), ("--tpm", 100_000), ("--rpd", 10_000)):
            found += [flag, f"{TALKER}={n}", flag, f"{JUDGE}={n}"]
        found += ["--agent", AGENT, "--knowledge", KB, "--search-tool", SEARCH]
        found += ["--out", str(self.out(out))]
        return [*found, "--note", "a made-up run", *extra]


def make_action_setup(tmp_path: Path) -> ActionSetup:
    """A world whose data holds the committed scenarios; git ignores `main/ignored`, where the
    runs' folders go."""
    main = tmp_path / "main"
    top = main / ".claude" / "worktrees" / "run"
    (top / DATA).mkdir(parents=True)
    (tmp_path / "audio").mkdir()
    shutil.copytree(COMMITTED, top / DATA / ACTIONS_DIR)
    world = World(main, top, tmp_path / "audio", FakeGit(top, main, ignored=(main / "ignored",)))
    return ActionSetup(world)
