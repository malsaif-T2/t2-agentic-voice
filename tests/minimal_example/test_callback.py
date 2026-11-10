"""The minimal example's action (examples/minimal's callback.py), on the public API alone:
`request_callback`, a branch calling the caller back, booked at a made-up desk the example holds
in memory and reaches by a closure, on the quickstart helper's languages and read tool. The
talker sees the draft's schema and nothing more, so a branch outside the set or a field claiming
the caller's yes is refused before any read-back; the read-back says the branch by its label in
each language and shows nothing (the caller only hears the agent); a write books once for its
request ID and its lookup finds it; and each agent made has a desk of its own.

A call with it, the read-back played and a yes heard, runs on the library's runner, yes rule and
session, which plan 007's other tracks fill: `ActionSafetySuite` runs on it once they merge."""

from __future__ import annotations

import asyncio
import json

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

DRAFT = CallbackRequest(branch="olaya", reason="my order did not arrive")


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
