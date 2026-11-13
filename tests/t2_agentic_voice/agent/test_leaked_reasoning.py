"""The model's reasoning written into its answer, never said (agent/leaked_reasoning.py; D-089).

- **The two leaks seen**, the owner's live call `_Hdmiy0vDE` (2026-11-12) and run A's a2-dev, each
  glued to an Arabic sentence: the sentence before is said, nothing from the leak on, however the
  text is cut into pieces.
- **The tells**: in English, a glued sentence that opens as the reasoning does ("We need …")
  stops the reply; one that only starts the answer again ("…as needed.Open …") is said. A
  speaker's label at a sentence's start stops it, glued or not, and so does a reply that opens
  with one. Lowercase Latin, digits and a name in capitals not glued never do.
- **In the talker**: what was said before the leak is spoken, no request follows, a question
  glued to the next is counted by the question limit, and the log line holds the count alone."""

from __future__ import annotations

import logging

import pytest
from t2_agentic_voice.agent.leaked_reasoning import LeakedReasoning
from t2_agentic_voice.agent.talker import SpokenClause, TalkerEvent
from t2_agentic_voice.core.conversation import TalkerTurn

from tests.leaks import holding, shown
from tests.t2_agentic_voice.agent.chat_support import FakeChat, reply, said, talker

# The live call's reply, as the caller heard it (ahtaaj aakhir arba'at arqaam lit-tadhkara 'ashaan
# adeef al-mulaahaza, I need the ticket's last four digits to add the note).
SAID = "أحتاج آخر أربعة أرقام للتذكرة عشان أضيف الملاحظة."
LIVE = (
    f'{SAID}User: "ما أعرف، سولها". Possibly they want us to ask the system for ticket status? '
    "But we can't. So we need to ask them again for ticket number.ممكن تزودني بأخر أربعة أرقام "
    "للتذكرة؟أحتاج آخر أربعة أرقام للتذكرة لتحديث الملاحظة."
)
# Run A's a2-dev (ma 'indi ma'luumaat 'an tariiqat taghyiir lughat al-waajiha lil-ingliizi
# haaliyyan, I have no information on changing the interface language to English for now).
A2_SAID = "ما عندي معلومات عن طريقة تغيير لغة الواجهة للإنجليزي حالياً."
A2 = f"{A2_SAID}We need to respond accordingly.{A2_SAID}"


def _streamed(text: str, size: int, *, arabic: bool) -> tuple[str, LeakedReasoning]:
    leak = LeakedReasoning(arabic=arabic)
    given = "".join(leak.text(text[at : at + size]) for at in range(0, len(text), size))
    return given + leak.close(), leak


@pytest.mark.parametrize("size", [1, 2, 5, 13, 10_000])
@pytest.mark.parametrize(("text", "before"), [(LIVE, SAID), (A2, A2_SAID)])
def test_a_leak_glued_to_an_arabic_sentence_goes_from_its_first_character(
    text: str, before: str, size: int
) -> None:
    given, leak = _streamed(text, size, arabic=True)
    assert given == before
    assert (leak.found, leak.dropped) == (True, len(text) - len(before))


@pytest.mark.parametrize(
    ("text", "given"),
    [
        ("You can archive it.We need to check the policy. Then it is done.", "You can archive it."),
        ("Open it.According to the guide, yes.", "Open it."),
        ("Done. User: what now?", "Done. "),
        ("Assistant: here it is.", ""),
        ("It saves as needed.Open the correspondence. Then send.", None),
        ("Visit t2.example.It is 3.5.Users can send.", None),
        ("Sure, also visit t2.example. Users can then send.", None),
    ],
)
def test_the_tells_in_english(text: str, given: str | None) -> None:
    for size in (1, 4, 10_000):
        out, leak = _streamed(text, size, arabic=False)
        assert out == (text if given is None else given)
        assert leak.found is (given is not None)


