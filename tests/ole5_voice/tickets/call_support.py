"""What the end-to-end tests of Ole5's ticket calls share (test_ticket_calls.py; plan 007): Ole5's
served talker on the mock ticket system in a test's folder, its knowledge base a fake one, under
the settings the server gives it; the caller the demo customer, as the token route mints every
caller; the caller's yes, send, stop, pause and repeat words, taken from the library's lists and
Ole5's lines; a fake model that answers each request by the turn it answers and the newest tool
result, and the yes rule's check of an answer its lists leave unplaced (D-082) by the caller's
words; and what the call said, what the guard blocked, what the model was given and asked, and
what the yes rule read a turn as."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from ole5_voice.agent import talker_agent
from ole5_voice.customer import CUSTOMER_EMAIL
from ole5_voice.settings import DEMO_CUSTOMER_EMAIL
from ole5_voice.tickets.lines import SEND_WORDS
from ole5_voice.tickets.mock import MockTicketSystem
from ole5_voice.tickets.tools import with_ticket_claims
from ole5_voice.token_route import SUBJECT
from t2_agentic_voice import Caller, VoiceAgent, VoiceSettings
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.uncertain_overlaps import UNCERTAIN_OVERLAP_INSTRUCTION
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.domain.yes_words import PRESET_CONSENT
from t2_agentic_voice.evals import (
    FakeKnowledgeBase,
    FunctionLLM,
    ScriptedLLM,
    ScriptStep,
    TextCall,
    is_consent_check,
)
from t2_agentic_voice.events import ConfirmationAnswered, GuardBlocked
from t2_agentic_voice.ports import ChatRequest, Outbox, Passage

from tests.ole5_voice.tickets.ticket_support import Clock

# The two languages Ole5 speaks (agent.py).
Tag = Literal["ar-SA", "en"]
# The demo customer, as the token route mints every caller (token_route.py, customer.py).
CALLER: Final = Caller(subject=SUBJECT, attributes={CUSTOMER_EMAIL: DEMO_CUSTOMER_EMAIL})
# A text call's settings: the library's, its guard reading Ole5's phrases for a ticket's number
# as claims, as the server's talker runs (server.py).
SETTINGS: Final = with_ticket_claims(VoiceSettings(env="test"))
# How long a call runs on after the caller's yes: the sending line, the write and the outcome.
SETTLE_S: Final = 30.0
# What the uncertain overlap's request says before the caller's words over the reply.
_OVER: Final = "The caller said over it:"


def code(tag: Tag) -> LanguageCode:
    return "en" if tag == "en" else "ar"


def yes(tag: Tag) -> str:
    """A bare yes: the language preset's first yes word."""
    return PRESET_CONSENT[code(tag)].yes[0]


def yes_send(tag: Tag) -> str:
    """A yes with the send word Ole5's closing question holds («نعم أرسلها», "yes send it")."""
    return f"{yes(tag)} {SEND_WORDS[code(tag)][0]}"


def stop_word(tag: Tag) -> str:
    """The language preset's first stop word."""
    return PRESET_WORDS[code(tag)].stop[0]


def wait_word(tag: Tag) -> str:
    """The language preset's first word asking the agent to pause."""
    return PRESET_WORDS[code(tag)].wait[0]


def repeat_word(tag: Tag) -> str:
    """The language preset's first repeat word."""
    return PRESET_WORDS[code(tag)].repeat[0]


def ole5(folder: Path, passages: Sequence[Passage] = ()) -> tuple[VoiceAgent, MockTicketSystem]:
    """Ole5's served talker (agent.py's `talker_agent`) acting on a mock kept in `folder`, on a
    clock the test holds, its knowledge base a fake one holding `passages`."""
    tickets = MockTicketSystem(folder, clock=Clock())
    return talker_agent(FakeKnowledgeBase(passages), tickets=tickets), tickets


def text_call(
    agent: VoiceAgent, llm: FunctionLLM, tag: Tag, outbox: Outbox | None = None
) -> TextCall:
    """A text call of `agent` on `llm`, in `tag`, under the settings the server serves the
    talker with (`with_ticket_claims`), its caller the demo customer, its actions' writes kept
    in `outbox` (a new one in memory unless given, so a later call can share it)."""
    return TextCall(agent, llm=llm, settings=SETTINGS, caller=CALLER, language=tag, outbox=outbox)


