"""The declaration of a use case (the design's 4.3 and 5.2; plan 003, Q3 and Q5): an agent with a
name, its languages, each built from its preset with the team's greeting, the echo's frame and
the notices, and its pronunciation map; anything it cannot run with a ConfigurationError naming
the field, with a FIX line (the design's 4.2)."""

from __future__ import annotations

import copy
import pickle
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import NOTICE_KINDS, Language, VoiceAgent

SAUDI = Language.saudi_arabic(greeting="هلا! وش أقدر أساعدك فيه؟")
ENGLISH = Language.english(greeting="Hi! Which branch can I help you with?")
# What pasted text carries unseen, which a phrase may hold (written with `chr`, so this file
# holds none of them): the no-break spaces, the joiners and the direction marks.
NBSP, NARROW_NBSP = chr(0x00A0), chr(0x202F)
ZWNJ, ZWJ = chr(0x200C), chr(0x200D)
LRM, RLM, ALM = chr(0x200E), chr(0x200F), chr(0x061C)
# Each preset's notices, as the owner's register for the fixed phrases has them (Q5): Saudi for
# ar-SA, Modern Standard Arabic for ar, and English.
NOTICES = {
    "ar-SA": {
        "busy": "الخطوط مشغولة الحين، حاول مرة ثانية بعد شوي.",
        "error": "صار عندنا خلل بسيط، تكلم مرة ثانية لو سمحت.",
        "cut_off": "معليش، انقطع الجواب. تبيه من البداية؟",
        "ended": "انتهت المكالمة، يعطيك العافية.",
    },
    "ar": {
        "busy": "الخطوط مشغولة الآن، يرجى المحاولة مرة أخرى بعد قليل.",
        "error": "حدث خلل لدينا، هل يمكنك إعادة ما قلته؟",
        "cut_off": "عذرا، انقطعت الإجابة. هل تريدها من البداية؟",
        "ended": "انتهت المكالمة، شكرا لاتصالك.",
    },
    "en": {
        "busy": "All our lines are busy right now. Please try again in a little while.",
        "error": "Something went wrong on our side. Could you say that again?",
        "cut_off": "Sorry, that answer got cut off. Do you want it from the start?",
        "ended": "The call has ended. Thank you for calling.",
    },
}


def test_each_preset_has_its_tag_and_the_frame_the_owner_chose() -> None:
    """Q3's frames: «سمعتك تقول: …» for both Arabic presets, "I heard: …" for English."""
    msa = Language.arabic(greeting="مرحبا بك")
    assert [(lang.tag, lang.echo_frame, lang.primary) for lang in (SAUDI, msa, ENGLISH)] == [
        ("ar-SA", "سمعتك تقول:", "ar"),
        ("ar", "سمعتك تقول:", "ar"),
        ("en", "I heard:", "en"),
    ]
    assert ENGLISH.greeting == "Hi! Which branch can I help you with?"


def test_each_preset_has_a_text_for_every_notice_in_its_register() -> None:
    msa = Language.arabic(greeting="مرحبا بك")
    for language in (SAUDI, msa, ENGLISH):
        assert dict(language.notices) == NOTICES[language.tag], language.tag
        assert tuple(language.notices) == NOTICE_KINDS == ("busy", "error", "cut_off", "ended")
    assert all(len(text) <= 200 for texts in NOTICES.values() for text in texts.values())


def test_a_teams_notices_replace_the_kinds_they_name() -> None:
    english = Language.english(greeting="Hello there.", notices={"ended": "Bye for now."})
    assert dict(english.notices) == NOTICES["en"] | {"ended": "Bye for now."}
    saudi = Language.saudi_arabic(greeting="هلا", notices={"error": "صار خلل"})
    assert saudi.notices["error"] == "صار خلل"
    assert saudi.notices["busy"] == NOTICES["ar-SA"]["busy"]
    assert Language.english(greeting="Hello there.", notices={}) == ENGLISH.model_copy(
        update={"greeting": "Hello there."}
    )


