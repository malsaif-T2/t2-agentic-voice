"""The characters a spoken phrase may hold that a reader does not see, and the text a
text-to-speech provider is sent for a phrase (plan 003's decision log).

Text pasted from a word processor, a web page or a chat app often carries such characters: a
no-break space between two words, a joiner or a direction mark beside Arabic letters. A fixed
phrase (a greeting, the echo's frame, a notice, a spoken form of the pronunciation map) may hold
seven of them, which change nothing a listener hears: the no-break spaces U+00A0 and U+202F, the
joiners U+200C and U+200D, and the direction marks U+200E, U+200F and U+061C. Every other control
or format character, line or paragraph separator and lone surrogate, and every space but U+0020
and the no-break spaces, is refused when the agent is declared (domain/declaration.py). A
caption shows a phrase as written; a provider is sent `provider_text`'s form of it, which holds
none of the seven. Public through the `languages` facade, beside the clause splitter.
"""

from __future__ import annotations

import unicodedata

# Sent as a space: NO-BREAK SPACE, NARROW NO-BREAK SPACE.
_NO_BREAK = "\u00a0\u202f"
# Dropped from what a provider is sent: ZERO WIDTH NON-JOINER, ZERO WIDTH JOINER,
# LEFT-TO-RIGHT MARK, RIGHT-TO-LEFT MARK, ARABIC LETTER MARK.
_UNSEEN = "\u200c\u200d\u200e\u200f\u061c"
_SENT = str.maketrans(_NO_BREAK, " " * len(_NO_BREAK), _UNSEEN)
# The general categories a phrase holds no character of, but U+0020 and the seven above:
# control (Cc), format (Cf) and surrogate (Cs), and the space (Zs), line (Zl) and paragraph (Zp)
# separators.
_REFUSED = frozenset({"Cc", "Cf", "Cs", "Zs", "Zl", "Zp"})
_KEPT = frozenset(" " + _NO_BREAK + _UNSEEN)


def holds_refused_character(text: str) -> bool:
    """Whether `text` holds a character a spoken phrase may not (above)."""
    return any(char not in _KEPT and unicodedata.category(char) in _REFUSED for char in text)


def provider_text(text: str) -> str:
    """`text` as a text-to-speech provider is sent it: each no-break space a space, each joiner
    and direction mark dropped, every other character as written. The phrase cache sends only
    this text, after the pronunciation map (adapters/phrase_cache.py)."""
    return text.translate(_SENT)
