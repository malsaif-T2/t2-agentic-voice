"""What the tests of a talker with actions share (plan 007, Track B): the made-up request action of
the action runner's tests (tests/t2_agentic_voice/actions/action_support.py) declared beside
read tools, its runner on an in-memory outbox, a talker of the call given that runner, and a
stand-in for the guard's rule A (`check_claims` and `default_claims` are Track A's, built in
parallel): a plain substring match that keeps what each call was given, honouring Block 0's
signature."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import Tool
from t2_agentic_voice.agent.talker import ChatTalker, TalkerCall
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain import claims
from t2_agentic_voice.domain.claims import ActionEvidence, ClaimVerdict
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatModel
from t2_agentic_voice.domain.ports.outbox import OutboxEntry

from tests.t2_agentic_voice.actions.action_support import Backend, an_action
from tests.t2_agentic_voice.agent.chat_support import CALLER, ENGLISH, INSTRUCTIONS, MSA, SAUDI
from tests.t2_agentic_voice.fakes import FakeClock

CALL_ID = "call-1"
# The stand-in's phrases that claim any action, by language.
ANY_ACTION: Mapping[LanguageCode, tuple[str, ...]] = {
    "en": ("I have created",),
    "ar": ("تم إنشاء",),
}
_DIGITS = re.compile("[0-9]{3,}")


@dataclass
class FakeClaims:
    """Rule A's stand-in: a clause claims an action when it holds one of its phrases, or any
    action when it holds one of `any_action`; a claim passes only when the evidence holds the
    action (any action, for a phrase of any), and each run of three digits or more is in that
    evidence. It keeps each call's evidence and phrases (`seen`)."""

    seen: list[tuple[str, dict[str, tuple[str, ...]], tuple[str, ...], list[ActionEvidence]]] = (
        field(default_factory=list)
    )

    def check(
        self,
        clause: str,
        *,
        claims: Mapping[str, Sequence[str]],
        any_action: Sequence[str],
        evidence: Sequence[ActionEvidence],
        settings: GuardSettings,
        year: int,
    ) -> ClaimVerdict:
        assert isinstance(settings, GuardSettings) and year > 2000
        given = {name: tuple(phrases) for name, phrases in claims.items()}
        self.seen.append((clause, given, tuple(any_action), list(evidence)))
        text = clause.casefold()
        named = [n for n, phrases in given.items() if any(p.casefold() in text for p in phrases)]
        anyone = any(p.casefold() in text for p in any_action)
        if not named and not anyone:
            return ClaimVerdict(claimed=(), passed=True)
        held = {each.action: each.texts for each in evidence}
        claimed = tuple(named) or tuple(given)
        backed = [a for a in claimed if a in held] if named else list(held)
        if (named and len(backed) < len(named)) or not backed:
            return ClaimVerdict(claimed=claimed, passed=False)
        texts = " ".join(text for a in backed for text in held[a])
        unsupported = tuple(n for n in _DIGITS.findall(clause) if n not in texts)
        return ClaimVerdict(claimed=claimed, passed=not unsupported, unsupported=unsupported)


def fake_rule_a(monkeypatch: pytest.MonkeyPatch) -> FakeClaims:
    """Rule A's stand-in in place of Track A's `check_claims` and `default_claims`."""
    fake = FakeClaims()
    monkeypatch.setattr(claims, "check_claims", fake.check)
    monkeypatch.setattr(claims, "default_claims", lambda code: ANY_ACTION[code])
    return fake


@dataclass
class Acting:
    """A talker with actions and what it was built on: the backend, its action, the runner
    and its outbox, and the clock."""

    talker: ChatTalker
    backend: Backend
    action: Action
    runner: ActionRunner
    outbox: MemoryOutbox
    clock: FakeClock


def rows(outbox: MemoryOutbox) -> tuple[OutboxEntry, ...]:
    """Every row `outbox` holds, oldest first, read outside any reply."""
    return asyncio.run(outbox.entries())


def acting_agent(action: Action, *tools: Tool) -> VoiceAgent:
    """The tests' agent, in Saudi Arabic, MSA and English, with `tools` and `action`."""
    languages = [SAUDI, MSA, ENGLISH]
    tags = {language.tag for language in languages}
    instructions = {tag: text for tag, text in INSTRUCTIONS.items() if tag in tags}
    return VoiceAgent(
        name="helper", languages=languages, instructions=instructions, tools=[*tools, action]
    )


def acting(
    model: ChatModel,
    *tools: Tool,
    settings: VoiceSettings | None = None,
    outbox: MemoryOutbox | None = None,
    language: LanguageTag = "en",
    **changes: Any,
) -> Acting:
    """A call's talker of the tests' agent with `tools` and the made-up request action (its
    words changed by `changes`), its runner on an in-memory outbox, in `language`."""
    clock = FakeClock()
    store = outbox or MemoryOutbox()
    backend = Backend("answer", outbox=store, clock=clock)
    action = an_action(backend, **changes)
    runner = ActionRunner([action], outbox=store)
    talker = ChatTalker(
        acting_agent(action, *tools),
        model=model,
        runner=ToolRunner(tools),
        settings=settings or VoiceSettings(env="test"),
        call=TalkerCall(call_id=CALL_ID, caller=CALLER, language=language),
        clock=clock,
        actions=runner,
    )
    return Acting(talker, backend, action, runner, store, clock)
