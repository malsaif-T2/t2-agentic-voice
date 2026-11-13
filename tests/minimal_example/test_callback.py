"""The minimal example's action (examples/minimal's callback.py), on the public API alone:
`request_callback`, a branch calling the caller back, booked at a made-up desk the example holds
in memory and reaches by a closure, on the quickstart helper's languages and read tool. The
talker sees the draft's schema and nothing more, so a branch outside the set or a field claiming
the caller's yes is refused before any read-back; the read-back says the branch by its label in
each language and shows nothing (the caller only hears the agent); a write books once for its
request ID and its lookup finds it; and each agent made has a desk of its own.

A call with it, in each language, runs on the real parts (plan 007's integration): `TextCall`'s
own talker on a scripted model that calls the action, the session's read-back and confirming,
the yes rule, the guard and the action runner over a `MemoryOutbox`. A yes over the read-back and
a bare yes over its closing question book nothing; a yes with a send word, heard once it played,
books once. Its yes and send words are the yes rule's presets' (domain/yes_words.py, read in
their rule form, domain/words.py, by a tag's primary code, core/settings/words.py: the only
imports from inside the library). `ActionSafetySuite` runs on it in test_callback_safety.py."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

import pytest
from minimal_example.app import helper, opening_hours
from minimal_example.callback import (
    CALLBACK_INSTRUCTIONS,
    MALAZ,
    OLAYA,
    CallbackBooked,
    CallbackDesk,
    CallbackRequest,
    make_callback_helper,
)
from pydantic import ValidationError
from t2_agentic_voice import (
    Action,
    ActionContext,
    Caller,
    HeardConsent,
    Spoken,
    VoiceAgent,
    render_prompt,
)
from t2_agentic_voice.core.settings.words import primary_code
from t2_agentic_voice.domain.words import rule_form
from t2_agentic_voice.domain.yes_words import PRESET_CONSENT
from t2_agentic_voice.evals import ScriptedLLM, TextCall

DRAFT = CallbackRequest(branch="olaya", reason="my order did not arrive")
# "Talabi ma waSal": my order did not arrive.
SAUDI_REASON = "طلبي ما وصل"
# Each language's call: the caller's request, the draft's reason, the branch's label, a yes, and
# a send word ("na'am" yes, "arsilha" send it), each a preset's word (checked below).
Tag = Literal["en", "ar-SA"]
CALLS: dict[Tag, tuple[str, str, str, str, str]] = {
    "en": ("Can Olaya call me back about my order?", DRAFT.reason, "Olaya", "yes", "send it"),
    # "mumkin far' al-olaya yittaSil 'alay? Talabi ma waSal": can the Olaya branch call me? My
    # order did not arrive.
    "ar-SA": (f"ممكن فرع {OLAYA} يتصل علي؟ {SAUDI_REASON}", SAUDI_REASON, OLAYA, "نعم", "أرسلها"),
}


def _callback(agent: VoiceAgent | None = None) -> Action:
    made = agent or make_callback_helper(CallbackDesk())
    found = [each for each in made.tools if isinstance(each, Action)]
    assert [each.name for each in found] == ["request_callback"]
    return found[0]


def _context(request_id: str) -> ActionContext:
    return ActionContext(
        caller=Caller(subject="u-1"),
        call_id="c-1",
        language="en",
        request_id=request_id,
        consent=HeardConsent(words="yes, send it", source="typed", speech_at=4.0),
    )


def _booked(action: Action, request_id: str) -> CallbackBooked:
    made = asyncio.run(action.execute(ctx=_context(request_id), draft=DRAFT))
    assert isinstance(made, CallbackBooked)
    return made


def test_the_agent_is_the_helpers_languages_and_tool_with_the_action() -> None:
    agent = make_callback_helper(CallbackDesk())
    assert agent.instructed and agent.languages == helper.languages
    assert agent.tools[0] is opening_hours
    assert [each.name for each in agent.tools] == ["opening_hours", "request_callback"]
    for language in agent.languages:
        assert CALLBACK_INSTRUCTIONS in render_prompt(agent, language.tag)


def test_the_talker_sees_the_drafts_schema_and_nothing_more() -> None:
    told = _callback().tool_schema()
    assert told.name == "request_callback" and "call the caller back" in told.description
    schema = json.loads(json.dumps(dict(told.parameters)))  # as it is sent
    assert sorted(schema["properties"]) == ["branch", "reason"]
    assert schema["properties"]["branch"]["enum"] == ["olaya", "malaz"]
    assert sorted(schema["required"]) == ["branch", "reason"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"branch": "diriyah", "reason": "x"},  # a branch outside the set
        {"branch": "olaya", "reason": "x" * 121},  # a reason past its bound
        {"branch": "olaya", "reason": "x", "confirmed": True},  # a yes claimed by the talker
        {"branch": "olaya"},
    ],
)
def test_a_draft_the_talker_gets_wrong_is_refused_before_any_read_back(
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _callback().parameters.model_validate(arguments)
    assert _callback().parameters.model_validate({"branch": "malaz", "reason": "x"})


def test_the_read_back_says_the_branch_by_its_label_and_shows_nothing() -> None:
    callback = _callback()
    assert callback.read_back.show_draft is False
    (spoken,) = [
        m for m in CallbackRequest.model_fields["branch"].metadata if isinstance(m, Spoken)
    ]
    assert (spoken.label("olaya", "ar-SA"), spoken.label("malaz", "ar-SA")) == (OLAYA, MALAZ)
    assert spoken.label("olaya", "en") == "Olaya"
    for language in helper.languages:
        summary, question = callback.read_back.for_language(language.tag)
        assert "{branch}" in summary and "{reason}" in summary and question
        assert "{number:id}" in callback.done.for_language(language.tag)
        assert callback.claims.for_language(language.tag)
    english = " ".join([*callback.read_back.for_language("en"), callback.done.for_language("en")])
    assert not {"screen", "card", "page", "button"} & set(english.lower().split())


def test_a_write_books_once_for_its_request_id_and_its_lookup_finds_it() -> None:
    own = CallbackDesk()
    callback = _callback(make_callback_helper(own))
    first = _booked(callback, "r-1")
    assert first == CallbackBooked(number="4101") and _booked(callback, "r-1") == first
    assert _booked(callback, "r-2") == CallbackBooked(number="4102")
    assert own.booked["r-1"] == (DRAFT, first) and len(own.booked) == 2
    assert callback.finder is not None
    assert asyncio.run(callback.finder(ctx=_context("r-9"), request_id="r-1")) == first
    assert asyncio.run(callback.finder(ctx=_context("r-9"), request_id="r-9")) is None


def test_each_agent_made_books_at_a_desk_of_its_own() -> None:
    first, second = CallbackDesk(), CallbackDesk()
    _booked(_callback(make_callback_helper(first)), "r-1")
    assert list(first.booked) == ["r-1"] and second.booked == {}
    with pytest.raises(ValidationError):
        CallbackBooked(number="41")  # the desk's numbers are four digits


def test_each_calls_yes_and_send_words_are_the_presets() -> None:
    for tag, (_, _, _, yes, send) in CALLS.items():
        words = PRESET_CONSENT[primary_code(tag)]
        assert rule_form(yes) in words.yes and rule_form(send) in words.send


@pytest.mark.parametrize("tag", list(CALLS))
def test_a_callback_is_booked_only_after_a_yes_heard_once_the_read_back_played(tag: Tag) -> None:
    request, reason, label, yes, send = CALLS[tag]
    desk = CallbackDesk()
    # One answer only: each later turn goes to the read-back's confirming, never to the model.
    llm = ScriptedLLM([ScriptedLLM.call_tool("request_callback", branch="olaya", reason=reason)])

    async def scene() -> tuple[str, ...]:
        async with TextCall(make_callback_helper(desk), llm=llm, language=tag) as call:
            asked = await call.user(request)
            over = await call.user(yes, during="read_back")  # over the summary: it plays on
            over.expect.no_action()
            assert desk.booked == {}
            asked.expect.read_back(contains=label, branch="olaya", reason=reason)
            bare = await call.user(yes, during="closing_question")
            bare.expect.asked_again()
            bare.expect.no_action()
            assert desk.booked == {}
            await call.advance(10.0)
            sent = await call.user(f"{yes} {send}")
            await call.advance(30.0)
            sent.expect.confirmed("request_callback", branch="olaya", reason=reason)
            sent.expect.action_ended("request_callback", "done")
            sent.expect.action_completed("request_callback")
            assert [booked.number for _, booked in desk.booked.values()] == ["4101"]
            rows = await call.outbox.entries(action="request_callback")
            assert [row.state for row in rows] == ["done"]
            return call.violations

    assert asyncio.run(scene()) == ()