def test_a_languages_notices_are_read_only_and_dump_as_a_plain_object() -> None:
    with pytest.raises(TypeError):
        ENGLISH.notices["busy"] = "changed"  # type: ignore[index]
    dumped = ENGLISH.model_dump()
    assert dumped["notices"] == NOTICES["en"] and isinstance(dumped["notices"], dict)
    assert Language.model_validate(dumped) == ENGLISH
    again = pickle.loads(pickle.dumps(ENGLISH))  # noqa: S301 - loads only bytes it dumped
    assert copy.deepcopy(ENGLISH) == ENGLISH == again


@pytest.mark.parametrize(
    "greeting",
    [
        "",
        "   ",
        NBSP * 3,  # spaces only, if no-break ones
        RLM,  # a mark alone says nothing
        "Hi\nthere",
        "Hi\x00",
        f"Hi{chr(0x3000)}there",  # IDEOGRAPHIC SPACE
        f"Hi{chr(0x2028)}there",  # LINE SEPARATOR
        f"{chr(0xFEFF)}Hi there",  # a byte order mark
        f"Hi there{chr(0xD800)}",  # a lone surrogate
        3,
    ],
)
def test_a_greeting_says_something_on_one_line(greeting: Any) -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        Language.english(greeting=greeting)
    assert raised.value.details == {"field": "greeting"}


def test_a_phrase_pasted_with_no_break_spaces_and_marks_is_kept_as_written() -> None:
    """A Saudi greeting, a notice and a spoken form pasted from a phone or a document: captions
    show each as written; the provider is sent each without them (domain/text/invisible.py)."""
    pasted = RLM + SAUDI.greeting.replace(" ", NBSP, 1)
    saudi = Language.saudi_arabic(greeting=pasted, notices={"error": f"{LRM}صار خلل{ALM}"})
    assert (saudi.greeting, saudi.notices["error"]) == (pasted, f"{LRM}صار خلل{ALM}")
    said = {f"L{ZWNJ}T-": {"ar": f"إل{NARROW_NBSP}تي", "en": f"L{ZWJ}T"}}
    agent = VoiceAgent(name="helpdesk", languages=[saudi], pronounce=said)
    assert {form: dict(each) for form, each in agent.pronounce.items()} == said


def test_a_refused_character_is_named_as_the_rule_says_never_as_a_line_break() -> None:
    with pytest.raises(ConfigurationError) as raised:
        Language.english(greeting=f"Hi{chr(0x3000)}there")
    message = str(raised.value)
    assert (
        "holds a control or format character, a line or paragraph separator, a lone surrogate "
        "or a space other than U+0020; of these, a phrase may hold only the no-break spaces "
        "U+00A0 and U+202F, the joiners U+200C and U+200D and the direction marks U+200E, "
        "U+200F and U+061C. FIX: give `greeting` the words the agent opens a call with, on one "
        "line of plain text (type again a text pasted from a document or a chat)."
    ) in message
    assert "line break" not in message
    with pytest.raises(ConfigurationError, match="says nothing"):
        Language.english(greeting=RLM + NBSP)


@pytest.mark.parametrize(
    "notices",
    [
        {"error": ""},
        {"ended": "Bye\nnow"},
        {"ended": f"Bye{chr(0x2029)}now"},  # PARAGRAPH SEPARATOR
        {"farewell": "Bye now."},  # not a kind of notice
        {"busy": 3},
        [("error", "Bye now.")],  # not a map
    ],
)
def test_a_teams_notice_says_something_on_one_line_for_a_kind_there_is(notices: Any) -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        Language.english(greeting="Hello there.", notices=notices)
    assert raised.value.details == {"field": "notices"}


def test_a_language_built_without_its_preset_still_needs_every_notice() -> None:
    """Its FIX asks for all four, which no preset fills in on this path."""
    fields = ENGLISH.model_dump() | {"notices": {"busy": "Busy now."}}
    with pytest.raises(ConfigurationError, match="no text for error, cut_off or ended") as raised:
        Language.model_validate(fields)
    assert raised.value.details == {"field": "notices"}
    assert "a text for each of busy, error, cut_off and ended" in str(raised.value)
    assert "keeps the preset's text" not in str(raised.value)
    with pytest.raises(ConfigurationError, match="no text for busy, error, cut_off or ended"):
        Language.model_validate(fields | {"notices": {}})


