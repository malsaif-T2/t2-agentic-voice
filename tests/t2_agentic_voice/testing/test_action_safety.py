"""`ActionSafetySuite` (testing/action_safety.py, testing/action_scenes.py; plan 007): the
design's 9.3 cases, one `test_` method each, which pytest finds on a team's subclass and never on
the base; what a subclass must give, and what the suite refuses of it; and each case's setting:
the caller's lines in the call's language, the fake model answering by what each request holds,
the action swapped for its watched or faulted copy, and the suite's own tools beside it.

The cases themselves run a `TextCall` on the real session, the yes rule and the action runner:
tests/minimal_example/test_callback_safety.py runs them on the minimal example's action."""

from __future__ import annotations

import inspect
import json

import pytest
from pydantic import BaseModel
from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.actions.tools import Tool
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import (
    ChatMessage,
    ChatRequest,
    TextDelta,
    ToolCallRequest,
)
from t2_agentic_voice.domain.yes_words import ConsentWords
from t2_agentic_voice.evals import ActionSafetySuite
from t2_agentic_voice.testing import action_scenes
from t2_agentic_voice.testing.action_scenes import Scene

from tests.t2_agentic_voice.testing.action_support import (
    VISIT,
    Desk,
    Visit,
    agent_with,
    book_action,
)

# The design's 9.3, in its order, as the suite names its cases.
CASES = [
    "test_a_yes_over_the_summary_confirms_nothing",
    "test_an_eager_yes_before_the_read_back_confirms_nothing",
    "test_a_bare_yes_over_the_closing_question_is_asked_again",
    "test_a_call_whose_arguments_claim_consent_is_refused",
    "test_model_text_claiming_the_action_is_blocked",
    "test_model_text_after_the_action_call_is_dropped",
    "test_a_status_from_a_reports_on_tool_may_be_said",
    "test_a_passages_number_is_never_said_in_a_claim",
    "test_an_id_in_digit_words_or_arabic_indic_digits_counts_as_one",
    "test_a_lost_reply_the_lookup_finds_is_said_done",
    "test_a_lost_reply_no_lookup_finds_is_said_unknown",
    "test_a_refused_or_unsent_write_is_said_failed",
    "test_the_same_request_twice_is_written_once",
    "test_the_per_call_cap_holds",
    # For an agent that has a chat model judge what the lists leave unplaced (D-082).
    "test_a_model_yes_beside_a_change_marker_is_a_correction",
    "test_a_model_yes_beside_a_no_word_or_a_question_mark_is_asked_again",
    "test_a_check_that_fails_or_times_out_is_asked_again",
    "test_a_model_yes_over_the_closing_question_with_no_send_word_is_asked_again",
    "test_the_closing_question_heard_back_as_it_plays_confirms_nothing",
    "test_an_unlisted_yes_once_the_question_ended_confirms_once",
    # Said in the agent's other language than the read-back's (D-086).
    "test_a_yes_with_a_change_in_another_language_is_a_correction",
    "test_a_no_word_in_another_language_is_never_a_yes",
]


class _Booking(ActionSafetySuite):
    """A team's subclass, named so pytest never collects it here."""

    def make_agent(self) -> VoiceAgent:
        return agent_with(Desk())

    def action_under_test(self) -> Action:
        return book_action(Desk())

    def sample_draft(self) -> BaseModel:
        return VISIT


def _words(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[str, ...]]]:
    """The yes rule's word lists, stood in for: each call's code and the action's send words."""
    asked: list[tuple[str, tuple[str, ...]]] = []

    def words(code: str, *, action_send: tuple[str, ...] = (), **added: object) -> ConsentWords:
        asked.append((code, tuple(action_send)))
        return ConsentWords(yes=("yes",), send=("send it",), no=("no",), fillers=("please",))

    monkeypatch.setattr(action_scenes, "consent_words", words)
    return asked


def test_the_suite_holds_the_designs_cases_each_a_test_method() -> None:
    found = [name for name, _ in inspect.getmembers(ActionSafetySuite) if name.startswith("test_")]
    assert sorted(found) == sorted(CASES)
    assert not ActionSafetySuite.__name__.startswith("Test")  # pytest never runs the base
    for name in CASES:
        assert not inspect.iscoroutinefunction(getattr(ActionSafetySuite, name))  # sync


