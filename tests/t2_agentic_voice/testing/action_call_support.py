"""What the end-to-end calls with an action share (test_action_calls.py and the files beside it;
plan 007's integration): an agent with one action, `book_visit`, over a made-up desk the test
holds (action_support.py's `Desk`), read back in English and in Saudi Arabic, and a read tool,
`visit_status`, that reports on it; each language's caller's words, the yes, send, stop, repeat
and no words taken from the presets; and a fake model that answers each request by the caller's
newest line or a tool's result, so a case never counts requests.

Nothing here stands in for the library: each call is a `TextCall` on its own talker, session,
read-back, yes rule, guard and action runner over a `MemoryOutbox`."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from t2_agentic_voice.actions.action import Action, ActionContext, action
from t2_agentic_voice.actions.tools import Tool, ToolResult
from t2_agentic_voice.agent.context import DECLINED
from t2_agentic_voice.core.conversation import DeclineKind
from t2_agentic_voice.core.events import Event
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.action_declaration import Claims, ReadBack, Say
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatRequest
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.domain.yes_words import PRESET_CONSENT
from t2_agentic_voice.testing.llm_fakes import FunctionLLM, ScriptedLLM, ScriptStep
from t2_agentic_voice.testing.text_call import TextCall

from tests.t2_agentic_voice.testing.action_support import Booked, Desk, Visit

ACTION, STATUS = "book_visit", "visit_status"
ROOM = "R-204"
# The Saudi read-back, "baHjiz lak al-ghurfa {room} 'ashan: {note}. arsil aT-Talab?": I'll book
# you room {room} for: {note}. Shall I send the request?
SAUDI_SUMMARY = "بحجز لك الغرفة {room:id} عشان: {note}."
SAUDI_QUESTION = "أرسل الطلب؟"
# "tamm, raqm al-Hajz {number}": done, the booking's number is {number}.
SAUDI_DONE = "تم، رقم الحجز {number:id}."
# "Hajazt lak al-ghurfa": I booked you the room.
SAUDI_CLAIM = "حجزت لك الغرفة"
ENGLISH_CLAIM = "visit is booked"
# How long a case lets the call run on after the caller's words: the read-back, the sending line
# and the outcome all played (seconds on the call's clock).
SETTLE_S = 30.0


@dataclass(kw_only=True)
class Backend:
    """The desk the action books at, the writes it was asked for (`writes`), and, when given, a
    gate each write waits on before it books (`gate`)."""

    desk: Desk = field(default_factory=Desk)
    gate: asyncio.Event | None = None
    writes: int = 0

    def numbers(self) -> list[str]:
        return [str(5100 + index) for index in range(1, len(self.desk.booked) + 1)]


def book_action(backend: Backend) -> Action:
    """`book_visit`, booking at `backend`'s desk, reached by a closure."""

    @action(
        description="Book a visit to a room. Ask for the room and what is wrong first.",
        read_back=ReadBack(
            {
                "en": ("I'll book room {room:id} for: {note}.", "Shall I send it?"),
                "ar": (SAUDI_SUMMARY, SAUDI_QUESTION),
            }
        ),
        done=Say(en="Done, your visit number is {number:id}.", ar=SAUDI_DONE),
        claims=Claims({"en": [ENGLISH_CLAIM, "booked your visit"], "ar": [SAUDI_CLAIM]}),
    )
    async def book_visit(ctx: ActionContext, draft: Visit) -> Booked:
        backend.writes += 1
        if backend.gate is not None:
            await backend.gate.wait()
        return backend.desk.book(ctx.request_id, draft)

    return book_visit


def status_tool(backend: Backend) -> Tool:
    """`visit_status`, the last visit booked at `backend`'s desk, a report on `book_visit`."""

    async def visit_status() -> ToolResult:
        numbers = backend.numbers()
        if not numbers:
            return ToolResult(data={"state": "none"})
        return ToolResult(data={"number": numbers[-1], "state": "booked"}, evidence=(numbers[-1],))

    return Tool.from_function(
        visit_status,
        description="The caller's last visit booked, and its state.",
        reports_on=[ACTION],
    )


def agent_of(backend: Backend) -> VoiceAgent:
    return VoiceAgent(
        name="visit-desk",
        languages=[Language.english(greeting="Hello."), Language.saudi_arabic(greeting="هلا.")],
        instructions="Book visits to rooms, and tell a caller how their visit stands.",
        tools=[book_action(backend), status_tool(backend)],
    )


