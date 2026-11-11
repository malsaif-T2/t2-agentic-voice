"""A cancel, a stop or a question in answer to an action's read-back, end to end through
`TextCall` (D-081 and D-082 as amended by the owner's answer of 2026-11-11), on the library's own
talker, session, real interruption rule, yes rule and action runner over a `MemoryOutbox`
(action_call_support.py), in English and in Saudi Arabic (MSA reads the same `ar` lists).

- **A stop word over the summary is never ignored.** «خلاص» (khalas, enough) is a stop word of
  the interruption rule and a filler to the yes rule: said alone over the summary, it stops the
  read-back as `stopped`, with no receipt; the talker asks what to change. Said with a yes and a
  send word once the read-back played, it is still a yes; yes words and fillers alone over the
  summary are still ignored, the summary playing on.
- **A cancel said over the summary is a no.** "No, cancel it, don't send it." or «لا لا، لا
  ترسلها» over the summary reaches the talker with the no note, nothing sent; a no with a
  change in it is still a correction; and a no beside a stop word stays `stopped`.
- **A question in answer to the read-back goes to the talker.** For an agent that asks, the
  model's no on it drops the read-back, and the talker answers it in its own words.

Every word and line here is made up for the test."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from t2_agentic_voice.core.conversation import DeclineKind
from t2_agentic_voice.core.events import ConfirmationAnswered
from t2_agentic_voice.testing.text_call import TextCall
from t2_agentic_voice.testing.text_watch import plans_of

from tests.t2_agentic_voice.testing.action_call_support import (
    ACTION,
    ENGLISH,
    ROOM,
    SAUDI,
    SETTLE_S,
    Backend,
    Words,
    agent_of,
    asked_with,
    call_action,
    drafts_in,
    events,
    model,
    note,
    say,
    told,
)

LANGUAGES = [ENGLISH, SAUDI]
KHALAS = "خلاص"  # khalas: enough, that's it
WHAT = "What would you like to change?"
LEFT = "All right, I won't send it. Anything else?"
# Over the summary: a plain cancel; a no with a change in it; a no beside a stop word.
CANCELS = {
    "en": "No, cancel it, don't send it.",
    "ar-SA": "لا لا، لا ترسلها",  # la la, la tirsilha: no no, don't send it
}
CHANGES = {
    "en": "No, not Monday, since Thursday.",
    "ar-SA": "لا، مو الاثنين، الخميس",  # la, mu al-ithnain, al-khamees: no, not Monday, Thursday
}
STOPPING = {"en": "No, stop.", "ar-SA": "لا، وقف"}  # la, wagif: no, stop
QUESTIONS = {
    "en": "How do I reset my password?",
    # Tayyib, kaif aghayyir kalimat al-muroor?: OK, how do I change the password?
    "ar-SA": "طيب كيف أغير كلمة المرور؟",
}
ANSWER = "You can reset it from the sign-in page."
KINDS: tuple[DeclineKind, ...] = ("no", "correction", "stopped")


def _ids(words: Words) -> str:
    return words.tag


def test_khalas_alone_over_the_summary_stops_it_and_the_talker_asks() -> None:
    backend = Backend()
    llm = model({SAUDI.request: call_action(SAUDI.note), KHALAS: say(WHAT)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=SAUDI.tag) as call:
            await call.user(SAUDI.request)
            stop = await call.user(KHALAS, during="read_back")
            await call.advance(SETTLE_S)
            stop.expect.no_action()
            stop.expect.no_read_back()
            stop.expect.said(contains=WHAT)
            (request,) = asked_with(llm, KHALAS)
            assert note("stopped") in told(request)
            assert {"room": ROOM, "note": SAUDI.note} in drafts_in(request)  # the draft kept
            _, session = call._parts()
            assert not session._confirming.active
            eager = await call.user(SAUDI.yes_send)  # no receipt: nothing to confirm
            await call.advance(SETTLE_S)
            eager.expect.no_action()
            assert backend.writes == 0 and call._jobs is not None and not call._jobs.runs
            assert not [e for e in events(call) if isinstance(e, ConfirmationAnswered)]
            return call.violations

    assert asyncio.run(scene()) == ()


def test_khalas_with_a_yes_and_a_send_word_once_it_played_is_still_a_yes() -> None:
    """«ايه خلاص أرسلها» (eeh khalas arsilha: yes, that's it, send it): to the yes rule
    «خلاص» is still a filler."""
    backend, yes = Backend(), "ايه خلاص أرسلها"
    llm = model({SAUDI.request: call_action(SAUDI.note)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=SAUDI.tag) as call:
            await call.user(SAUDI.request)
            await call.advance(SETTLE_S)
            sent = await call.user(yes)
            await call.advance(SETTLE_S)
            sent.expect.confirmed(ACTION, room=ROOM, note=SAUDI.note)
            sent.expect.action_completed(ACTION)
            assert backend.writes == 1
            return call.violations

    assert asyncio.run(scene()) == ()


# Yes words, send words and fillers alone, which still count for nothing over the summary:
# «eeh», yes; «law samaHt», please; «yalla», come on.
IGNORED = [
    (ENGLISH, "yes"),
    (ENGLISH, "please"),
    (SAUDI, "ايه"),
    (SAUDI, "لو سمحت"),
    (SAUDI, "يلا"),
    (SAUDI, SAUDI.yes_send),
]


@pytest.mark.parametrize(("words", "said"), IGNORED, ids=[said for _, said in IGNORED])
def test_yes_words_and_fillers_alone_over_the_summary_are_still_ignored(
    words: Words, said: str
) -> None:
    backend = Backend()
    llm = model({words.request: call_action(words.note)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=words.tag) as call:
            asked = await call.user(words.request)
            over = await call.user(said, during="read_back")
            assert over.fate == "went_on"
            over.expect.no_action()
            assert asked_with(llm, said) == []  # never the talker's
            await call.advance(SETTLE_S)
            asked.expect.read_back(room=ROOM, note=words.note)
            _, session = call._parts()
            assert session._confirming.active  # it played on, still confirming
            assert backend.writes == 0
            return call.violations

    assert asyncio.run(scene()) == ()


@pytest.mark.parametrize(
    ("said", "kind", "reply"),
    [(CANCELS, "no", LEFT), (CHANGES, "correction", WHAT), (STOPPING, "stopped", WHAT)],
    ids=["cancel", "change", "stop"],
)
@pytest.mark.parametrize("words", LANGUAGES, ids=_ids)
def test_what_cuts_the_summary_reaches_the_talker_declined_by_what_it_says(
    words: Words, said: dict[str, str], kind: DeclineKind, reply: str
) -> None:
    """A plain no by the yes rule's lists is a no; a no with a change in it a correction; a
    stop word stays stopped. Nothing is sent, and the talker's note says which."""
    backend, heard = Backend(), said[words.tag]
    llm = model({words.request: call_action(words.note), heard: say(reply)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=words.tag) as call:
            await call.user(words.request)
            cut = await call.user(heard, during="read_back")
            await call.advance(SETTLE_S)
            cut.expect.no_action()
            cut.expect.no_read_back()
            cut.expect.said(contains=reply)
            (request,) = asked_with(llm, heard)
            assert note(kind) in told(request)
            others = [other for other in KINDS if other != kind]
            assert not any(note(other) in told(request) for other in others)
            _, session = call._parts()
            assert not session._confirming.active
            assert backend.writes == 0 and call._jobs is not None and not call._jobs.runs
            return call.violations

    assert asyncio.run(scene()) == ()


@pytest.mark.parametrize("words", LANGUAGES, ids=_ids)
def test_a_question_in_answer_to_the_read_back_judged_no_goes_to_the_talker(words: Words) -> None:
    """For an agent that asks: the model's no drops the read-back, once, and the talker answers
    the question in its own words; nothing is asked again or sent."""
    backend, question = Backend(), QUESTIONS[words.tag]
    judged: dict[str, Any] = {question: say("no")}
    llm = model({words.request: call_action(words.note), question: say(ANSWER)}, judged=judged)

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend, asks=True), llm=llm, language=words.tag) as call:
            await call.user(words.request)
            await call.advance(SETTLE_S)
            asked = await call.user(question)
            await call.advance(SETTLE_S)
            asked.expect.no_action()
            asked.expect.said(contains=ANSWER)
            (plan,) = plans_of(call._watched)
            assert not any(plan.asked_again.text in c.text for c in asked.clauses)
            (request,) = asked_with(llm, question)
            assert note("no") in told(request)
            found = [
                (e.decision, e.by) for e in events(call) if isinstance(e, ConfirmationAnswered)
            ]
            assert found == [("declined", "model")]
            assert backend.writes == 0
            return call.violations

    assert asyncio.run(scene()) == ()