def test_a_subclass_gives_its_agent_action_and_draft_or_is_told_how() -> None:
    suite = ActionSafetySuite()
    for give in ("make_agent", "action_under_test", "sample_draft"):
        with pytest.raises(NotImplementedError, match=f"gives {give}\\(\\). FIX"):
            getattr(suite, give)()


def test_the_suite_refuses_a_subclass_whose_parts_do_not_fit() -> None:
    class NoSuchAction(_Booking):
        def make_agent(self) -> VoiceAgent:
            return agent_with(Desk()).model_copy(update={"tools": ()})

    class WrongDraft(_Booking):
        def sample_draft(self) -> BaseModel:
            return ConsentWords(yes=(), send=(), no=(), fillers=())

    class Unspoken(_Booking):
        language = "ar"

    for suite, said in [
        (NoSuchAction(), "declares no action named book_visit"),
        (WrongDraft(), "is not the action's draft"),
        (Unspoken(), "speaks no ar"),
    ]:
        with pytest.raises(AssertionError, match=said):
            suite._scene()


def test_a_scene_takes_the_agents_own_action_and_the_calls_language() -> None:
    suite = _Booking()
    scene = suite._scene()
    assert scene.action is scene.agent.tools[0] and scene.tag == "en" and scene.code == "en"
    assert scene.writes.action is scene.action and scene.language.greeting == "Hello."
    suite.language = "ar-SA"
    assert (suite._scene().tag, suite._scene().code) == ("ar-SA", "ar")


def test_a_scenes_lines_are_the_drafts_values_and_the_presets_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _words(monkeypatch)
    scene = _Booking()._scene()
    assert scene.request == "R-204 the projector is broken"
    assert (scene.yes, scene.yes_send, scene.claim) == ("yes", "yes send it", "request is booked")
    assert asked[-1] == ("en", ())
    assert scene.number == "48213" and scene.number not in json.dumps(scene.arguments)
    held = Visit(room="R-204", note="48213")
    taken = Scene(agent=scene.agent, action=scene.action, draft=held, tag="en")
    assert taken.number == "73905"


def test_a_scenes_action_is_swapped_and_its_tools_put_after_the_agents() -> None:
    scene = _Booking()._scene()
    counted = scene.writes.counted()

    async def status() -> str:
        return "open"

    tool = Tool.from_function(status, name="t2v_safety_status", description="A status.")
    agent = scene.with_action(counted, tools=[tool])
    assert agent.tools == (counted, tool) and scene.agent.tools == (scene.action,)


def _request(*messages: ChatMessage) -> ChatRequest:
    return ChatRequest(messages=(ChatMessage.system("Be brief."), *messages), model="m")


def test_a_scenes_model_answers_by_the_newest_line_or_tool_result() -> None:
    scene = _Booking()._scene()
    called = scene.call_action(confirmed=True)
    model = scene.model(
        {scene.request: called},
        after={"book_visit": tuple(scene.said_after_the_call("x"))},
    )
    asked = _request(ChatMessage.user(f"{scene.request} [said over your reply 1]"))
    assert tuple(model.fn(asked)) == called
    (request,) = [s for s in called if isinstance(s, ToolCallRequest)]
    assert json.loads(request.arguments) == {**scene.arguments, "confirmed": True}
    call = ToolCallRequest(id="call_1", name="book_visit", arguments="{}")
    answered = _request(
        ChatMessage.user(scene.request),
        ChatMessage.assistant(tool_calls=(call,)),
        ChatMessage.tool_result("call_1", "{}"),
        ChatMessage.system("Reply in English."),
    )
    after = list(model.fn(answered))
    assert isinstance(after[0], ToolCallRequest)
    assert [s.text for s in after if isinstance(s, TextDelta)] == [" x"]
    neutral = list(model.fn(_request(ChatMessage.user("something else"))))
    assert "".join(s.text for s in neutral if isinstance(s, TextDelta)) == "Hello."
