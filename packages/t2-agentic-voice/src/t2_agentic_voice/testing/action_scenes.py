"""What one case of `ActionSafetySuite` is set up with (testing/action_safety.py; the design's
9.3): a `Scene`, the team's agent with its action under test watched or faulted
(testing/action_faults.py) and the suite's own tools beside it, the call's language, and what
the caller says and the fake model answers, in that language.

**The caller's lines.** The request is the sample draft's text values, so every value of the
draft is the caller's own words; a yes is the language preset's first yes word, with a send word
(the action's own first, else the preset's) where one is wanted. They are said as text, as a
`TextCall` takes them, and read by the yes rule as they would be heard.

**The model** is a `FunctionLLM`: each request answered by the newest thing in it, the caller's
line it holds (`turns`, by the line) or a tool's result (`after`, by the tool's name), and with
a neutral line, the language's greeting, for anything else, so a case never depends on how
many requests the talker makes. The yes rule's check of an answer its lists leave unplaced
(domain/consent_check.py, D-082), told by its instruction, is answered by `judged`, and by the
neutral line, which reads as unclear, when a case gives none.

What every case ends with is here too (`check`, `clean`, `SETTLE_S`), shared by the suite's two
modules (testing/action_safety.py, testing/action_judged.py).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, JsonValue

from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.actions.tools import Tool
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import LanguageCode, primary_code
from t2_agentic_voice.domain.consent_check import is_consent_check
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatRequest, Done
from t2_agentic_voice.domain.yes_words import consent_words
from t2_agentic_voice.testing.action_faults import Writes
from t2_agentic_voice.testing.llm_fakes import FunctionLLM, ScriptedLLM, ScriptStep
from t2_agentic_voice.testing.text_call import TextCall

# How long a case lets the call run on after the caller's last words: the read-back, its
# question, the sending line and the outcome all played (seconds on the call's clock).
SETTLE_S = 30.0
# Numbers a case may say that nothing in the call holds: the first that the draft does not hold
# is the case's (`Scene.number`).
_NUMBERS = ("48213", "73905", "61847", "95130")


def check(holds: bool, what: str) -> None:
    """AssertionError saying `what` unless it `holds`."""
    if not holds:
        raise AssertionError(what)


def clean(call: TextCall) -> None:
    """The call's checks found nothing (`call.violations`)."""
    found = call.violations
    check(not found, f"the call's checks found: {list(found)}")


@dataclass(kw_only=True)
class Scene:
    """One case's call (the module's docstring): the team's `agent`, its `action` as declared,
    the sample `draft`, the call's `tag`, its `caller` (None for `TextCall`'s made-up one), and
    the `writes` of the action, watched."""

    agent: VoiceAgent
    action: Action
    draft: BaseModel
    tag: LanguageTag
    caller: Caller | None = None
    writes: Writes = field(init=False)

    def __post_init__(self) -> None:
        self.writes = Writes(self.action)

    @property
    def code(self) -> LanguageCode:
        return primary_code(self.tag)

    @property
    def asks(self) -> bool:
        """Whether the agent has a chat model judge the answers its lists leave unplaced."""
        return self.agent.ask_on_unlisted_answers

    @property
    def language(self) -> Language:
        return next(each for each in self.agent.languages if each.tag == self.tag)

    def with_action(self, action: Action, *, tools: Iterable[Tool] = ()) -> VoiceAgent:
        """The agent with `action` in its action's place, and `tools` after its own."""
        kept = [action if each.name == action.name else each for each in self.agent.tools]
        return self.agent.model_copy(update={"tools": (*kept, *tools)})

    @property
    def arguments(self) -> dict[str, JsonValue]:
        """The draft as the talker writes it, JSON values."""
        dumped: dict[str, JsonValue] = self.draft.model_dump(mode="json")
        return dumped

    @property
    def request(self) -> str:
        """The caller's request: the draft's text values, or the action's name."""
        texts = [value for value in self.arguments.values() if isinstance(value, str)]
        return " ".join(texts) or self.action.name.replace("_", " ")

    @property
    def yes(self) -> str:
        """A bare yes, in the call's language."""
        return consent_words(self.code).yes[0]

    @property
    def yes_send(self) -> str:
        """A yes with a send word, in the call's language."""
        own = self.action.read_back.send_words.get(self.code, ())
        send = own[0] if own else consent_words(self.code, action_send=own).send[0]
        return f"{self.yes} {send}"

    @property
    def claim(self) -> str:
        """A phrase that claims the action, its first in the call's language."""
        return self.action.claims.for_language(self.tag)[0]

    @property
    def number(self) -> str:
        """A number of five digits nothing in the call holds."""
        held = json.dumps(self.arguments, ensure_ascii=False)
        return next(number for number in _NUMBERS if number not in held)

    def call_action(self, **extra: JsonValue) -> tuple[ScriptStep, ...]:
        """The model's call of the action with the draft, and `extra` arguments beside it."""
        return ScriptedLLM.call_tool(self.action.name, **{**self.arguments, **extra})

    def said_after_the_call(self, text: str) -> tuple[ScriptStep, ...]:
        """The model's call of the action, then `text` in the same answer."""
        called = [step for step in self.call_action() if not isinstance(step, Done)]
        return (*called, *ScriptedLLM.reply(f" {text}")[:-1])

    def model(
        self,
        turns: Mapping[str, Sequence[ScriptStep]],
        after: Mapping[str, Sequence[ScriptStep]] | None = None,
        *,
        judged: Sequence[ScriptStep] | None = None,
    ) -> FunctionLLM:
        """The fake model of the case (the module's docstring)."""
        neutral = ScriptedLLM.reply(self.language.greeting)
        answered_after = dict(after or {})

        def answer(request: ChatRequest) -> Sequence[ScriptStep]:
            if is_consent_check(request):
                return neutral if judged is None else judged
            said = [m for m in request.messages if m.role in ("user", "tool")]
            if not said:
                return neutral
            newest = said[-1]
            if newest.role == "tool":
                calls = [c for m in request.messages for c in m.tool_calls]
                tool = next((c.name for c in calls if c.id == newest.tool_call_id), "")
                return answered_after.get(tool, neutral)
            return next((steps for line, steps in turns.items() if line in newest.content), neutral)

        return FunctionLLM(answer)
