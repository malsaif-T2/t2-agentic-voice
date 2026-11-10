"""An action's lines in the caller's register, end to end through `TextCall` (the owner's ruling
of 2026-11-10 on MSA read-backs; agent/language.py's `wording`): an `ar-SA` agent whose action
gives an `ar` text, MSA, beside each `ar-SA` one. A caller whose Arabic holds no dialect form
hears the MSA read-back and outcome, and the library's MSA lines where the action gives none
(its ask-again and sending lines); a Saudi caller hears the Saudi ones; each is said in the
call's tag, `ar-SA`, its voice. The talker, session, yes rule, guard and action runner are the
library's own, over a `MemoryOutbox` (action_call_support.py)."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.actions.action import Action, ActionContext, action
from t2_agentic_voice.domain.action_declaration import Claims, ReadBack, Say
from t2_agentic_voice.domain.action_lines import default_action_lines
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.testing.text_call import TextCall

from tests.t2_agentic_voice.testing.action_call_support import (
    ACTION,
    ROOM,
    SAUDI,
    SAUDI_CLAIM,
    SAUDI_DONE,
    SAUDI_QUESTION,
    SAUDI_SUMMARY,
    SETTLE_S,
    Backend,
    call_action,
    model,
)
from tests.t2_agentic_voice.testing.action_support import Booked, Visit

# The MSA read-back, "sa-aHjizu laka al-ghurfa {room} li-: {note}. hal ursilu aT-Talab?": I will
# book you room {room} for: {note}. Shall I send the request?
MSA_SUMMARY = "سأحجز لك الغرفة {room:id} من أجل: {note}."
MSA_QUESTION = "هل أرسل الطلب؟"
# "tamma dhalik, wa-raqmu al-Hajz {number}": done, and the booking's number is {number}.
MSA_DONE = "تم ذلك، ورقم الحجز {number:id}."
# The MSA caller: "ureedu Hajza al-ghurfa R-204, jihaazu al-'arD mu'aTTal": I want to book room
# R-204, the projector is broken.
MSA_REQUEST = f"أريد حجز الغرفة {ROOM}، جهاز العرض معطل"
MSA_NOTE = "جهاز العرض معطل"
YES = "نعم"  # na'am, yes
YES_SEND = "نعم أرسلها"  # na'am arsilha, yes, send it


def _book_in_two_registers(backend: Backend) -> Action:
    """`book_visit` read back in Saudi Arabic and in MSA, its `sending` and ask-again lines left
    to the library."""

    @action(
        description="Book a visit to a room. Ask for the room and what is wrong first.",
        read_back=ReadBack(
            {
                "en": ("I'll book room {room:id} for: {note}.", "Shall I send it?"),
                "ar-SA": (SAUDI_SUMMARY, SAUDI_QUESTION),
                "ar": (MSA_SUMMARY, MSA_QUESTION),
            }
        ),
        done=Say({"en": "Done, number {number:id}.", "ar-SA": SAUDI_DONE, "ar": MSA_DONE}),
        claims=Claims({"en": ["visit is booked"], "ar-SA": [SAUDI_CLAIM]}),
    )
    async def book_visit(ctx: ActionContext, draft: Visit) -> Booked:
        backend.writes += 1
        return backend.desk.book(ctx.request_id, draft)

    return book_visit


def _agent(backend: Backend) -> VoiceAgent:
    return VoiceAgent(
        name="visit-desk",
        languages=[Language.saudi_arabic(greeting="هلا."), Language.english(greeting="Hello.")],
        instructions="Book visits to rooms.",
        tools=[_book_in_two_registers(backend)],
    )


def _heard(call: TextCall) -> tuple[str, set[str]]:
    """Every clause the call's replies said, as captioned, joined, and the tags of the voices
    they were said in."""
    side, session = call._parts()
    replies = session.history.replies()
    said = " ".join(c.text for r in replies for c in r.clauses if c.fate != "unplayed")
    return said, {speak.language for speak in side.speaks.values()}


@pytest.mark.parametrize("register", ["msa", "saudi"])
def test_a_caller_hears_the_actions_lines_in_their_own_register_in_the_calls_voice(
    register: str,
) -> None:
    msa = register == "msa"
    request, note = (MSA_REQUEST, MSA_NOTE) if msa else (SAUDI.request, SAUDI.note)
    saudi = (SAUDI_SUMMARY, SAUDI_QUESTION, SAUDI_DONE)
    summary, question, done = (MSA_SUMMARY, MSA_QUESTION, MSA_DONE) if msa else saudi
    library = default_action_lines("ar" if msa else "ar-SA")
    backend = Backend()
    llm = model({request: call_action(note)})

    async def scene() -> tuple[str, set[str]]:
        async with TextCall(_agent(backend), llm=llm, language="ar-SA") as call:
            asked = await call.user(request)
            asked.expect.read_back(contains=note, room=ROOM, note=note)
            bare = await call.user(YES, during="closing_question")
            bare.expect.asked_again()
            await call.advance(10.0)
            sent = await call.user(YES_SEND)
            await call.advance(SETTLE_S)
            sent.expect.action_completed(ACTION)
            assert call.violations == ()
            return _heard(call)

    said, voices = asyncio.run(scene())
    lines = [
        summary.replace("{room:id}", ROOM).replace("{note}", note),
        question,
        library.asked_again,
        library.sending,
        done.replace("{number:id}", backend.numbers()[0]),
    ]
    assert [line for line in lines if line not in said] == [], said
    assert voices == {"ar-SA"}  # the call's voice, for the MSA lines too
