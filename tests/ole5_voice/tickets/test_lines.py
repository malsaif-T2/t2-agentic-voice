"""What Ole5's actions say (ole5_voice/tickets/lines.py): every text in each language Ole5
speaks, so the library's declaration takes them and refuses a language they miss; a read-back
that states every field it sends; a number said whole, digit by digit, in four groups (plan
007's Q6), and none in a line with no result; a closing question holding its send word, and no
other line a word the caller commands with; no line claiming its own action, naming a screen
or promising a person (D-009, D-075)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import pytest
from ole5_voice.agent import Tag, declare
from ole5_voice.tickets import lines
from ole5_voice.tickets.tools import ticket_tools
from t2_agentic_voice import (
    Action,
    ConfigurationError,
    Language,
    ReadBack,
    Say,
    VoiceAgent,
)
from t2_agentic_voice.languages import normalize_arabic, provider_text

from tests.ole5_voice.spoken_support import held
from tests.ole5_voice.tickets.ticket_support import mock

TAGS: tuple[Tag, ...] = ("ar-SA", "en")
# What a line the caller only hears never names, in each language (D-075); and what no line
# promises (D-009).
SEEN = ("screen", "card", "page", "button", "look at", "شاشة", "الشاشة", "صفحة", "الصفحة", "زر")
PROMISED = ("will call", "will contact", "is joining", "بيتصل", "بيكلمك", "بيتواصل")


def _actions(tmp_path: Path) -> list[Action]:
    return [each for each in ticket_tools(mock(tmp_path)) if isinstance(each, Action)]


def _form(text: str) -> str:
    return f" {normalize_arabic(provider_text(text))} "


def _lines_of(made: Action, tag: Tag) -> dict[str, str]:
    """Each line `made` speaks in `tag`, by its field, the read-back as its two parts."""
    summary, question = made.read_back.for_language(tag)
    found = {"summary": summary, "question": question}
    for name, text in made.texts.items():
        if isinstance(text, Say):
            found[name] = text.for_language(tag)
    return found


def test_each_action_speaks_every_language_ole5_speaks(tmp_path: Path) -> None:
    """The declaration's boundary checks: Ole5's talker takes them, and a talker that also
    spoke MSA (`ar`), which none of their texts is written for, is refused."""
    tools = ticket_tools(mock(tmp_path))
    talker = declare(tools)
    assert [language.tag for language in talker.languages] == list(TAGS)
    assert [tool.name for tool in talker.tools] == [
        "create_ticket",
        "add_ticket_note",
        "hand_off",
        "ticket_status",
    ]
    for made in _actions(tmp_path):
        assert {"sending", "failed", "unknown", "declined"} <= set(made.texts)
        for text in made.texts.values():
            assert all(text.covers(tag) for tag in TAGS)
            assert not text.covers("ar")  # the Saudi text never stands for MSA
    with pytest.raises(ConfigurationError, match="tools"):
        VoiceAgent(
            name="ole5",
            languages=[*talker.languages, Language.arabic(greeting="مرحبا بك.")],
            instructions="Made up.",
            tools=tools,
        )


def test_each_read_back_states_every_field_it_sends(tmp_path: Path) -> None:
    """Invariant 1's templates: the caller confirms what is sent. A handoff's says the call's
    conversation goes with it."""
    for made in _actions(tmp_path):
        assert made.read_back.show_draft is False  # the caller only hears the agent (D-075)
        assert made.read_back.placeholders == set(made.draft.model_fields)
        for tag in TAGS:
            summary, _ = made.read_back.for_language(tag)
            named = set(re.findall(r"{(\w+)", summary))
            assert named == set(made.draft.model_fields), (made.name, tag)
    summaries = lines.HANDOFF_READ_BACK.templates
    assert "what we said in this call" in summaries["en"][0]
    assert "كلامنا في هالمكالمة" in summaries["ar-SA"][0]


def test_a_ticket_made_is_said_whole_in_four_groups_and_no_other_line_says_a_number() -> None:
    """Q6 on creation; invariant 6: `unknown` has no number to say, nor do the lines said before
    there is a result."""
    for done in (lines.TICKET_DONE, lines.HANDOFF_DONE):
        for tag in TAGS:
            text = done.for_language(tag)
            places = [text.index(f"{{part_{n}:id}}") for n in range(1, 5)]
            assert places == sorted(places)
    assert lines.NOTE_DONE.placeholders == {"last_four"}
    assert "{last_four:id}" in lines.NOTE_DONE.for_language("en")
    for say in (
        lines.TICKET_SENDING,
        lines.TICKET_FAILED,
        lines.TICKET_UNKNOWN,
        lines.TICKET_DECLINED,
        lines.NOTE_SENDING,
        lines.NOTE_FAILED,
        lines.NOTE_UNKNOWN,
        lines.NOTE_DECLINED,
        lines.HANDOFF_SENDING,
        lines.HANDOFF_FAILED,
        lines.HANDOFF_UNKNOWN,
        lines.HANDOFF_DECLINED,
    ):
        assert say.placeholders == set()
        assert not any(re.search("[0-9]", text) for text in say.templates.values())


def test_only_a_closing_question_holds_a_word_the_caller_commands_with(tmp_path: Path) -> None:
    """Plan 006's item 6: no line's echo is heard as a stop, a wait, a repeat, a listening
    sound, a yes or a send; the closing question holds its action's own send word, so «نعم
    أرسلها» said over it counts (the design's 8.3)."""
    talker = declare(ticket_tools(mock(tmp_path)))
    for made in _actions(tmp_path):
        assert dict(made.read_back.send_words) == {
            code: tuple(words) for code, words in lines.SEND_WORDS.items()
        }
        for tag in TAGS:
            code: Literal["ar", "en"] = "en" if tag == "en" else "ar"
            for name, text in _lines_of(made, tag).items():
                found = held(text.replace("{", " ").replace("}", " "), code, talker)
                if name == "question":
                    sends = [_form(word) for word in lines.SEND_WORDS[code]]
                    assert any(send in _form(text) for send in sends), (made.name, tag)
                else:
                    assert found == [], (made.name, tag, name, found)


def test_no_line_claims_its_own_action_names_a_screen_or_promises_a_person(
    tmp_path: Path,
) -> None:
    """Rule A's phrases are the talker's to be held to; Ole5's own lines say the outcome in
    other words, so no echo of one reads as a claim. No line names a screen (D-075), and none
    says a person joins or will call (D-009)."""
    for made in _actions(tmp_path):
        for tag in TAGS:
            phrases = made.claims.for_language(tag)
            for name, text in _lines_of(made, tag).items():
                form = _form(text)
                assert [p for p in phrases if _form(p) in form] == [], (made.name, tag, name)
                for word in (*SEEN, *PROMISED):
                    assert _form(word) not in form, (made.name, tag, name, word)


def test_the_claim_phrases_cover_each_language_and_are_past_tense_claims() -> None:
    for claims in (lines.TICKET_CLAIMS, lines.NOTE_CLAIMS, lines.HANDOFF_CLAIMS):
        for tag in TAGS:
            phrases = claims.for_language(tag)
            assert len(phrases) >= 5 and len(set(phrases)) == len(phrases)
        assert all(phrase.isascii() for phrase in claims.for_language("en"))
    assert "I've opened" in lines.TICKET_CLAIMS.for_language("en")
    assert "رفعت طلبك" in lines.HANDOFF_CLAIMS.for_language("ar-SA")  # the design's 8.4


def test_every_read_back_is_a_pair_a_summary_and_its_closing_question() -> None:
    for read_back in (lines.TICKET_READ_BACK, lines.NOTE_READ_BACK, lines.HANDOFF_READ_BACK):
        assert isinstance(read_back, ReadBack) and set(read_back.templates) == set(TAGS)
        for summary, question in read_back.templates.values():
            assert question.endswith(("?", "؟")) and not summary.endswith(("?", "؟"))
