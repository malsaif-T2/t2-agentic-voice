"""Stage notes and tags the model writes into its answer, never said (agent/leaked_reasoning.py
under `guard.drop_stage_notes`; run F's f-dev-5, where a Saudi question was said with
"(Waiting for user response)" glued to it, and the search after it ran).

- **Off, the default**: every text below is said whole, as before (GP-18).
- **On**: in a reply in Arabic script, a parenthesis or bracket glued to a sentence's end with a
  capital Latin letter after it begins a leak; in any language, one that opens a stage word,
  glued or not, in any case; and a "<" that opens a tag (`TAGS`, a tool's or an action's name,
  "</" too); and in a reply in Arabic script, a sentence that opens as the reasoning does
  ("We need") after an Arabic sentence, after a space too, the reply's earlier request's
  sentence too (run F's f25). Arabic in parentheses, a Latin word in a parenthesis not glued,
  an English parenthesis that opens no stage word, a "<" before no tag, a Latin name after an
  Arabic sentence and an English "Let me check" after a space, under an Arabic tag too (a
  caller who speaks English on a call that did not move), are said, however the text is cut
  into pieces.
- **In the talker**: what came before the note is said, the request's tool does not run and no
  request follows; a tag of the agent's own tool is found; a reply moved to another language
  keeps the setting (`anew`)."""

from __future__ import annotations

import pytest
from t2_agentic_voice.actions.tools import tool
from t2_agentic_voice.agent.leaked_reasoning import LeakedReasoning
from t2_agentic_voice.agent.talker import SpokenClause, TalkerEvent
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.domain.ports.chat_model import Done, TextDelta

from tests.t2_agentic_voice.agent.chat_support import (
    FakeChat,
    Step,
    call,
    kinds,
    reply,
    said,
    talker,
)

NAMES = ("hold_seat",)
# mita tibi tsaafir? (when do you want to travel?)
ASKED = "متى تبي تسافر؟"
# ayy waHda tibi? (which one do you want?)
WHICH = "أي وحدة تبي؟"
CASES = [
    (f"{ASKED}(Waiting for the caller)(Waiting)", True, ASKED),
    (f"{WHICH}[Note: the caller may pick]", True, WHICH),  # glued, a capital Latin letter
    (f"{WHICH} [no reply yet]", True, f"{WHICH} "),  # a stage word, not glued, in lowercase
    # intiZaar radd al-'amiil: waiting for the customer's answer, an Arabic stage word
    (f"{WHICH}[انتظار رد العميل]", True, WHICH),
    # ma fiih maqaa'id, (qaa'imat al-intiZaar): no seats, (the waiting list), no note
    ("ما فيه مقاعد (قائمة الانتظار).", True, None),
    # illi tiTla' 07:40 b-610 riyaal (al-arkhaS), w-illi tiTla' 16:05: the 07:40 at 610 riyals
    # (the cheapest), and the 16:05.
    ("اللي تطلع 07:40 بـ 610 ريال (الأرخص)، واللي تطلع 16:05.", True, None),
    # tibiha 'ala (Business) walla as-siyaaHi? (do you want it in Business or economy?)
    ("تبيها على (Business) ولا السياحي؟", True, None),
    ("Which one would you like? (Pause for the answer.)", False, "Which one would you like? "),
    ("Sure.(No output)", False, "Sure."),
    ("The 07:40 (no seats left) and the 16:05 (the cheapest).", False, None),
    ('<action tool="hold_seat"/>', False, ""),
    ("Held.</data>", False, "Held."),
    ('Done. <hold_seat seat="12A">', False, "Done. "),
    ("Press <Enter> twice, then wait.", False, None),
    # f-dev-lean-4, f25: Hajazt ar-riHla bi-najaaH (I booked the trip), then the model's English
    # self-check after a space, said whole; in Arabic it never is speech.
    (
        "حجزت الرحلة بنجاح. We need to check if everything follows guidelines. Thus it is fine.",
        True,
        "حجزت الرحلة بنجاح. ",
    ),
    # tamm al-Hajz. T2 Air tirHab bik (it is booked. T2 Air welcomes you): a name, no tell.
    ("تم الحجز. T2 Air ترحب بك.", True, None),
    ("Sure. Let me check the flights for you.", False, None),
    # An English reply under the call's ar-SA tag: no Arabic sentence before the tell, so it is
    # speech, at the reply's start too.
    ("Sure. Let me check the flights for you.", True, None),
    ("Let me book that for you.", True, None),
    # «جدة» (jidda, Jeddah), an Arabic word quoted in an English reply: still English.
    ("Your flight to «جدة» is chosen. Let me read it back.", True, None),
]
TURN = TalkerTurn(turn_id=1, words="أبي أروح جدة", language="ar-SA")  # abi aruuH jidda