def test_a_presets_notices_fix_says_a_kind_left_out_keeps_its_text() -> None:
    with pytest.raises(ConfigurationError) as raised:
        Language.english(greeting="Hello there.", notices={"error": ""})
    assert raised.value.details == {"field": "notices"}
    assert "with a preset, a kind it leaves out keeps the preset's text" in str(raised.value)


def test_a_language_is_frozen_and_takes_no_other_field() -> None:
    with pytest.raises(ValidationError):
        ENGLISH.greeting = "Hello"  # type: ignore[misc]
    refused: list[tuple[object, str | None]] = [
        (ENGLISH.model_dump() | {"tag": "fr"}, "tag"),
        ({"tag": "en", "greeting": "Hello"}, "echo_frame"),
        (ENGLISH.model_dump() | {"voice": "troy"}, "voice"),
        ("en", None),  # not a language at all
    ]
    for value, field in refused:
        with pytest.raises(ConfigurationError, match="FIX: ") as raised:
            Language.model_validate(value)
        assert raised.value.details == {"field": field}, value


def test_an_agent_has_a_name_and_its_languages_the_first_a_calls_by_default() -> None:
    agent = VoiceAgent(name="branch-helper", languages=[SAUDI, ENGLISH])
    assert (agent.name, agent.languages, dict(agent.pronounce)) == (
        "branch-helper",
        (SAUDI, ENGLISH),
        {},
    )
    assert agent.languages[0].tag == "ar-SA"
    with pytest.raises(ValidationError):
        agent.name = "other"  # type: ignore[misc]


def test_an_agent_keeps_its_pronunciations_read_only() -> None:
    """The design's 4.3 map: each written form to how `ar` and `en` say it."""
    said = {"LT-": {"ar": "إل تي", "en": "L T"}}
    agent = VoiceAgent(name="helpdesk", languages=[SAUDI, ENGLISH], pronounce=said)
    assert {form: dict(each) for form, each in agent.pronounce.items()} == said
    with pytest.raises(TypeError):
        agent.pronounce["LT-"]["en"] = "changed"  # type: ignore[index]
    said["LT-"]["en"] = "changed later"
    assert agent.pronounce["LT-"]["en"] == "L T"  # a copy, not the team's dict
    assert VoiceAgent.model_validate(agent.model_dump()) == agent
    assert agent.model_dump()["pronounce"] == {"LT-": {"ar": "إل تي", "en": "L T"}}


@pytest.mark.parametrize(
    ("requested", "locale", "tag"),
    [
        (None, "ar-SA", "ar-SA"),  # the locale's exact tag
        (None, "AR-sa", "ar-SA"),  # in any case
        (None, "ar", "ar-SA"),  # its primary subtag: the agent has no `ar`
        (None, "en-US", "en"),
        (None, "fr", "ar-SA"),  # a language the agent does not speak: its first
        (None, None, "ar-SA"),  # no locale (DevIdentity's caller): its first
        ("en", "ar-SA", "en"),  # the caller's pick comes before the locale
        ("ar", "en-US", "en"),  # a pick the agent does not speak: the locale
    ],
)
def test_a_calls_language_is_the_callers_pick_then_the_locale_then_the_first(
    requested: LanguageTag | None, locale: str | None, tag: str
) -> None:
    agent = VoiceAgent(name="branch-helper", languages=[SAUDI, ENGLISH])
    assert agent.call_language(requested, locale=locale).tag == tag


def test_a_locale_takes_its_exact_tag_before_another_of_its_language() -> None:
    msa = Language.arabic(greeting="مرحبا بك")
    agent = VoiceAgent(name="branch-helper", languages=[ENGLISH, msa, SAUDI])
    picked = [agent.call_language(None, locale=locale) for locale in ("ar-SA", "ar-EG", "ar")]
    assert picked == [SAUDI, msa, msa]
    assert agent.call_language("ar-SA", locale="en") is SAUDI


