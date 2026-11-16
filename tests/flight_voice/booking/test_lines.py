"""What the booking says (flight_voice/booking/lines.py), held to the lines' rules on its texts and
on the final lines a call hears, the read-back filled from a round trip and a one-way one: every
wording the agent reads (Saudi Arabic, MSA and English) covered; each read-back's summary naming
its own wording's parts, the trip's kind among them; no line but the closing question holding a
stop, wait, repeat, listening, yes or send word, and the closing question its send word; no
line holding a phrase the guard reads as a claim; `done` never saying the reference, and no line
said before there is a result saying a number; every MSA line MSA."""

from __future__ import annotations

import re
from typing import Final, Literal

import pytest
from flight_voice.booking import lines
from flight_voice.booking.draft import BOOK_TRIP, WORDINGS, BookingDraft
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.actions.spoken_lines import read_back_plan
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import primary_code
from t2_agentic_voice.domain.claims import (
    ClaimVerdict,
    any_action_claims,
    check_claims,
    every_language,
)
from t2_agentic_voice.domain.yes_words import PRESET_CONSENT
from t2_agentic_voice.languages import normalize_arabic, provider_text, register_of

from tests.flight_voice.booking.booking_support import (
    agent,
    airline,
    booking,
    booking_of,
    london,
    planned,
)

TAGS: Final[tuple[LanguageTag, ...]] = ("ar-SA", "ar", "en")
_SUFFIX: Final[dict[LanguageTag, str]] = {"ar-SA": "ar_sa", "ar": "ar", "en": "en"}
# Saudi forms no MSA line holds, as a word's start: tabi (want), al-heen (now), the future's
# b- (baHjiz, I'll book), sawwet (I made), raayiH (going).
SAUDI_FORMS: Final = ("تبي", "الحين", "بحجز", "سويت", "رايح", "ترجع")
_OTHERS: Final = (lines.DONE, lines.SENDING, lines.FAILED, lines.UNKNOWN, lines.DECLINED)


def _form(text: str) -> str:
    return f" {normalize_arabic(provider_text(text))} "


def _commands(line: str, code: Literal["ar", "en"]) -> list[str]:
    """The stop, wait, repeat and listening words of the agent, and the presets' yes and send
    words with the booking's own, that `line` holds as whole words."""
    words = agent(airline(), planned()).phrases.words(code)
    consent = PRESET_CONSENT[code]
    listed = (
        *words.stop,
        *words.wait,
        *words.repeat,
        *words.backchannel,
        *consent.yes,
        *consent.send,
        *lines.SEND_WORDS[code],
    )
    form = _form(re.sub(r"[{}]", " ", line))
    return [word for word in listed if _form(word) in form]


def _drafts() -> tuple[BookingDraft, ...]:
    flights = airline()
    trips = (london(), london(one_way=True, travelers=3, cabin="business"))
    return tuple(booking_of(flights, trip) for trip in trips)


def _heard(tag: LanguageTag) -> dict[str, str]:
    """Each line a call hears in `tag`, the read-back as filled from both trips."""
    made = booking(agent(airline(), planned()))
    heard: dict[str, str] = {}
    for n, draft in enumerate(_drafts()):
        reply: LanguageTag = "en" if tag == "en" else "ar-SA"
        plan = read_back_plan(made, draft, tool_call_id="t", tag=reply, wording=tag)
        heard[f"summary-{n}"] = plan.summary.text
        heard[f"question-{n}"] = plan.question.text
        heard[f"declined-{n}"] = plan.declined.text
        heard[f"sending-{n}"] = plan.sending.text
    for name, say in (("failed", lines.FAILED), ("unknown", lines.UNKNOWN)):
        heard[name] = say.for_language(tag)
    return heard


def test_every_text_covers_each_wording_the_agent_reads() -> None:
    made = booking(agent(airline(), planned()))
    assert {"read_back", "done", "claims", "sending", "failed", "unknown", "declined"} <= set(
        made.texts
    )
    for text in made.texts.values():
        keys = text.phrases if hasattr(text, "phrases") else text.templates
        assert set(keys) == set(TAGS)
    assert made.read_back.show_draft is False  # the caller only hears the agent (D-075)
    assert made.max_per_call == 1


@pytest.mark.parametrize("tag", TAGS)
def test_each_summary_names_its_own_wordings_parts_and_the_cabin(tag: LanguageTag) -> None:
    summary, question = lines.READ_BACK.for_language(tag)
    named = re.findall(r"{(\w+)}", summary)
    own = [f"{part}_{_SUFFIX[tag]}" for part in ("trip_kind", "route", "outbound", "return")]
    assert set(named) == {"cabin", f"party_{_SUFFIX[tag]}", f"total_{_SUFFIX[tag]}", *own}
    assert named.index(f"trip_kind_{_SUFFIX[tag]}") < named.index(f"route_{_SUFFIX[tag]}")
    assert "{" not in question
    assert set(WORDINGS) == set(_SUFFIX.values())


@pytest.mark.parametrize("tag", TAGS)
def test_only_the_closing_question_holds_a_word_the_caller_commands_with(tag: LanguageTag) -> None:
    code = primary_code(tag)
    texts = {"summary": lines.READ_BACK.for_language(tag)[0]}
    texts |= {f"line-{n}": say.for_language(tag) for n, say in enumerate(_OTHERS)}
    for name, text in {**texts, **_heard(tag)}.items():
        if name.startswith("question"):
            sends = [_form(word) for word in lines.SEND_WORDS[code]]
            assert any(send in _form(text) for send in sends), (tag, name)
            assert [w for w in _commands(text, code) if w not in lines.SEND_WORDS[code]] == []
        else:
            assert _commands(text, code) == [], (tag, name, _commands(text, code))


@pytest.mark.parametrize("tag", TAGS)
def test_no_line_holds_a_phrase_the_guard_reads_as_a_claim(tag: LanguageTag) -> None:
    claims = {BOOK_TRIP: every_language(lines.CLAIMS.phrases)}
    guard = VoiceSettings(env="test").guard
    texts = {f"line-{n}": say.for_language(tag) for n, say in enumerate(_OTHERS)}
    for name, text in {**texts, **_heard(tag)}.items():
        verdict = check_claims(
            text,
            claims=claims,
            any_action=any_action_claims(guard.claims),
            evidence=(),
            settings=guard,
            year=2026,
        )
        assert verdict == ClaimVerdict(claimed=(), passed=True), (tag, name)
        assert "\n" not in text and text.strip() == text, (tag, name)


def test_done_never_says_the_reference_and_no_line_before_a_result_says_a_number() -> None:
    assert lines.DONE.placeholders == {
        f"{part}_{suffix}" for part in ("city", "when") for suffix in WORDINGS
    }
    for say in _OTHERS[1:]:
        assert say.placeholders == set()
        assert not any(re.search(r"\d", text) for text in say.templates.values())


def test_every_msa_line_is_msa_and_differs_from_its_saudi_line() -> None:
    forms = tuple(normalize_arabic(form) for form in SAUDI_FORMS)
    msa, saudi = _heard("ar"), _heard("ar-SA")
    msa |= {f"line-{n}": say.for_language("ar") for n, say in enumerate(_OTHERS)}
    saudi |= {f"line-{n}": say.for_language("ar-SA") for n, say in enumerate(_OTHERS)}
    for name, text in msa.items():
        words = [normalize_arabic(w.strip("،؛؟.,!?:")) for w in re.sub(r"{\w+}", " ", text).split()]
        assert register_of(" ".join(words)) == "msa", name
        assert [w for w in words if w.startswith(forms)] == [], name
        assert text != saudi[name], name