@pytest.mark.parametrize(
    ("pieces", "arabic"),
    [
        (["Okay.\n\n", "User: hi"], False),
        (["Okay.", "\n\n", "User: hi"], False),
        (["Okay.  ", "User: hi"], False),
        (["Okay. ", " ", "User: hi"], False),
        (["Okay...\n", "\n", "Us", "er: hi"], False),
        (["\n\n\n", "User: hi"], False),
        (["تم.", "\n\n", "Assistant: x"], True),  # tamm, done
    ],
)
def test_a_label_after_spaces_given_apart_is_found_as_in_one_piece(
    pieces: list[str], arabic: bool
) -> None:
    """A sentence's start after an end mark and two or more spaces or line breaks, where an
    earlier piece ended in some of them, is read as it is in one piece."""
    whole = LeakedReasoning(arabic=arabic)
    whole_given = whole.text("".join(pieces)) + whole.close()
    leak = LeakedReasoning(arabic=arabic)
    given = "".join(leak.text(piece) for piece in pieces) + leak.close()
    assert whole.found
    assert (given, leak.found, leak.dropped) == (whole_given, True, whole.dropped)


def test_an_arabic_reply_with_latin_words_and_numbers_is_no_leak() -> None:
    # iftah Ole5 w-ikhtar Settings, ba'deen zur ds.t2.sa, open Ole5, choose Settings, then visit.
    text = "افتح Ole5 واختر Settings، بعدين زر ds.t2.sa أو الإصدار 3.5.ثم اضغط Ctrl + Shift + R."
    for size in (1, 3, 10_000):
        given, leak = _streamed(text, size, arabic=True)
        assert (given, leak.found) == (text, False)


def test_each_request_is_read_on_its_own() -> None:
    """A reply's second request, after a tool, never reads as glued to the first's last
    sentence."""
    leak = LeakedReasoning(arabic=True)
    first = leak.text("أدوّر لك في الدليل.") + leak.close()  # adawwir lak fid-daleel, I'll look
    second = leak.text("Ole5 فيه زر للأرشفة.") + leak.close()  # Ole5 has an archive button
    assert (first, second, leak.found) == ("أدوّر لك في الدليل.", "Ole5 فيه زر للأرشفة.", False)


SAUDI_TURN = TalkerTurn(turn_id=1, words="ما أعرف، سولها", language="ar-SA")


def _spoken(events: list[TalkerEvent]) -> list[str]:
    return [event.text for event in events if isinstance(event, SpokenClause)]


def test_the_talker_says_what_came_before_the_leak_and_logs_only_its_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    pieces = [LIVE[at : at + 7] for at in range(0, len(LIVE), 7)]
    model = FakeChat(said(*pieces))
    events = reply(talker(model, language="ar-SA"), SAUDI_TURN)
    assert _spoken(events) == [SAID]
    assert len(model.requests) == 1
    [record] = [r for r in caplog.records if r.getMessage() == "talker_reasoning_dropped"]
    fields = dict(record.fields)  # type: ignore[attr-defined]
    # the stream is closed once the leak begins: the count is what of it came before then
    assert fields["turn_id"] == 1 and 0 < fields["dropped_chars"] <= len(LIVE) - len(SAID)
    surfaces = shown(caplog=caplog)
    for value in ("Possibly they want", "ممكن تزودني", "سولها"):
        assert holding(value, surfaces) == [], value


def test_a_question_glued_to_the_next_is_counted_by_the_question_limit() -> None:
    # wish tihtaaj bid-dabt? wish ash-shay illi tibi tis'al 'anh? what exactly do you need? what
    # is it you want to ask about?
    model = FakeChat(said("وش تحتاج بالضبط؟وش الشي اللي تبي تسأل عنه؟"))
    events = reply(talker(model, language="ar-SA"), SAUDI_TURN)
    assert _spoken(events) == ["وش تحتاج بالضبط؟"]
