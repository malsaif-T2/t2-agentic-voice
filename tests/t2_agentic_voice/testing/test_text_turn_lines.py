"""What a `TextTurn`'s clauses say of whose words they are (testing/text_turn.py, turn_data.py),
end to end through `TextCall` on the library's own talker, session, read-back and action runner
(action_call_support.py): the talker's own words are its, and each line of the runtime's own a
turn's reply says (the read-back's summary and closing question, the sending line) is marked
`template`, so a runner that reads the talker's register reads its words alone; a reply that
never acted marks none."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.domain.ports.chat_model import TextDelta
from t2_agentic_voice.testing.text_call import TextCall
from t2_agentic_voice.testing.text_watch import plans_of

from tests.t2_agentic_voice.testing.action_call_support import (
    ENGLISH,
    SAUDI,
    SETTLE_S,
    Backend,
    Words,
    agent_of,
    call_action,
    model,
    say,
)

# The talker's own words before its action call, one clause in each language: «laHDHa min
# faDlak», a moment, please.
OWN = {"en": "All right, one moment.", "ar-SA": "لحظة من فضلك."}


@pytest.mark.parametrize("words", [ENGLISH, SAUDI], ids=lambda words: words.tag)
def test_the_runtimes_own_lines_are_marked_and_the_talkers_words_are_not(words: Words) -> None:
    backend = Backend()
    own = OWN[words.tag]
    llm = model({words.request: (TextDelta(text=f"{own} "), *call_action(words.note))})

    async def scene() -> tuple[list[tuple[str, bool]], list[tuple[str, bool]], tuple[str, ...]]:
        async with TextCall(agent_of(backend), llm=llm, language=words.tag) as call:
            asked = await call.user(words.request)
            await call.advance(SETTLE_S)
            sent = await call.user(words.yes_send)
            await call.advance(SETTLE_S)
            sent.expect.action_completed("book_visit")
            (plan,) = plans_of(call._watched)
            assert plan.summary.text in " ".join(c.text for c in asked.clauses if c.template)
            first = [(clause.text, clause.template) for clause in asked.clauses]
            after = [(clause.text, clause.template) for clause in sent.clauses]
            return first, after, call.violations

    first, after, violations = asyncio.run(scene())
    assert first[0] == (own, False) and len(first) > 1
    assert all(template for _, template in first[1:])  # the read-back, both its parts
    assert after and all(template for _, template in after)  # the sending line
    assert violations == ()


def test_a_reply_that_never_acted_marks_no_line() -> None:
    llm = model({ENGLISH.request: say("Open the menu, then the item.")})

    async def scene() -> list[bool]:
        async with TextCall(agent_of(Backend()), llm=llm, language="en") as call:
            turn = await call.user(ENGLISH.request)
            await call.advance(SETTLE_S)
            return [clause.template for clause in turn.clauses]

    marks = asyncio.run(scene())
    assert marks and not any(marks)
