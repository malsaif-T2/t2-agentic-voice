"""What Ole5's actions say (ole5_voice/tickets/lines.py): every text in each language Ole5
speaks, so the library's declaration takes them and refuses a language they miss, and each line
in MSA too, which an MSA caller hears (the owner's ruling of 2026-11-10); a read-back that
states every field it sends; a number said whole, digit by digit, in four groups (plan 007's
Q6), and none in a line with no result; a closing question holding its send word, and no other
line a word the caller commands with; no line holding a claim phrase of any action or one that
claims any, Ole5's for a ticket's number among them (the owner's ruling of 2026-11-10), naming
a screen or promising a person (D-009, D-075); and no MSA line holding a dialect form."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final, Literal

import pytest
from ole5_voice.agent import Tag, declare
from ole5_voice.tickets import lines
from ole5_voice.tickets.tools import ticket_tools, with_ticket_claims
from t2_agentic_voice import (
    Action,
    Claims,
    ConfigurationError,
    Language,
    ReadBack,
    Say,
    VoiceAgent,
    VoiceSettings,
)
from t2_agentic_voice.domain.claims import (
    ClaimVerdict,
    any_action_claims,
    check_claims,
    every_language,
)
from t2_agentic_voice.domain.yes_words import PRESET_CONSENT
from t2_agentic_voice.languages import normalize_arabic, provider_text, register_of

from tests.ole5_voice.spoken_support import held
from tests.ole5_voice.tickets.ticket_support import mock

TAGS: tuple[Tag, ...] = ("ar-SA", "en")
# The texts each line is read in: Ole5's two languages, and MSA, which an `ar-SA` reply to a
# caller who speaks MSA reads (the library's `wording`).
WORDINGS: tuple[Tag, ...] = ("ar-SA", "ar", "en")
# What a line the caller only hears never names, in each language (D-075); and what no line
# promises (D-009).
SEEN = ("screen", "card", "page", "button", "look at", "شاشة", "الشاشة", "صفحة", "الصفحة", "زر")
PROMISED = (
    "will call",
    "will contact",
    "is joining",
    "بيتصل",
    "بيكلمك",
    "بيتواصل",
    "سيتصل",  # sa-yattaSil: will call
    "سيتواصل",  # sa-yatawaaSal: will contact
)
# The Saudi forms of Ole5's Saudi lines and of the judge's register question, each as a word's
# start, which no MSA line holds: tabi, want (as in tabeeni, do you want me to); illi, which;
# al-heen, now; and the future's b- before a verb: baftaH, I'll open; baHawwil, I'll pass on.
SAUDI_FORMS: Final = ("تبي", "اللي", "الحين", "بفتح", "بحول", "بضيف", "هال")


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


def _commands_or_yes(line: str, code: Literal["ar", "en"], talker: VoiceAgent) -> list[str]:
    """The words of the agent's stop, wait, repeat and listening lists, and the yes rule's yes
    words, that `line` holds as whole words: none, even in a closing question, which holds a
    send word alone."""
    words = talker.phrases.words(code)
    listed = [*words.stop, *words.wait, *words.repeat, *words.backchannel]
    form = _form(line.replace("{", " ").replace("}", " "))
    return [w for w in (*listed, *PRESET_CONSENT[code].yes) if _form(w) in form]


def _words(text: str) -> list[str]:
    """`text`'s words, each placeholder and mark left out."""
    plain = re.sub(r"{\w+(:id)?}", " ", text)
    return [normalize_arabic(word.strip("،؛؟.,!?:")) for word in plain.split()]


def test_each_action_speaks_every_language_ole5_speaks(tmp_path: Path) -> None:
    """The declaration's boundary checks: Ole5's talker takes them, with an MSA text beside
    each Saudi line, which declares no language of its own; a talker that also spoke MSA (`ar`)
    is still refused, its claim phrases written for none."""
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
            keys = text.phrases if isinstance(text, Claims) else text.templates
            assert ("ar" in keys) is not isinstance(text, Claims), made.name
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
        for tag in WORDINGS:
            summary, _ = made.read_back.for_language(tag)
            named = set(re.findall(r"{(\w+)", summary))
            assert named == set(made.draft.model_fields), (made.name, tag)
    summaries = lines.HANDOFF_READ_BACK.templates
    assert "what we said in this call" in summaries["en"][0]
    assert "كلامنا في هالمكالمة" in summaries["ar-SA"][0]
    assert "محادثتنا في هذه المكالمة" in summaries["ar"][0]  # our conversation in this call