@pytest.mark.parametrize(
    ("values", "field"),
    [
        ({"name": "Branch Helper", "languages": [ENGLISH]}, "name"),
        ({"name": "../var", "languages": [ENGLISH]}, "name"),
        ({"name": "9lives", "languages": [ENGLISH]}, "name"),
        ({"name": "a" * 65, "languages": [ENGLISH]}, "name"),
        ({"name": 3, "languages": [ENGLISH]}, "name"),
        ({"languages": [ENGLISH]}, "name"),
        ({"name": "helper", "languages": []}, "languages"),
        (
            {"name": "helper", "languages": [ENGLISH, Language.english(greeting="Hello")]},
            "languages",
        ),
        ({"name": "helper"}, "languages"),
        ({"name": "helper", "languages": "en"}, "languages"),
        ({"name": "helper", "languages": ["en"]}, "languages"),  # not a preset
        ({"name": "helper", "languages": [{"tag": "en"}]}, "greeting"),  # its own field
        ({"name": "helper", "languages": [ENGLISH], "actions": []}, "actions"),
        ({"name": "helper", "languages": [ENGLISH], "pronounce": ["LT-"]}, "pronounce"),
    ],
)
def test_an_agent_it_cannot_run_is_a_configuration_error_with_a_fix(
    values: dict[str, Any], field: str
) -> None:
    """Its name names a folder under `storage.var_dir`, so nothing but a lowercase word."""
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        VoiceAgent.model_validate(values)
    assert raised.value.details == {"field": field}


@pytest.mark.parametrize("name", ["nul", "con", "prn", "aux", "com1", "com9", "lpt1", "lpt9"])
def test_an_agent_is_not_named_like_a_windows_device(name: str) -> None:
    """Windows keeps these names for its devices: on this machine, a file under a folder named
    `nul` cannot be written (plan 003's review)."""
    with pytest.raises(ConfigurationError, match="Windows keeps") as raised:
        VoiceAgent(name=name, languages=[ENGLISH])
    assert raised.value.details == {"field": "name"}
    assert VoiceAgent(name=f"{name}-helper", languages=[ENGLISH]).name == f"{name}-helper"


@pytest.mark.parametrize(
    "pronounce",
    [
        {"LT-": {"ar-SA": "إل تي"}},  # a tag, not the primary code
        {"LT-": {"fr": "L T"}},
        {"LT-": {}},  # says how no language says it
        {"LT-": {"en": ""}},
        {"LT-": {"en": "L\nT"}},
        {"LT-": {"en": f"L{chr(0x2003)}T"}},  # EM SPACE
        {f"LT-{NBSP}": {"en": "L T"}},  # a no-break space at its end
        {"": {"en": "L T"}},
        {" LT-": {"en": "L T"}},  # never stands as whole words
        {"LT-\n": {"en": "L T"}},
        {"LT-": "L T"},
    ],
)
def test_a_pronunciation_names_ar_or_en_and_says_something(pronounce: Any) -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        VoiceAgent(name="helpdesk", languages=[ENGLISH], pronounce=pronounce)
    assert raised.value.details == {"field": "pronounce"}


@pytest.mark.parametrize(
    "build",
    [
        lambda: Language.english(greeting="Secret greeting\nline"),
        lambda: Language.english(greeting="Hi", notices={"error": "Secret notice\x00"}),
        lambda: VoiceAgent(name="Secret Name", languages=[ENGLISH]),
        lambda: VoiceAgent(name="x", languages=[ENGLISH], pronounce={"x": {"en": "Secret\n"}}),
    ],
)
def test_an_error_never_repeats_the_value_it_refused(build: Callable[[], object]) -> None:
    with pytest.raises(ConfigurationError) as raised:
        build()
    assert "Secret" not in str(raised.value)
    assert raised.value.__context__ is None and raised.value.__cause__ is None
