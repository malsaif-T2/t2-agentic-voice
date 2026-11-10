"""The output guard's rule A in the library's own talker, and a write that outlives its call, end
to end through `TextCall` (plan 007's integration; docs/SECURITY.md, invariants 2 and 6), on the
real talker, session, guard and action runner over a `MemoryOutbox` (action_call_support.py).

Model text claiming the action, in its own claim phrase or a default one, or in the call's other
language, with no record is never said: the session emits `GuardBlocked` for an unsupported
claim, and the call's checks stay clean. Once a write is done, a claim with the number it issued
is said, and so is one a `reports_on` tool's status backs, but not a status that found nothing,
which holds no number. A hang-up while the write runs lets it finish, once: its
`ActionCompleted` is emitted, and its line is never said after the call's end."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.events import ActionCompleted, ActionUnconfirmed, GuardBlocked
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.testing.llm_fakes import ScriptedLLM
from t2_agentic_voice.testing.text_call import TextCall
from t2_agentic_voice.testing.text_watch import plans_of

from tests.t2_agentic_voice.testing.action_call_support import (
    ACTION,
    ENGLISH,
    SAUDI,
    SETTLE_S,
    STATUS,
    Backend,
    Words,
    agent_of,
    call_action,
    events,
    model,
    said_texts,
    say,
)
from tests.t2_agentic_voice.testing.action_support import Visit

# A claim of each kind with no record, in each language: the action's own phrase, a default one
# ("I've booked"; «sajjalt lak», I registered for you), and the action's own phrase in the
# call's other language, as a model drifting into it writes it.
CLAIMS: dict[tuple[LanguageTag, str], str] = {
    ("en", "own"): "Your visit is booked.",
    ("en", "default"): "I've booked it for you.",
    ("en", "other"): "حجزت لك الغرفة.",
    ("ar-SA", "own"): "حجزت لك الغرفة.",  # Hajazt lak al-ghurfa: I booked you the room
    ("ar-SA", "default"): "سجلت لك الزيارة.",  # sajjalt lak az-ziyaara: I registered the visit
    ("ar-SA", "other"): "Your visit is booked.",
}
ASKED = {"en": "Is my visit booked?", "ar-SA": "حجزت الزيارة؟"}  # Hajazt az-ziyaara?
NUMBER = {"en": "What is my visit number?", "ar-SA": "كم رقم الحجز؟"}  # kam raqm al-Hajz?


def _blocked(call: TextCall) -> list[str]:
    return [e.reason for e in events(call) if isinstance(e, GuardBlocked)]


@pytest.mark.parametrize(("tag", "kind"), list(CLAIMS))
def test_a_claim_with_no_record_is_never_said(tag: LanguageTag, kind: str) -> None:
    claim = CLAIMS[(tag, kind)]
    backend = Backend()
    llm = model({ASKED[tag]: say(claim)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=tag) as call:
            turn = await call.user(ASKED[tag])
            await call.advance(SETTLE_S)
            turn.expect.blocked()
            assert all(claim not in clause.text for clause in turn.heard())
            assert all(claim not in text for text in said_texts(call))
            assert _blocked(call) == ["unsupported_claim"]
            assert backend.writes == 0
            return call.violations

    assert asyncio.run(scene()) == ()


@pytest.mark.parametrize("words", [ENGLISH, SAUDI], ids=lambda words: words.tag)
def test_once_a_write_is_done_a_claim_with_its_number_is_said(words: Words) -> None:
    backend = Backend()
    claimed = f"{CLAIMS[(words.tag, 'own')].rstrip('.')}, 5101."
    llm = model({words.request: call_action(words.note), NUMBER[words.tag]: say(claimed)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=words.tag) as call:
            await call.user(words.request)
            await call.advance(SETTLE_S)
            sent = await call.user(words.yes_send)
            await call.advance(SETTLE_S)
            sent.expect.action_completed(ACTION)
            assert backend.numbers() == ["5101"]
            asked = await call.user(NUMBER[words.tag])
            await call.advance(SETTLE_S)
            asked.expect.said(contains="5101")
            assert not asked.blocked and _blocked(call) == []
            return call.violations

    assert asyncio.run(scene()) == ()


def test_a_status_the_read_tool_reports_backs_a_claim_with_no_record() -> None:
    backend = Backend()
    backend.desk.book("r-earlier", Visit(room="R-204", note="the projector is broken"))
    claimed = "Your visit is booked, number 5101."
    llm = model({NUMBER["en"]: ScriptedLLM.call_tool(STATUS)}, after={STATUS: say(claimed)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language="en") as call:
            asked = await call.user(NUMBER["en"])
            await call.advance(SETTLE_S)
            asked.expect.tool_call(STATUS)
            asked.expect.said(contains=claimed)
            assert _blocked(call) == []
            return call.violations

    assert asyncio.run(scene()) == ()


def test_a_status_that_found_nothing_backs_no_claim() -> None:
    backend = Backend()  # nothing booked: the status holds no number
    claimed = "Your visit is booked."
    llm = model({NUMBER["en"]: ScriptedLLM.call_tool(STATUS)}, after={STATUS: say(claimed)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language="en") as call:
            asked = await call.user(NUMBER["en"])
            await call.advance(SETTLE_S)
            asked.expect.tool_call(STATUS)
            asked.expect.blocked()
            assert all(claimed not in text for text in said_texts(call))
            assert _blocked(call) == ["unsupported_claim"]
            return call.violations

    assert asyncio.run(scene()) == ()


def test_a_hang_up_while_the_write_runs_lets_it_finish_once_and_says_nothing_after() -> None:
    backend = Backend(gate=asyncio.Event())
    llm = model({ENGLISH.request: call_action(ENGLISH.note)})

    async def scene() -> TextCall:
        async with TextCall(agent_of(backend), llm=llm, language="en") as call:
            await call.user(ENGLISH.request)
            await call.advance(SETTLE_S)
            sent = await call.user(ENGLISH.yes_send)
            await call.advance(5.0)
            sent.expect.confirmed(ACTION)
            assert backend.writes == 1 and backend.desk.booked == {}  # the write waits
            (plan,) = plans_of(call._watched)
            sent.expect.said(contains=plan.sending.text)  # said while it runs
        assert backend.gate is not None
        backend.gate.set()
        for _ in range(200):
            if any(isinstance(e, ActionCompleted) for e in events(call)):
                break
            await asyncio.sleep(0)
        return call

    call = asyncio.run(scene())
    done = [e for e in events(call) if isinstance(e, ActionCompleted)]
    assert [e.action for e in done] == [ACTION]
    assert not [e for e in events(call) if isinstance(e, ActionUnconfirmed)]
    assert backend.writes == 1 and backend.numbers() == ["5101"]
    assert all("5101" not in text for text in said_texts(call))
    assert call._jobs is not None
    (run,) = call._jobs.runs
    assert run.outcome is not None and run.outcome.kind == "done"
