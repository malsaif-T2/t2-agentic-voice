"""The canonical Arabic normalizer: one spelling of a text, so two texts can be compared.

Ported from the prototype's normalizer (D-010), rule for rule: plan 002's progress log names
its source file and lines, and the characterization table in the library's tests holds what it
makes of each case. Only the letter forms the prototype folded are folded (the spelling guide
of plan 002, Q8): alef wasla, Farsi yeh, keheh and a lone hamza are kept. Public through the
`languages` facade (D-021).
"""

from __future__ import annotations

import re

# The marks removed before anything else, the prototype's set: the honorific signs and the
# small high letters above the text (U+0610 to U+061A); the harakat, tanween, shadda, sukun and
# the combining hamza and madda forms (U+064B to U+065F); the superscript alef (U+0670); the
# Quranic annotation marks (U+06D6 to U+06ED); and the tatweel (U+0640).
ARABIC_MARKS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")

# Anything that is neither a word character nor a space: punctuation in every script, symbols
# and emoji, and the format characters (the bidirectional marks, the zero-width joiners), each
# read as a space.
_NOT_WORD = re.compile(r"[^\w\s]")

# The letter forms folded, as the prototype folds them.
_FOLD = str.maketrans(
    {
        "\u0623": "\u0627",  # alef with hamza above -> alef
        "\u0625": "\u0627",  # alef with hamza below -> alef
        "\u0622": "\u0627",  # alef with madda above -> alef
        "\u0629": "\u0647",  # teh marbuta -> heh
        "\u0649": "\u064a",  # alef maksura -> yeh
        "\u0624": "\u0648",  # waw with hamza above -> waw
        "\u0626": "\u064a",  # yeh with hamza above -> yeh
    }
)


def normalize_arabic(text: str) -> str:
    """`text` in its canonical form for comparison: no diacritics and no tatweel; the alef,
    hamza, teh marbuta and alef maksura forms folded; Latin letters in lower case; an
    underscore, punctuation, symbols and emoji read as spaces; runs of space made one, and the
    ends trimmed. Digits are kept as written (`normalize_digits` reads them)."""
    text = ARABIC_MARKS.sub("", text).translate(_FOLD).lower().replace("_", " ")
    return " ".join(_NOT_WORD.sub(" ", text).split())
