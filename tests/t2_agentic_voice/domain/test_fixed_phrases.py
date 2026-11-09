"""The fixed phrases (domain/fixed_phrases.py): what a call of an agent speaks as written, which
the phrase cache has at hand from the runtime's start, each naming which of its language's texts
it is."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass

import pytest
from t2_agentic_voice.domain.declaration import SPOKEN_NOTICES, Language, VoiceAgent
from t2_agentic_voice.domain.fixed_phrases import FixedPhrase, fixed_phrases

SAUDI = Language.saudi_arabic(greeting="هلا! وش أقدر أساعدك فيه؟")
ENGLISH = Language.english(greeting="Hi! Which branch can I help you with?")


def test_the_fixed_phrases_are_each_languages_greeting_frame_and_spoken_notices() -> None:
    """What the phrase cache declares: `busy` comes at join, before a call, so it is not one."""
    agent = VoiceAgent(name="branch-helper", languages=[SAUDI, ENGLISH])
    assert SPOKEN_NOTICES == ("error", "cut_off", "ended")
    said = [(phrase.kind, phrase.text, phrase.language) for phrase in fixed_phrases(agent)]
    assert said == [
        ("greeting", SAUDI.greeting, "ar-SA"),
        ("echo_frame", "سمعتك تقول:", "ar-SA"),
        ("notices.error", SAUDI.notices["error"], "ar-SA"),
        ("notices.cut_off", SAUDI.notices["cut_off"], "ar-SA"),
        ("notices.ended", SAUDI.notices["ended"], "ar-SA"),
        ("greeting", ENGLISH.greeting, "en"),
        ("echo_frame", "I heard:", "en"),
        ("notices.error", ENGLISH.notices["error"], "en"),
        ("notices.cut_off", ENGLISH.notices["cut_off"], "en"),
        ("notices.ended", ENGLISH.notices["ended"], "en"),
    ]
    assert ENGLISH.notices["busy"] not in {phrase.text for phrase in fixed_phrases(agent)}


def test_a_fixed_phrase_is_frozen() -> None:
    phrase = fixed_phrases(VoiceAgent(name="helper", languages=[ENGLISH]))[0]
    assert phrase == FixedPhrase(text=ENGLISH.greeting, language="en", kind="greeting")
    with pytest.raises(FrozenInstanceError):
        phrase.text = "changed"  # type: ignore[misc]


@dataclass(frozen=True)
class MadeUpTool:
    """The smallest tool shape the declaration reads (`DeclaredTool`)."""

    name: str
    description: str = "Search the help articles."
    progress: str | None = None


def test_each_progress_line_a_tool_names_is_a_fixed_phrase_in_every_language() -> None:
    """Plan 006: declared with the others, so the phrase cache renders each once; a line no
    tool names is never spoken, so it is not declared, and two tools naming one line declare
    it once."""
    saudi = Language.saudi_arabic(
        greeting=SAUDI.greeting, progress={"searching": "ثواني أشيك لك", "unused": "ما تنقال"}
    )
    english = Language.english(
        greeting=ENGLISH.greeting,
        progress={"searching": "Checking that for you.", "unused": "Never said."},
    )
    tools = [
        MadeUpTool("search_help", progress="searching"),
        MadeUpTool("search_more", progress="searching"),
        MadeUpTool("plain"),
    ]
    agent = VoiceAgent(name="branch-helper", languages=[saudi, english], tools=tools)
    progress = [phrase for phrase in fixed_phrases(agent) if phrase.kind == "progress"]
    assert progress == [
        FixedPhrase(text="ثواني أشيك لك", language="ar-SA", kind="progress", key="searching"),
        FixedPhrase(text="Checking that for you.", language="en", kind="progress", key="searching"),
    ]
    others = [phrase for phrase in fixed_phrases(agent) if phrase.kind != "progress"]
    assert all(phrase.key is None for phrase in others) and len(others) == 10