def _streamed(leak: LeakedReasoning, text: str, size: int) -> str:
    return (
        "".join(leak.text(text[at : at + size]) for at in range(0, len(text), size)) + leak.close()
    )


@pytest.mark.parametrize("size", [1, 2, 5, 10_000])
@pytest.mark.parametrize(("text", "arabic", "given"), CASES)
def test_a_stage_note_or_a_tag_is_a_leak_only_with_the_setting(
    text: str, arabic: bool, given: str | None, size: int
) -> None:
    off = LeakedReasoning(arabic=arabic)
    assert (_streamed(off, text, size), off.found) == (text, False)
    on = LeakedReasoning(arabic=arabic, stage_notes=True, names=NAMES)
    assert _streamed(on, text, size) == (text if given is None else given)
    assert on.found is (given is not None)
    assert on.dropped == (0 if given is None else len(text) - len(given))


def test_a_tell_after_a_space_reads_the_replys_earlier_requests_too() -> None:
    # f25's shape over two requests of one reply: the Arabic sentence ends the first.
    leak = LeakedReasoning(arabic=True, stage_notes=True)
    assert _streamed(leak, "حجزت الرحلة بنجاح.", 3) == "حجزت الرحلة بنجاح."
    assert (_streamed(leak, "We need to check the rules.", 3), leak.found) == ("", True)
    english = LeakedReasoning(arabic=True, stage_notes=True)
    assert _streamed(english, "Sure.", 3) == "Sure."
    said_whole = "Let me check the flights."
    assert (_streamed(english, said_whole, 3), english.found) == (said_whole, False)


def test_a_check_made_anew_for_another_language_keeps_the_stage_notes() -> None:
    moved = LeakedReasoning(arabic=True, stage_notes=True, names=NAMES).anew(arabic=False)
    assert (_streamed(moved, "<hold_seat/>", 3), moved.found) == ("", True)
    plain = LeakedReasoning(arabic=True).anew(arabic=False)
    assert (_streamed(plain, "<hold_seat/>", 3), plain.found) == ("<hold_seat/>", False)


@tool(description="Do a made-up quick thing.")
async def quick() -> dict[str, bool]:
    return {"ok": True}


def _spoken(events: list[TalkerEvent]) -> list[str]:
    return [event.text for event in events if isinstance(event, SpokenClause)]


def _noted(on: bool) -> VoiceSettings:
    return VoiceSettings(env="test", guard=GuardSettings(drop_stage_notes=on))


def test_the_talker_says_what_came_before_the_note_and_runs_no_tool_of_its_request() -> None:
    noted: list[Step] = [TextDelta(text=f"{ASKED}(Wait"), TextDelta(text="ing)"), call("quick")]
    model = FakeChat([*noted, Done(finish_reason="tool_calls")])
    events = reply(talker(model, quick, language="ar-SA", settings=_noted(True)), TURN)
    assert _spoken(events) == [ASKED]
    assert "ToolBegan" not in kinds(events) and len(model.requests) == 1
    # Off, as before: the note is said with its question, and the tool runs.
    model = FakeChat([*noted, Done(finish_reason="tool_calls")], said("تمام."))  # tamaam, okay
    events = reply(talker(model, quick, language="ar-SA", settings=_noted(False)), TURN)
    assert _spoken(events)[0] == f"{ASKED}(Waiting)"
    assert kinds(events).count("ToolEnded") == 1 and len(model.requests) == 2


def test_a_tag_of_the_agents_own_tool_is_never_said() -> None:
    english = TalkerTurn(turn_id=1, words="Hold a seat for me.", language="en")
    model = FakeChat(said("<qui", "ck>{}</quick>"))
    events = reply(talker(model, quick, settings=_noted(True)), english)
    assert _spoken(events) == [] and kinds(events)[-1] == "ReplyDone"
    events = reply(talker(FakeChat(said("<quick>{}</quick>")), quick), english)
    assert _spoken(events) == ["<quick>{}</quick>"]
