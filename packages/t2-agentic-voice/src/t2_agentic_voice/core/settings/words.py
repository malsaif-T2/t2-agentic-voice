"""The `words` group: the words a team adds, in its settings, to the lists its agent's
interruption rule reads (the design's 7.6 and 4.3; plan 005), for each language by its primary
code (`ar` for both Arabic presets, `en`): its stop words, the words that ask it to pause, its
repeat words, its listening sounds (`backchannel`) and its no words. Each is added to the
language preset's list and the declaration's (`VoiceAgent(phrases=...)`, domain/words.py), so an
app sets its own additions without code; none by default. `yes` and `send` are the yes rule's
(domain/yes_words.py), added to the presets' and to an action's own send words. And the product
terms added to the declaration's vocabulary (`VoiceAgent(vocabulary=...)`), which becomes the
Whisper prompt (plan 006), in any language: none by default.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field

from t2_agentic_voice.core.settings.base import FROZEN, PLAIN, Group

# A language's primary code, which both Arabic presets share: what a word list is keyed by.
LanguageCode = Literal["ar", "en"]
# One word or phrase, as a transcript would hold it.
_Word = Annotated[str, Field(min_length=1, max_length=64)]
# One product term, as a speaker says it and a transcript should write it ("VPN", "Outlook").
_Term = Annotated[str, Field(min_length=1, max_length=64)]
# A list of words for each language, by its code: read-only once loaded.
WordLists = Annotated[Mapping[LanguageCode, tuple[_Word, ...]], FROZEN, PLAIN]
_AS = 'as a JSON object from a language\'s code (ar, en) to a list: {"ar": ["..."]}'


def primary_code(tag: str) -> LanguageCode:
    """The primary code of the language tag `tag` (a `LanguageTag`, or a speech port's tag as
    a string): `en` for English, `ar` for both Arabic tags."""
    return "en" if tag == "en" else "ar"


def _additions(what: str) -> Any:
    """A word list's field: none by default, read-only once loaded."""
    return Field(
        default_factory=dict,
        validate_default=True,
        description=f"Words added to each language's {what}, {_AS}. A value replaces the map.",
    )


class WordSettings(Group):
    """Words: what a team adds to each language's lists, which the interruption rule reads."""

    stop: WordLists = _additions("stop words, which stop the agent at once")
    wait: WordLists = _additions("words asking the agent to pause, which stop it as a stop word")
    repeat: WordLists = _additions(
        "repeat words, which stop the agent and say its last reply again"
    )
    backchannel: WordLists = _additions("listening sounds, after which the agent goes on")
    no: WordLists = _additions("no words, which a short output never holds")
    yes: WordLists = _additions("yes words, which the yes rule reads")
    send: WordLists = _additions(
        "send words, which a yes over the closing question needs, and which a yes over any "
        "reply's question may be (interruptions.answer_yes_over_question)"
    )
    vocabulary: tuple[_Term, ...] = Field(
        default=(),
        description=(
            "Product terms added to the declaration's vocabulary, which becomes the Whisper "
            'prompt, as a JSON list: ["VPN", "Outlook"]. A value replaces the list.'
        ),
    )