@dataclass(frozen=True, kw_only=True)
class Words:
    """One language's call: the caller's request and the draft's note in it, a second note for
    a change, and the preset's yes, send, stop, pause, repeat and no words."""

    tag: LanguageTag
    request: str
    note: str
    changed: str
    yes: str
    send: str
    stop: str
    wait: str
    repeat: str
    no: str

    @property
    def code(self) -> LanguageCode:
        return "en" if self.tag == "en" else "ar"

    @property
    def yes_send(self) -> str:
        return f"{self.yes} {self.send}"

    @property
    def claim(self) -> str:
        return ENGLISH_CLAIM if self.tag == "en" else SAUDI_CLAIM


ENGLISH = Words(
    tag="en",
    request=f"Please book room {ROOM}, the projector is broken.",
    note="the projector is broken",
    changed="the screen is broken",
    yes=PRESET_CONSENT["en"].yes[0],
    send="send it",
    stop=PRESET_WORDS["en"].stop[0],
    wait=PRESET_WORDS["en"].wait[0],
    repeat=PRESET_WORDS["en"].repeat[0],
    no=PRESET_WORDS["en"].no[0],
)
SAUDI = Words(
    tag="ar-SA",
    # "abghaak tiHjiz li al-ghurfa R-204, al-brojektar kharbaan": book me room R-204, the
    # projector is broken.
    request=f"أبغاك تحجز لي الغرفة {ROOM}، البروجكتر خربان",
    note="البروجكتر خربان",
    changed="الشاشة خربانة",  # "ash-shaasha kharbaana": the screen is broken
    yes="نعم",  # na'am, yes
    send="أرسلها",  # arsilha, send it
    stop=PRESET_WORDS["ar"].stop[0],
    wait=PRESET_WORDS["ar"].wait[0],
    repeat=PRESET_WORDS["ar"].repeat[0],
    no=PRESET_WORDS["ar"].no[0],
)


def call_action(note: str, *, room: str = ROOM) -> tuple[ScriptStep, ...]:
    """The model's call of `book_visit` with the draft."""
    return ScriptedLLM.call_tool(ACTION, room=room, note=note)


def say(text: str) -> tuple[ScriptStep, ...]:
    return ScriptedLLM.reply(text)


def model(
    lines: Mapping[str, Sequence[ScriptStep]],
    *,
    after: Mapping[str, Sequence[ScriptStep]] | None = None,
    neutral: str = "How can I help?",
) -> FunctionLLM:
    """The fake model: a request whose newest message is the caller's turn answered by `lines`
    at its words (the turn's message is its words, then the notes the talker adds), one whose
    newest is a tool's result by `after` at the tool's name, and `neutral` otherwise."""
    answered_after = dict(after or {})

    def answer(request: ChatRequest) -> Sequence[ScriptStep]:
        said = [m for m in request.messages if m.role in ("user", "tool")]
        if not said:
            return say(neutral)
        newest = said[-1]
        if newest.role == "tool":
            calls = [c for m in request.messages for c in m.tool_calls]
            tool = next((c.name for c in calls if c.id == newest.tool_call_id), "")
            return answered_after.get(tool, say(neutral))
        for words, steps in lines.items():
            if newest.content == words or newest.content.startswith(f"{words} ["):
                return steps
        return say(neutral)

    return FunctionLLM(answer)


def asked_with(llm: FunctionLLM, words: str) -> list[ChatRequest]:
    """Each model request whose newest user message is the caller's `words`, with its notes."""
    found = []
    for request in llm.requests:
        users = [m.content for m in request.messages if m.role == "user"]
        if users and (users[-1] == words or users[-1].startswith(f"{words} [")):
            found.append(request)
    return found


def told(request: ChatRequest) -> str:
    """The newest user message of `request`: the turn's words, then the talker's notes."""
    return [m.content for m in request.messages if m.role == "user"][-1]


def drafts_in(request: ChatRequest) -> list[dict[str, object]]:
    """The arguments of each call of `book_visit` the history of `request` holds, parsed."""
    calls = [c for m in request.messages for c in m.tool_calls if c.name == ACTION]
    return [json.loads(call.arguments) for call in calls]


def note(kind: DeclineKind) -> str:
    """The talker's note of a read-back declined as `kind`, for `book_visit`."""
    return DECLINED[kind].format(action=ACTION)


def events(call: TextCall) -> list[Event]:
    """The call's events as its session emitted them, in order."""
    return list(call._emitted)


def said_texts(call: TextCall) -> list[str]:
    """Every clause of every reply the session asked for, as captioned, in order."""
    _, session = call._parts()
    return [clause.text for reply in session.history.replies() for clause in reply.clauses]
