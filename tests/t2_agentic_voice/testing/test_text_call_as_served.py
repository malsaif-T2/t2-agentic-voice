"""A `TextCall` checks and acts as a served call does (testing/text_checks.py, text_call.py; plan
007's integration): what an action's call gave back, its refusal holding a number, is rule B's
evidence, as the talker keeps it for the output guard, so a clause the guard passes is no
violation; and the call's runner takes the daily cap per caller from the settings, as the
runtime's does (api/actions.py)."""

from __future__ import annotations

import asyncio
from typing import Annotated

from pydantic import BaseModel, Field
from t2_agentic_voice import (
    ActionContext,
    Claims,
    Language,
    LimitSettings,
    ReadBack,
    Say,
    ToolError,
    VoiceAgent,
    VoiceSettings,
    action,
)
from t2_agentic_voice.evals import ScriptedLLM, TextCall

FREE = "48291377"  # a made-up room the refusal offers


class Visit(BaseModel):
    room: Annotated[str, Field(min_length=1, max_length=20)]


class Booked(BaseModel):
    code: str


def _agent(booked: list[str], *, refuse: bool) -> VoiceAgent:
    async def free_room(ctx: ActionContext, draft: Visit) -> Visit:
        if refuse:
            raise ToolError(f"Room {draft.room} is taken; room {FREE} is free, offer it.")
        return draft

    @action(
        description="Book a visit to a room.",
        read_back=ReadBack({"en": ("I'll book room {room}.", "Shall I send it?")}),
        done=Say(en="Done."),
        claims=Claims({"en": ["booked your visit"]}),
        validate=free_room,
        max_per_call=3,
    )
    async def book_visit(ctx: ActionContext, draft: Visit) -> Booked:
        booked.append(draft.room)
        return Booked(code=str(len(booked)))

    return VoiceAgent(
        name="rooms",
        languages=[Language.english(greeting="Hello.")],
        instructions="Book visits.",
        tools=[book_visit],
    )


def test_a_refusal_holding_a_number_is_evidence_as_for_the_guard() -> None:
    said = f"Room R-204 is taken, but room {FREE} is free."
    llm = ScriptedLLM([ScriptedLLM.call_tool("book_visit", room="R-204"), ScriptedLLM.reply(said)])

    async def scene() -> None:
        async with TextCall(_agent([], refuse=True), llm=llm, language="en") as call:
            turn = await call.user("Book me a visit to room R-204.")
            await call.advance(30.0)
            assert turn.blocked == ()  # the guard read the refusal
            turn.expect.said(contains=FREE)
            assert call.violations == ()

    asyncio.run(scene())


def test_the_calls_runner_takes_the_daily_cap_per_caller_from_the_settings() -> None:
    booked: list[str] = []
    settings = VoiceSettings(env="test", limits=LimitSettings(actions_per_caller_per_day=1))
    llm = ScriptedLLM(
        [
            ScriptedLLM.call_tool("book_visit", room="R-204"),
            ScriptedLLM.call_tool("book_visit", room="R-305"),
            ScriptedLLM.reply("I can't book another visit today."),
        ]
    )

    async def scene() -> None:
        agent = _agent(booked, refuse=False)
        async with TextCall(agent, llm=llm, language="en", settings=settings) as call:
            await call.user("Book me a visit to room R-204.")
            await call.advance(10.0)
            await call.user("yes send it")
            await call.advance(30.0)
            second = await call.user("And one to room R-305, please.")
            await call.advance(10.0)
            second.expect.no_read_back()  # refused before it, as the runtime's runner refuses
            assert call.violations == ()

    asyncio.run(scene())
    assert booked == ["R-204"]
