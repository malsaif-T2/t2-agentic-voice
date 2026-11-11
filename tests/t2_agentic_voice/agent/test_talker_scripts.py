"""The stray-script filter in the talker (agent/stray_script.py, agent/turn.py; domain/text/
scripts.py's rule), on the fake chat model: every piece the model writes and every string value
of its tool calls' arguments is filtered before anything reads it, so the clauses, the guard,
the next request, the trace and the read-back hold one filtered text.

- A stray character, in a piece of its own or a word cut across two, is in no `SpokenClause`, and
  the turn's next request holds the filtered text; a clause left with no letter or digit once a
  character went is no clause, while one written so is spoken as before.
- *Invariant 2* (docs/SECURITY.md): the guard reads the filtered text, the real rule A and rule B
  in an agent with an action and an empty record, so a stray character hides no claim and no
  number, and a number the evidence holds is said whole; with the setting off, as before.
- *Invariants 1 and 4:* a draft's stray character is gone from its read-back, the receipt's
  draft, the confirmed action and the outbox row alike; a fixed-set value with one parses as
  the member; a key is never changed, so a key holding one is refused as an extra field; text
  that is not JSON goes to the runner as written and is refused.
- A read tool's string values are filtered and its keys kept; a tool's result, its card and the
  caller's heard words reach their consumers as written; the terms the agent declares keep
  their characters.
- `ModelReplied` counts what went and labels it, 0 and () when nothing did; with the setting off,
  every event is as before."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from t2_agentic_voice.actions.tools import ToolResult, tool
from t2_agentic_voice.agent.stray_script import StrayScript
from t2_agentic_voice.agent.talker import (
    ClauseBlocked,
    ModelReplied,
    ReadBackRequested,
    ShownCard,
    SpokenClause,
    TalkerEvent,
    ToolBegan,
    ToolEnded,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import WordSettings
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import Done, TextDelta, ToolCallRequest
from t2_agentic_voice.domain.talker_declaration import Vocabulary

from tests.t2_agentic_voice.actions.action_support import CALL_ID, CALLER, confirmed_of
from tests.t2_agentic_voice.agent.action_talk_support import Acting, acting, rows
from tests.t2_agentic_voice.agent.chat_support import (
    ENGLISH,
    INSTRUCTIONS,
    FakeChat,
    call,
    calls,
    kinds,
    reply,
    said,
    talker,
)

TURN = TalkerTurn(turn_id=1, words="How do I reset my password?", language="en")
# "abi a'arf Talabi", I want to know about my request.
SAUDI_TURN = TalkerTurn(turn_id=1, words="ابي اعرف عن طلبي", language="ar-SA")
OFF = VoiceSettings(env="test", guard=GuardSettings(remove_stray_script=False))
SUMMARY = "the made-up laptop will not start"


@tool(description="Do a made-up quick thing.")
async def quick() -> dict[str, bool]:
    return {"ok": True}


@tool(description="Read the caller's made-up ticket number.")
async def ticket_number() -> dict[str, str]:
    return {"number": "12345"}


@tool(description="Find a made-up help page.")
async def find_page(query: str, labels: dict[str, str]) -> dict[str, str]:
    return {"found": query}


@tool(description="Read a made-up guide.")
async def guide() -> Any:
    return ToolResult(data={"title": "重置 guide"}, card=Card(title="重置 guide", steps=("重置",)))


def _spoken(events: list[TalkerEvent]) -> list[str]:
    return [e.text for e in events if isinstance(e, SpokenClause)]


def _blocked(events: list[TalkerEvent]) -> list[ClauseBlocked]:
    return [e for e in events if isinstance(e, ClauseBlocked)]


def _replied(events: list[TalkerEvent]) -> list[tuple[int, tuple[str, ...]]]:
    return [(e.stray_characters, e.stray_scripts) for e in events if isinstance(e, ModelReplied)]


def _plan(events: list[TalkerEvent]) -> Any:
    [read_back] = [e for e in events if isinstance(e, ReadBackRequested)]
    return read_back.plan


def test_a_stray_character_is_in_no_clause_and_the_next_request_holds_the_filtered_text() -> None:
    model = FakeChat(
        [
            TextDelta(text="Let me 重"),
            TextDelta(text="新check. "),
            TextDelta(text="重"),
            TextDelta(text="One moment. "),
            call("quick"),
            Done(finish_reason="tool_calls"),
        ],
        said("Done 😀."),
    )
    events = reply(talker(model, quick), TURN)
    assert _spoken(events) == ["Let me check.", "One moment.", "Done ."]
    [_, asked, _] = [m for m in model.requests[1].messages if m.role != "system"][-3:]
    assert asked.role == "assistant" and asked.content == "Let me check. One moment. "
    assert _replied(events) == [(3, ("CJK",)), (1, ("PICTOGRAPH",))]


def test_nothing_went_counts_nothing_and_a_clause_with_no_letter_is_spoken_as_before() -> None:
    events = reply(talker(FakeChat(said("Open Settings. → "))), TURN)
    assert _spoken(events) == ["Open Settings.", "→"]
    assert _replied(events) == [(0, ())]


def test_a_clause_left_with_no_letter_or_digit_once_a_character_went_is_no_clause() -> None:
    """«重置 → 确认» ("reset, then confirm") filtered leaves a lone arrow, which the voice drops:
    given as a clause, it would count as said and leave the caller in silence."""
    events = reply(talker(FakeChat(said("重置 → 确认"))), TURN)
    assert _spoken(events) == [] and _replied(events) == [(4, ("CJK",))]
    events = reply(talker(FakeChat(said("Open it. 重置 → 。"))), TURN)
    assert _spoken(events) == ["Open it."]
    assert "SpokenClause" not in kinds(reply(talker(FakeChat(said("重置确认。"))), TURN))


def test_a_stray_character_hides_no_claim_from_rule_a() -> None:
    """Invariant 2: «تم重 إنشاء طلبك» ("your request was created") and "I've 重created your
    ticket" read as the claims they are, with no record to back them; with the setting off the
    guard reads them as written, two words where the claim is one, as before."""
    claims: list[tuple[str, TalkerTurn, LanguageTag]] = [
        ("تم重 إنشاء طلبك.", SAUDI_TURN, "ar-SA"),
        ("I've 重created your ticket.", TURN, "en"),
    ]
    for words, turn, language in claims:
        events = reply(acting(FakeChat(said(words)), language=language).talker, turn)
        assert [b.reason for b in _blocked(events)] == ["unsupported_claim"], words
        assert _spoken(events) == []
        events = reply(acting(FakeChat(said(words)), settings=OFF, language=language).talker, turn)
        assert _spoken(events) == [words]


def test_a_stray_character_hides_no_number_from_rule_b() -> None:
    events = reply(acting(FakeChat(said("Your number is 12重34重5."))).talker, TURN)
    [blocked] = _blocked(events)
    assert (blocked.reason, blocked.unsupported) == ("unsupported_id", ("12345",))
    events = reply(acting(FakeChat(said("Your number is 12重34重5.")), settings=OFF).talker, TURN)
    assert _spoken(events) == ["Your number is 12重34重5."]


def test_the_guard_reads_the_filtered_number_so_one_the_evidence_holds_is_said_whole() -> None:
    """The filter runs before the guard: "12重345" is said as the tool's "12345"; read as
    written, it is blocked."""
    script = [calls(call("ticket_number")), said("Your number is 12重345.")]
    events = reply(acting(FakeChat(*script), ticket_number).talker, TURN)
    assert _spoken(events) == ["Your number is 12345."]
    events = reply(acting(FakeChat(*script), ticket_number, settings=OFF).talker, TURN)
    assert [b.reason for b in _blocked(events)] == ["unsupported_id"]


def test_fullwidth_digits_are_judged_as_their_ascii_form() -> None:
    fullwidth = reply(acting(FakeChat(said("It is ４５：２１：３３ now."))).talker, TURN)
    ascii_ = reply(acting(FakeChat(said("It is 45:21:33 now."))).talker, TURN)
    assert _spoken(fullwidth) == _spoken(ascii_) == ["It is 45:21:33 now."]
    assert _blocked(fullwidth) == _blocked(ascii_) == []


def _confirmed_and_written(rig: Acting, plan: Any) -> None:
    """`plan` confirmed as the yes rule would, from its receipt, and written."""

    async def run() -> None:
        outcome = await rig.runner.run(
            confirmed_of(plan),
            caller=CALLER,
            call_id=CALL_ID,
            language="en",
            turn_id=0,
            conversation=(),
            clock=rig.clock,
        )
        assert outcome.kind == "done"

    asyncio.run(run())


def test_a_drafts_stray_character_is_gone_from_the_read_back_receipt_and_outbox_alike() -> None:
    """Invariant 1: the read-back, the receipt's draft, the confirmed action and the outbox row
    hold one text, the filtered one; a fixed-set value with a stray character parses as the
    member it otherwise is."""
    model = FakeChat(calls(call("open_request", category="software重", summary=f"{SUMMARY}重")))
    rig = acting(model)
    events = reply(rig.talker, TURN)
    [began] = [e for e in events if isinstance(e, ToolBegan)]
    assert json.loads(began.arguments) == {"category": "software", "summary": SUMMARY}
    plan = _plan(events)
    assert plan.summary.text == f"A software request: {SUMMARY}."
    assert json.loads(plan.draft_json) == {"category": "software", "summary": SUMMARY}
    confirmed = confirmed_of(plan)
    assert confirmed.draft_json == plan.draft_json
    _confirmed_and_written(rig, plan)
    [row] = rows(rig.outbox)
    assert row.draft_json == plan.draft_json and "重" not in row.draft_json
    [(_, draft)] = rig.backend.writes
    assert (draft.category, draft.summary) == ("software", SUMMARY)


def test_a_key_holding_a_stray_character_is_kept_and_refused_as_an_extra_field() -> None:
    """Invariant 4: keys are never changed, so a field named like consent with a stray character
    is still a field the draft does not hold."""
    arguments = {"category": "software", "summary": SUMMARY, "confirmed重": True}
    written = json.dumps(arguments, ensure_ascii=False)
    request = ToolCallRequest(id="c-1", name="open_request", arguments=written)
    rig = acting(FakeChat(calls(request), said("Sorry.")))
    events = reply(rig.talker, TURN)
    [ended] = [e for e in events if isinstance(e, ToolEnded)]
    assert ended.failure == "bad_arguments" and "`confirmed重`" in ended.result
    assert "ReadBackRequested" not in kinds(events) and rows(rig.outbox) == ()


def test_arguments_that_are_not_json_go_to_the_runner_as_written_and_are_refused() -> None:
    written = '{"category": "software重", "summary": '
    request = ToolCallRequest(id="c-1", name="open_request", arguments=written)
    rig = acting(FakeChat(calls(request), said("Sorry.")))
    events = reply(rig.talker, TURN)
    [began] = [e for e in events if isinstance(e, ToolBegan)]
    [ended] = [e for e in events if isinstance(e, ToolEnded)]
    assert began.arguments == written and ended.failure == "bad_arguments"
    assert rows(rig.outbox) == ()


def test_a_read_tools_string_values_are_filtered_and_its_keys_kept() -> None:
    model = FakeChat(
        calls(call("find_page", query="reset重 password", labels={"名重": "a重b"})), said("Ok.")
    )
    events = reply(talker(model, find_page), TURN)
    [began] = [e for e in events if isinstance(e, ToolBegan)]
    expected = {"query": "reset password", "labels": {"名重": "ab"}}
    assert began.arguments == json.dumps(expected, ensure_ascii=False)
    [kept] = model.requests[1].messages[-3].tool_calls
    assert kept.arguments == began.arguments
    clean = ToolCallRequest(id="c-1", name="find_page", arguments='{"query":"x" ,  "n": 1.50}')
    events = reply(talker(FakeChat(calls(clean), said("Ok.")), find_page), TURN)
    assert [e.arguments for e in events if isinstance(e, ToolBegan)] == [clean.arguments]


def test_a_tools_result_its_card_and_the_heard_words_reach_their_consumers_as_written() -> None:
    turn = TalkerTurn(turn_id=1, words="How do I use 重置?", language="en")
    model = FakeChat(calls(call("guide")), said("Here it is."))
    events = reply(talker(model, guide), turn)
    assert model.requests[0].messages[-1].content == "How do I use 重置?"
    [shown] = [e for e in events if isinstance(e, ShownCard)]
    assert shown.card == Card(title="重置 guide", steps=("重置",))
    [ended] = [e for e in events if isinstance(e, ToolEnded)]
    assert "重置 guide" in ended.result
    assert "重置 guide" in model.requests[1].messages[-2].content


def test_the_terms_an_agent_declares_keep_their_characters() -> None:
    declared = VoiceAgent(
        name="helper",
        languages=[ENGLISH],
        instructions=INSTRUCTIONS["en"],
        pronounce={"μs": {"en": "microseconds"}},
        vocabulary=Vocabulary(terms=["Ωmega"]),
    )
    words = WordSettings.model_validate({"vocabulary": ["λ-desk"]})
    settings = VoiceSettings(env="test", words=words)
    text = "It takes 10 μs in Ωmega and λ-desk, not ψ."
    events = reply(talker(FakeChat(said(text)), declared=declared, settings=settings), TURN)
    assert _spoken(events) == ["It takes 10 μs in Ωmega and λ-desk, not ."]
    filtered = StrayScript.of(declared, settings)
    assert filtered.text("μ Ω λ ψ") == "μ Ω λ "
    assert filtered.take() == (1, ("GREEK",)) and filtered.take() == (0, ())


def test_with_the_setting_off_every_event_is_as_before() -> None:
    text = "Restart重 it 😀 now."
    on = reply(talker(FakeChat(said(text))), TURN)
    off = reply(talker(FakeChat(said(text)), settings=OFF), TURN)
    assert kinds(on) == kinds(off)
    assert _spoken(off) == [text] and _replied(off) == [(0, ())]
    assert _spoken(on) == ["Restart it now."] and _replied(on) == [(2, ("CJK", "PICTOGRAPH"))]
    request = call("find_page", query="a重")
    assert StrayScript(languages=["en"], on=False).call(request) is request
