"""What the tests of Ole5's fixed lines share (plan 006, "What voice-first means here", item 6):
the words a caller commands the agent with, so a test can show that no fixed line's echo would
be heard as one."""

from __future__ import annotations

from typing import Literal

from t2_agentic_voice import VoiceAgent
from t2_agentic_voice.languages import normalize_arabic, provider_text

# The yes and send words, the prototype's (its `voice/rules.py`, YES and SUBMIT, read only:
# D-010), which the library's presets do not list yet (the yes rule's): a fixed line holds
# none, so its echo is never heard as a yes.
YES_AND_SEND = {
    "ar": (
        "نعم",
        "ايه",
        "اي",
        "ايوه",
        "ايوا",
        "اكيد",
        "موافق",
        "ارسل",
        "ارسلها",
        "ارسله",
        "ارسلي",
        "ارسلوها",
        "قدم",
        "قدمها",
        "قدمه",
        "افتحها",
        "افتح التذكره",
        "سجلها",
        "اعتمدها",
    ),
    "en": (
        "naam",
        "aywa",
        "yes",
        "yeah",
        "yep",
        "sure",
        "of course",
        "submit",
        "send",
        "confirm",
        "create",
        "go ahead",
    ),
}


def held(line: str, code: Literal["ar", "en"], talker: VoiceAgent) -> list[str]:
    """The words of the agent's stop, wait, repeat and listening lists, and the yes and send
    words, that `line` holds as whole words, compared in the interruption rule's form."""
    words = talker.phrases.words(code)
    listed = [*words.stop, *words.wait, *words.repeat, *words.backchannel, *YES_AND_SEND[code]]
    form = f" {normalize_arabic(provider_text(line))} "
    return [word for word in listed if f" {normalize_arabic(provider_text(word))} " in form]
