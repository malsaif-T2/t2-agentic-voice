"""`TextCall` (the design's 9.2; plan 006): a call held in text, for a team's tests and the
library's. It runs the real voice session (voice/session/), the real talker, tools and output
guard, with no audio: each of the caller's turns is typed text standing in for heard words, the
agent's speech is a fake text-to-speech whose clauses play at `chars_per_second`, and time is a
virtual clock that moves only when the test says (`advance`). It needs no key and no network,
never starts Pipecat, and is deterministic; it always runs with `env="test"`, the only place
typed text stands in for heard words. It is not a chat channel. The model is the test's
(`ScriptedLLM`, `FunctionLLM`: testing/llm_fakes.py, or a real one through its port for a
measurement), and so is every tool's backend (`FakeKnowledgeBase` for the knowledge tool).

**Injections:** `call.user(text)`, a turn said while the agent is silent; `call.user(text,
during="agent_speaking")`, said over the reply playing; `call.user(text, at="tool_running")`,
said while a tool of the reply runs; `call.advance(seconds)`; `call.stop()`, the client's Stop.

**Expectations**, on each turn's `expect`: `tool_call(name, **args)`, `said(contains=)`,
`blocked()`, `cancelled(tool)` and `language(tag)`, each raising AssertionError with what the
turn did instead. `call.violations` holds the output guard's checks, run on every call.

Plan 006's Track C builds it, with the parity test against `AudioCall`; this module holds its
shapes.
"""

from __future__ import annotations

from types import TracebackType
from typing import Literal

from pydantic import JsonValue

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatModel

# When a turn is said: over the reply playing.
During = Literal["agent_speaking"]
# Where in a reply a turn is said: while one of its tools runs.
At = Literal["tool_running"]
# The pace the fake text-to-speech plays each clause at: about 15 characters a second, a calm
# speaking rate.
CHARS_PER_SECOND = 15.0


class TurnExpectations:
    """What one turn of a `TextCall` is expected to have done; each check raises AssertionError
    saying what the turn did instead."""

    def tool_call(self, name: str, **args: JsonValue) -> None:
        """The talker called the tool `name`, with `args` among its arguments."""
        raise NotImplementedError("TextCall is plan 006's Track C")

    def said(self, *, contains: str) -> None:
        """The reply the caller heard holds `contains`."""
        raise NotImplementedError("TextCall is plan 006's Track C")

    def blocked(self) -> None:
        """The output guard blocked a clause of the reply."""
        raise NotImplementedError("TextCall is plan 006's Track C")

    def cancelled(self, tool: str) -> None:
        """The tool `tool` was cancelled, by the turn's words or a stop."""
        raise NotImplementedError("TextCall is plan 006's Track C")

    def language(self, tag: LanguageTag) -> None:
        """The reply was in the language `tag`."""
        raise NotImplementedError("TextCall is plan 006's Track C")


class TextTurn:
    """One of the caller's turns in a `TextCall`, and what came of it (`expect`)."""

    @property
    def expect(self) -> TurnExpectations:
        """The checks of what the turn did."""
        raise NotImplementedError("TextCall is plan 006's Track C")


class TextCall:
    """A call of `agent` held in text (the module's docstring), its talker on `llm`, with
    `settings` (`env` test, the library's defaults, unless given), its caller `caller` (a made-up
    one unless given) in `language` (the agent's first unless given). Enter it (`async with`)
    to connect the call, greeted; leaving it hangs up."""

    def __init__(
        self,
        agent: VoiceAgent,
        *,
        llm: ChatModel,
        settings: VoiceSettings | None = None,
        caller: Caller | None = None,
        language: LanguageTag | None = None,
        chars_per_second: float = CHARS_PER_SECOND,
    ) -> None:
        self.agent, self.llm, self.settings = agent, llm, settings
        self.caller, self.language, self.chars_per_second = caller, language, chars_per_second

    async def __aenter__(self) -> TextCall:
        raise NotImplementedError("TextCall is plan 006's Track C")

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        raise NotImplementedError("TextCall is plan 006's Track C")

    async def user(
        self, text: str, *, during: During | None = None, at: At | None = None
    ) -> TextTurn:
        """The caller says `text`: while the agent is silent, or `during` its reply, or `at` a
        point of it; returns once the turn is answered, or once its reply is stopped."""
        raise NotImplementedError("TextCall is plan 006's Track C")

    async def advance(self, seconds: float) -> None:
        """Move the call's virtual clock `seconds` on, what is due by then done."""
        raise NotImplementedError("TextCall is plan 006's Track C")

    async def stop(self) -> None:
        """The client's Stop: the agent's speech stops at once, and the reply's work with it."""
        raise NotImplementedError("TextCall is plan 006's Track C")

    @property
    def violations(self) -> tuple[str, ...]:
        """What the output guard's checks found in the call so far, each said in words."""
        raise NotImplementedError("TextCall is plan 006's Track C")
