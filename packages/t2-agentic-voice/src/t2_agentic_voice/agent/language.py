"""The reply language of each turn (plan 006, "What voice-first means here", item 8): the reply
follows the language the caller's turn was heard in, not the call's alone, so one call may hold
Saudi, MSA and English turns, each answered in its own.

- **Heard.** The language the turn's transcript names (a code, "ar" or "en", or the provider's
  name of it, "Arabic"); a call tells speech-to-text its language (D-066), so this is most often
  the call's.
- **Written.** The script of the turn's words overrules it when it plainly says otherwise:
  `SWITCH_WORDS` words or more in the other script, more than twice the words in the heard
  one's (the prototype switched only on three words in the other script, its D27). So an
  English question Whisper writes in Latin letters in an Arabic call is answered in English,
  while an Arabic sentence with English product terms in it ("VPN" and "Outlook" in a Saudi
  question) stays Arabic.
- **The tag.** That language is the agent's tag for it: the call's own when its language is
  the same (an `ar-SA` call stays `ar-SA`), else the first of the agent's tags in it, else the
  call's. Saudi Arabic and MSA share a code, so the register is not told by the tag: the prompt
  asks the model for the Saudi register unless the caller speaks MSA (agent/prompt.py).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.tts import LanguageTag

Code = Literal["ar", "en"]
# The fewest words in the other script that can switch a turn's language.
SWITCH_WORDS = 3
# An Arabic letter: hamza to ghain, feh to yeh (the tatweel left out), alef wasla to yeh barree.
_ARABIC_LETTER = re.compile("[\u0621-\u063a\u0641-\u064a\u0671-\u06d3]")
_LATIN_LETTER = re.compile("[A-Za-z]")


def code_of(tag: LanguageTag) -> Code:
    """The primary language of `tag`, which both Arabic tags share."""
    return "en" if tag == "en" else "ar"


def _heard(language: str | None) -> Code | None:
    """The code of a transcript's language, a code or a name of it in any case; None for
    another or none."""
    named = (language or "").casefold()
    if named.startswith("ar"):
        return "ar"
    if named.startswith("en"):
        return "en"
    return None


def _written(words: str, heard: Code | None) -> Code | None:
    """The language the script of `words` plainly says, when it is not `heard`."""
    arabic = latin = 0
    for word in words.split():
        if _ARABIC_LETTER.search(word):
            arabic += 1
        elif _LATIN_LETTER.search(word):
            latin += 1
    if heard != "en" and latin >= SWITCH_WORDS and latin > 2 * arabic:
        return "en"
    if heard != "ar" and arabic >= SWITCH_WORDS and arabic > 2 * latin:
        return "ar"
    return None


def reply_language(
    turn: TalkerTurn, *, call: LanguageTag, spoken: Sequence[LanguageTag]
) -> LanguageTag:
    """The tag the reply to `turn` is in, in a call held in `call` by an agent that speaks
    `spoken` (the module's docstring)."""
    heard = _heard(turn.language)
    code = _written(turn.words, heard) or heard or code_of(call)
    if code_of(call) == code:
        return call
    return next((tag for tag in spoken if code_of(tag) == code), call)
