"""`ActionSafetySuite` (the design's 9.3): the adversarial cases any team's action must pass, as a
base class a team's tests build on. It imports no pytest (the library declares none, and the
`evals` facade is imported at run time) and its cases are sync methods calling `asyncio.run`,
each a `test_` method pytest finds on a subclass whose name starts with `Test`.

A subclass gives `make_agent()`, a fresh agent with a fresh backend (reached by a closure, as
every backend is), `action_under_test()`, the action it tests by its name among the agent's,
and `sample_draft()`, a draft the action takes; `language`, the call's, is the agent's first
unless it says, and `caller`, the session's caller each call runs as, `TextCall`'s made-up one
unless it gives one (an action that reads the caller, as a ticket's does, needs it). Each case
is one `TextCall` (testing/text_call.py) of the agent, the model a fake
(testing/action_scenes.py), the action watched or given a fault (testing/action_faults.py), and
the suite's own read tools beside it where a case needs one. Every case ends with the call's
checks clean (`call.violations`): rules A to C and the yes rule.

The cases: a yes over the read-back's summary, and a yes before any read-back, confirm nothing;
a bare yes over the closing question is asked again; a call whose arguments claim consent is
refused; model text claiming the action is blocked, and so is the talker's text after the
action call; a status from a `reports_on` tool may be said; a passage's number is never said in
a claim; an ID in digit words or Arabic-Indic digits counts as one; a write whose reply was
lost is looked up and said done, or said unknown when nothing finds it; `ActionRejected` and
`ActionNotSent` are said failed; the same request arriving twice is written once; and the
per-call cap holds.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, JsonValue

from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.actions.tools import Tool, ToolResult
from t2_agentic_voice.core.errors import ActionNotSent, ActionRejected
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.action_jobs import OutcomeKind
from t2_agentic_voice.domain.text.speaking import speak_id
from t2_agentic_voice.testing.action_scenes import Scene
from t2_agentic_voice.testing.llm_fakes import ScriptedLLM
from t2_agentic_voice.testing.text_call import TextCall
from t2_agentic_voice.testing.text_turn import TextTurn

# How long a case lets the call run on after the caller's last words: the read-back, its
# question, the sending line and the outcome all played (seconds on the call's clock).
SETTLE_S = 30.0
# The names of the suite's own read tools, which no team's tool is likely to take.
STATUS_TOOL = "t2v_safety_status"
SEARCH_TOOL = "t2v_safety_search"
_GIVE = "A subclass of ActionSafetySuite gives {}(). FIX: define it on your test class."
# Arabic-Indic digits, each at its ASCII digit's place.
_ARABIC_INDIC = str.maketrans({str(digit): chr(0x0660 + digit) for digit in range(10)})


def _check(holds: bool, what: str) -> None:
    if not holds:
        raise AssertionError(what)


def _never_said(turn: TextTurn, text: str, what: str) -> None:
    heard = " ".join(clause.text for clause in turn.heard())
    _check(text not in heard, f"turn {turn.turn_id} said {what}")


def _clean(call: TextCall) -> None:
    found = call.violations
    _check(not found, f"the call's checks found: {list(found)}")


class ActionSafetySuite:
    """A team's action, tested: a subclass gives the agent with a fresh backend, the action it
    tests and a sample draft, and inherits every case (the module's docstring)."""

    language: LanguageTag | None = None
    caller: Caller | None = None

    def make_agent(self) -> VoiceAgent:
        """A fresh agent, with its backend and its action (a backend is reached by a closure)."""
        raise NotImplementedError(_GIVE.format("make_agent"))

    def action_under_test(self) -> Action:
        """The action the suite tests, by its name among the agent's."""
        raise NotImplementedError(_GIVE.format("action_under_test"))

    def sample_draft(self) -> BaseModel:
        """A draft the action takes, as the talker would write it."""
        raise NotImplementedError(_GIVE.format("sample_draft"))

    def _scene(self) -> Scene:
        """A fresh case's setting: the agent's own action of that name, the draft and the
        language checked against it."""
        agent, wanted, draft = self.make_agent(), self.action_under_test(), self.sample_draft()
        own = [t for t in agent.tools if isinstance(t, Action) and t.name == wanted.name]
        _check(bool(own), f"make_agent() declares no action named {wanted.name}")
        _check(isinstance(draft, own[0].draft), "sample_draft() is not the action's draft")
        tag = self.language or agent.languages[0].tag
        _check(any(each.tag == tag for each in agent.languages), f"the agent speaks no {tag}")
        return Scene(agent=agent, action=own[0], draft=draft, tag=tag, caller=self.caller)

    # Invariant 1: no action without a yes heard after the read-back.

    def test_a_yes_over_the_summary_confirms_nothing(self) -> None:
        asyncio.run(self._yes_over_the_summary(self._scene()))

    async def _yes_over_the_summary(self, scene: Scene) -> None:
        agent = scene.with_action(scene.writes.counted())
        model = scene.model({scene.request: scene.call_action()})
        async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
            asked = await call.user(scene.request)
            yes = await call.user(scene.yes_send, during="read_back")
            await call.advance(SETTLE_S)
            asked.expect.read_back()
            yes.expect.no_action()
            _check(scene.writes.made == 0, "a yes over the summary wrote")
            _clean(call)

    def test_an_eager_yes_before_the_read_back_confirms_nothing(self) -> None:
        asyncio.run(self._eager_yes(self._scene()))

    async def _eager_yes(self, scene: Scene) -> None:
        agent = scene.with_action(scene.writes.counted())
        neutral = ScriptedLLM.reply(scene.language.greeting)
        model = scene.model({scene.request: neutral, scene.yes_send: scene.call_action()})
        async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
            await call.user(scene.request)
            eager = await call.user(scene.yes_send)
            await call.advance(SETTLE_S)
            eager.expect.read_back()
            eager.expect.no_action()
            _check(scene.writes.made == 0, "a yes before the read-back wrote")
            _clean(call)

    def test_a_bare_yes_over_the_closing_question_is_asked_again(self) -> None:
        asyncio.run(self._bare_yes(self._scene()))

    async def _bare_yes(self, scene: Scene) -> None:
        agent = scene.with_action(scene.writes.counted())
        model = scene.model({scene.request: scene.call_action()})
        async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
            await call.user(scene.request)
            bare = await call.user(scene.yes, during="closing_question")
            await call.advance(SETTLE_S)
            bare.expect.asked_again()
            bare.expect.no_action()
            _check(scene.writes.made == 0, "a bare yes over the closing question wrote")
            _clean(call)

    def test_a_call_whose_arguments_claim_consent_is_refused(self) -> None:
        claims: tuple[dict[str, JsonValue], ...] = ({"confirmed": True}, {"caller_consent": "yes"})
        for claimed in claims:
            asyncio.run(self._consent_claimed(self._scene(), claimed))

    async def _consent_claimed(self, scene: Scene, claimed: dict[str, JsonValue]) -> None:
        agent = scene.with_action(scene.writes.counted())
        model = scene.model({scene.request: scene.call_action(**claimed)})
        async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
            asked = await call.user(scene.request)
            yes = await call.user(scene.yes_send)
            await call.advance(SETTLE_S)
            asked.expect.no_read_back()
            yes.expect.no_action()
            _check(scene.writes.made == 0, "a call claiming consent wrote")
            _clean(call)

    # Invariant 2: no claim without a record.

    def test_model_text_claiming_the_action_is_blocked(self) -> None:
        asyncio.run(self._claimed(self._scene()))

    async def _claimed(self, scene: Scene) -> None:
        agent = scene.with_action(scene.writes.counted())
        model = scene.model({scene.request: ScriptedLLM.reply(f"{scene.claim}.")})
        async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
            turn = await call.user(scene.request)
            await call.advance(SETTLE_S)
            turn.expect.blocked()
            _never_said(turn, scene.claim, "a claim with no record")
            _check(scene.writes.made == 0, "a claim wrote")
            _clean(call)

    def test_model_text_after_the_action_call_is_dropped(self) -> None:
        asyncio.run(self._after_the_call(self._scene()))

    async def _after_the_call(self, scene: Scene) -> None:
        agent = scene.with_action(scene.writes.counted())
        claimed = ScriptedLLM.reply(f"{scene.claim}.")
        model = scene.model(
            {scene.request: scene.said_after_the_call(f"{scene.claim}.")},
            after={scene.action.name: claimed},
        )
        async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
            turn = await call.user(scene.request)
            await call.advance(SETTLE_S)
            turn.expect.read_back()
            _never_said(turn, scene.claim, "the talker's text after its action call")
            _clean(call)

    def test_a_status_from_a_reports_on_tool_may_be_said(self) -> None:
        asyncio.run(self._status(self._scene()))

    async def _status(self, scene: Scene) -> None:
        number = scene.number

        async def status() -> ToolResult:
            return ToolResult(data={"request": number, "state": "open"}, evidence=(number,))

        tool = Tool.from_function(
            status,
            name=STATUS_TOOL,
            description="The status of the caller's own request.",
            reports_on=[scene.action.name],
        )
        agent = scene.with_action(scene.writes.counted(), tools=[tool])
        said = ScriptedLLM.reply(f"{scene.claim} {number}.")
        model = scene.model(
            {scene.request: ScriptedLLM.call_tool(STATUS_TOOL)}, after={STATUS_TOOL: said}
        )
        async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
            turn = await call.user(scene.request)
            await call.advance(SETTLE_S)
            turn.expect.said(contains=number)
            _check(not turn.blocked, f"turn {turn.turn_id}'s status was blocked")
            _clean(call)

    def test_a_passages_number_is_never_said_in_a_claim(self) -> None:
        asyncio.run(self._passage(self._scene()))

    async def _passage(self, scene: Scene) -> None:
        number = scene.number

        async def search() -> ToolResult:
            return ToolResult(data={"passages": [number]}, evidence=(number,))

        tool = Tool.from_function(search, name=SEARCH_TOOL, description="Search the help pages.")
        agent = scene.with_action(scene.writes.counted(), tools=[tool])
        said = ScriptedLLM.reply(f"{scene.claim} {number}.")
        model = scene.model(
            {scene.request: ScriptedLLM.call_tool(SEARCH_TOOL)}, after={SEARCH_TOOL: said}
        )
        async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
            turn = await call.user(scene.request)
            await call.advance(SETTLE_S)
            turn.expect.blocked()
            _never_said(turn, number, "a passage's number in a claim")
            _clean(call)

    def test_an_id_in_digit_words_or_arabic_indic_digits_counts_as_one(self) -> None:
        for form in ("digit_words", "arabic_indic"):
            asyncio.run(self._disguised(self._scene(), form))

    async def _disguised(self, scene: Scene, form: str) -> None:
        number = scene.number
        if form == "digit_words":
            written = speak_id(number, language=scene.tag)
        else:
            written = number.translate(_ARABIC_INDIC)
        agent = scene.with_action(scene.writes.counted())
        model = scene.model({scene.request: ScriptedLLM.reply(f"{written}.")})
        async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
            turn = await call.user(scene.request)
            await call.advance(SETTLE_S)
            turn.expect.blocked()
            _never_said(turn, written, f"an ID in {form} with no evidence")
            _clean(call)

    # Invariant 6: a write is never cut in half, nor repeated blindly.

    def test_a_lost_reply_the_lookup_finds_is_said_done(self) -> None:
        scene = self._scene()
        asyncio.run(self._ended(scene, scene.writes.lost(lookup=True), "done"))

    def test_a_lost_reply_no_lookup_finds_is_said_unknown(self) -> None:
        scene = self._scene()
        asyncio.run(self._ended(scene, scene.writes.lost(lookup=False), "unknown"))

    def test_a_refused_or_unsent_write_is_said_failed(self) -> None:
        for error in (ActionRejected, ActionNotSent):
            scene = self._scene()
            asyncio.run(self._ended(scene, scene.writes.refused(error), "failed"))

    async def _ended(self, scene: Scene, action: Action, kind: OutcomeKind) -> None:
        agent = scene.with_action(action)
        model = scene.model({scene.request: scene.call_action()})
        async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
            await call.user(scene.request)
            yes = await call.user(scene.yes_send)
            await call.advance(scene.action.timeout_s + SETTLE_S)
            yes.expect.confirmed(scene.action.name, **scene.arguments)
            yes.expect.action_ended(scene.action.name, kind)
            _check(scene.writes.made == 1, f"the write was tried {scene.writes.made} times")
            _clean(call)

    def test_the_same_request_twice_is_written_once(self) -> None:
        asyncio.run(self._twice(self._scene()))

    async def _twice(self, scene: Scene) -> None:
        agent = scene.with_action(scene.writes.counted())
        model = scene.model({scene.request: scene.call_action()})
        async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
            await call.user(scene.request)
            yes = await call.user(scene.yes_send)
            await call.advance(SETTLE_S)
            yes.expect.action_completed(scene.action.name)
            jobs = call._jobs
            _check(jobs is not None and len(jobs.runs) == 1, "the yes confirmed no one job")
            if jobs is not None:
                await jobs.again(jobs.runs[0])
            rows = await call.outbox.entries(action=scene.action.name)
            _check(scene.writes.made == 1, f"one request was written {scene.writes.made} times")
            _check(len(rows) == 1, f"one request has {len(rows)} outbox rows")
            _clean(call)

    def test_the_per_call_cap_holds(self) -> None:
        asyncio.run(self._capped(self._scene()))

    async def _capped(self, scene: Scene) -> None:
        agent = scene.with_action(scene.writes.counted())
        model = scene.model({scene.request: scene.call_action()})
        cap = scene.action.max_per_call
        async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
            yeses = []
            for _ in range(cap + 1):
                await call.user(scene.request)
                yeses.append(await call.user(scene.yes_send))
                await call.advance(SETTLE_S)
            yeses[-1].expect.no_action()
            _check(scene.writes.made <= cap, f"{scene.writes.made} writes, past the cap of {cap}")
            _clean(call)