def test_a_ticket_made_is_said_whole_in_four_groups_and_no_other_line_says_a_number() -> None:
    """Q6 on creation; invariant 6: `unknown` has no number to say, nor do the lines said before
    there is a result."""
    for done in (lines.TICKET_DONE, lines.HANDOFF_DONE):
        for tag in WORDINGS:
            text = done.for_language(tag)
            places = [text.index(f"{{part_{n}:id}}") for n in range(1, 5)]
            assert places == sorted(places)
    assert lines.NOTE_DONE.placeholders == {"last_four"}
    for tag in WORDINGS:
        assert "{last_four:id}" in lines.NOTE_DONE.for_language(tag)
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
        assert set(say.templates) == set(WORDINGS)
        assert not any(re.search("[0-9]", text) for text in say.templates.values())


def test_only_a_closing_question_holds_a_word_the_caller_commands_with(tmp_path: Path) -> None:
    """Plan 006's item 6: no line's echo is heard as a stop, a wait, a repeat, a listening
    sound, a yes or a send; the closing question holds its action's own send word, so «نعم
    أرسلها» said over it counts (the design's 8.3), in MSA too («هل أرسلها؟», hal ursiluha:
    shall I send it?)."""
    talker = declare(ticket_tools(mock(tmp_path)))
    for made in _actions(tmp_path):
        assert dict(made.read_back.send_words) == {
            code: tuple(words) for code, words in lines.SEND_WORDS.items()
        }
        for tag in WORDINGS:
            code: Literal["ar", "en"] = "en" if tag == "en" else "ar"
            for name, text in _lines_of(made, tag).items():
                found = held(text.replace("{", " ").replace("}", " "), code, talker)
                if name == "question":
                    sends = [_form(word) for word in lines.SEND_WORDS[code]]
                    assert any(send in _form(text) for send in sends), (made.name, tag)
                    assert _commands_or_yes(text, code, talker) == [], (made.name, tag)
                else:
                    assert found == [], (made.name, tag, name, found)


def test_no_line_holds_a_claim_names_a_screen_or_promises_a_person(tmp_path: Path) -> None:
    """Rule A's phrases are the talker's to be held to; Ole5's own lines say the outcome in
    other words, so the talker, which reads them in the call's history, copies no claim from
    one: no line holds a phrase the guard reads as a claim, matched as the guard matches it,
    every action's, the library's defaults or Ole5's for a ticket's number (`NUMBER_CLAIMS`,
    the owner's ruling of 2026-11-10), so `done` says a ticket's number with no «رقم تذكرتك»
    and no "your ticket number is". No line names a screen (D-075), and none says a person
    joins or will call (D-009)."""
    actions = _actions(tmp_path)
    claims = {each.name: every_language(each.claims.phrases) for each in actions}
    guard = with_ticket_claims(VoiceSettings(env="test")).guard
    any_action = any_action_claims(guard.claims)
    for made in actions:
        for tag in WORDINGS:
            for name, text in _lines_of(made, tag).items():
                verdict = check_claims(
                    text,
                    claims=claims,
                    any_action=any_action,
                    evidence=(),
                    settings=guard,
                    year=2026,
                )
                assert verdict == ClaimVerdict(claimed=(), passed=True), (made.name, tag, name)
                form = _form(text)
                for word in (*SEEN, *PROMISED):
                    assert _form(word) not in form, (made.name, tag, name, word)


def test_every_msa_line_is_msa_with_no_dialect_form(tmp_path: Path) -> None:
    """The MSA texts an MSA caller hears: each line, its values left out, holds no dialect form
    the library reads the caller's register by (`register_of`) and none of Ole5's Saudi forms,
    and differs from its Saudi line, so each was written for MSA."""
    forms = tuple(normalize_arabic(form) for form in SAUDI_FORMS)
    for made in _actions(tmp_path):
        saudi = _lines_of(made, "ar-SA")
        for name, text in _lines_of(made, "ar").items():
            words = _words(text)
            assert register_of(" ".join(words)) == "msa", (made.name, name)
            assert [w for w in words if w.startswith(forms)] == [], (made.name, name)
            assert text != saudi[name], (made.name, name)


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
        assert isinstance(read_back, ReadBack) and set(read_back.templates) == set(WORDINGS)
        for summary, question in read_back.templates.values():
            assert question.endswith(("?", "؟")) and not summary.endswith(("?", "؟"))
