"""Digit normalization: every way a digit is written or said, read as the digits 0 to 9.

Arabic-Indic and Persian digits are read as ASCII digits, as the prototype's scorer read them
(D-010); digits said one word each, in Arabic or in English, count as those digits, as the
spelling guide of plan 002 rules (Q8), where the prototype kept them as words. Numbers said as
number words (twenty-one, in either language) are not read: that needs a table of spoken
numbers, which comes with them. Public through the `languages` facade (D-021).
"""

from __future__ import annotations

import re

from t2_agentic_voice.domain.text.arabic import _MARKS, normalize_arabic

# Arabic-Indic digits (U+0660 to U+0669) and Persian, or Extended Arabic-Indic, digits (U+06F0
# to U+06F9), each read as its ASCII digit.
_DIGIT_CHARACTERS = str.maketrans(
    {chr(0x0660 + digit): str(digit) for digit in range(10)}
    | {chr(0x06F0 + digit): str(digit) for digit in range(10)}
)

# Each digit's name, as `normalize_arabic` writes it, so a name matches in any case and in every
# letter form the normalizer folds (teh marbuta or heh, alef with or without hamza). The Arabic
# names are the forms a digit is read by, one at a time; the short forms ("khams", "sab'",
# "tis'", "sitt") are left out, since each is also another everyday word.
_DIGIT_NAMES: dict[str, str] = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "\u0635\u0641\u0631": "0",  # sifr: sad, feh, reh
    "\u0648\u0627\u062d\u062f": "1",  # wahid: waw, alef, hah, dal
    "\u0627\u062b\u0646\u064a\u0646": "2",  # ithnayn: alef, theh, noon, yeh, noon
    "\u0627\u062b\u0646\u0627\u0646": "2",  # ithnan: alef, theh, noon, alef, noon
    "\u062b\u0644\u0627\u062b\u0647": "3",  # thalatha: theh, lam, alef, theh, heh
    "\u0627\u0631\u0628\u0639\u0647": "4",  # arba'a: alef, reh, beh, ain, heh
    "\u062e\u0645\u0633\u0647": "5",  # khamsa: khah, meem, seen, heh
    "\u0633\u062a\u0647": "6",  # sitta: seen, teh, heh
    "\u0633\u0628\u0639\u0647": "7",  # sab'a: seen, beh, ain, heh
    "\u062b\u0645\u0627\u0646\u064a\u0647": "8",  # thamaniya: theh, meem, alef, noon, yeh, heh
    "\u062a\u0633\u0639\u0647": "9",  # tis'a: teh, seen, ain, heh
}

_ASCII_DIGITS = frozenset("0123456789")
# A word: its word characters, and the marks `normalize_arabic` removes (harakat, tatweel), which
# are not word characters, so a digit's name written with its harakat is read whole.
_WORD = re.compile(rf"(?:\w|{_MARKS.pattern})+")


def _digit(word: str) -> str | None:
    """The digit `word` writes or names on its own, else None (a longer number, or a word)."""
    if word in _ASCII_DIGITS:
        return word
    return _DIGIT_NAMES.get(normalize_arabic(word))


def normalize_digits(text: str) -> str:
    """`text` with each digit as an ASCII digit: Arabic-Indic and Persian (Extended
    Arabic-Indic) digits become 0 to 9 wherever they are, and a digit spelled out as one word,
    in Arabic or in English, becomes its digit. Digits said or written one at a time, with only
    spaces between them, are one number: "five seven", its Arabic names, and "5 7" all read
    "57", while "45 21" stays two numbers. Everything else is left as it is, so the names are found
    as whole words in any text; after `normalize_arabic`, whatever punctuation stood between
    them is a space too."""
    text = text.translate(_DIGIT_CHARACTERS)
    pieces: list[str] = []
    done = 0  # where the text not yet copied to `pieces` starts
    run: list[str] = []  # the digits of the run being read
    start = end = 0  # where that run starts and ends in `text`
    for word in _WORD.finditer(text):
        digit = _digit(word.group())
        if digit is not None and run and text[end : word.start()].isspace():
            run.append(digit)
            end = word.end()
            continue
        if run:
            pieces += [text[done:start], "".join(run)]
            done, run = end, []
        if digit is not None:
            run = [digit]
            start, end = word.span()
    if run:
        pieces += [text[done:start], "".join(run)]
        done = end
    pieces.append(text[done:])
    return "".join(pieces)