@dataclass(frozen=True)
class Answer:
    """What the fake model writes (`steps`) in a request for the caller's turn whose message
    holds `heard`: its first request when `after` is None, else the one after the result of
    the tool `after`."""

    heard: str
    steps: Sequence[ScriptStep]
    after: str | None = None


def model(
    *answers: Answer,
    stop_over: Sequence[str] = (),
    judged: Mapping[str, Sequence[ScriptStep]] | None = None,
) -> FunctionLLM:
    """A fake model that answers each request with the first of `answers` that fits it; the
    interruption rule's request for an uncertain overlap with stop when the words said over the
    reply hold one of `stop_over`, else go_on; and the yes rule's check of an answer its lists
    leave unplaced (told by its instruction, D-082) by `judged` at the caller's words it holds,
    unclear for any other. AssertionError for any other request, which the call raises at its
    next step."""
    words_judged = dict(judged or {})

    def answer(request: ChatRequest) -> Sequence[ScriptStep]:
        if is_consent_check(request):
            return words_judged.get(checked(request), ScriptedLLM.reply("unclear"))
        if _judging(request):
            over = request.messages[-1].content.split(_OVER)[-1]
            return ScriptedLLM.reply("stop" if any(w in over for w in stop_over) else "go_on")
        said = [m for m in request.messages if m.role in ("user", "tool")]
        turn = next(m for m in reversed(said) if m.role == "user")
        names = {c.id: c.name for m in request.messages for c in m.tool_calls}
        after = names.get(said[-1].tool_call_id or "") if said[-1].role == "tool" else None
        for each in answers:
            if each.heard in turn.content and each.after == after:
                return each.steps
        raise AssertionError(f"the fake model has no answer for request {len(llm.requests)}")

    llm = FunctionLLM(answer)
    return llm


def _judging(request: ChatRequest) -> bool:
    """Whether `request` is the interruption rule's, asking about an uncertain overlap."""
    first = request.messages[0]
    return first.role == "system" and first.content == UNCERTAIN_OVERLAP_INSTRUCTION


def checked(request: ChatRequest) -> str:
    """The caller's words the yes rule's check `request` asks about."""
    said_as_data: dict[str, str] = json.loads(request.messages[-1].content)
    return said_as_data["answer"]


def checks(llm: FunctionLLM) -> list[str]:
    """The caller's words of each of the yes rule's checks the call asked the model, in order."""
    return [checked(request) for request in llm.requests if is_consent_check(request)]


def answered(call: TextCall, turn_id: int) -> list[tuple[str, str]]:
    """What the yes rule read the turn `turn_id` as, and by what (its lists or the model)."""
    return [
        (event.decision, event.by)
        for event in call._emitted
        if isinstance(event, ConfirmationAnswered) and event.turn_id == turn_id
    ]


def said(call: TextCall) -> str:
    """Every clause the agent said in the call, joined, an outcome's too, which answers no turn
    and so is in no turn's reads (TextCall reads no reply but a turn's)."""
    session = call._session
    assert session is not None
    replies = session.history.replies()
    return " ".join(c.text for r in replies for c in r.clauses if c.fate != "unplayed")


def blocks(call: TextCall) -> list[GuardBlocked]:
    """The guard's blocks the call reported, each with its rule's reason."""
    return [event for event in call._emitted if isinstance(event, GuardBlocked)]


def told(llm: FunctionLLM, heard: str) -> list[str]:
    """What the talker gave the model as the caller's turn whose words hold `heard`, once
    each."""
    found = []
    for request in llm.requests:
        if _judging(request) or is_consent_check(request):
            continue
        turns = [m.content for m in request.messages if m.role == "user"]
        if turns and heard in turns[-1] and turns[-1] not in found:
            found.append(turns[-1])
    return found


def results(llm: FunctionLLM, tool: str) -> list[str]:
    """The results of `tool` the model was given, as it read them, once each, in order."""
    found: dict[str, str] = {}
    for request in llm.requests:
        names = {c.id: c.name for m in request.messages for c in m.tool_calls}
        for m in request.messages:
            if m.role == "tool" and m.tool_call_id and names.get(m.tool_call_id) == tool:
                found.setdefault(m.tool_call_id, m.content)
    return list(found.values())


def grouped(number: str, tag: Tag) -> str:
    """A ticket number in four groups of four, as Ole5's `done` line says it in `tag`."""
    comma = ", " if tag == "en" else "، "  # the Arabic comma in Saudi Arabic
    return comma.join(number[n : n + 4] for n in range(0, len(number), 4))
