"""Numbers and IDs, spoken in Arabic and English (the design's 3.1 and 5.1). Public through the
`languages` facade.

A number is said through num2words (the cardinals; MSA forms in Arabic, which num2words gives),
behind these functions alone: only `domain` imports num2words (`[[owners]]`). An ID is read
digit by digit from the library's own table, never through num2words. In a text, a run of digits
is an ID when it has five digits or more, starts with a zero, or follows a cue that names a
number's last digits, in Arabic or in English; any other run is a number (plan 003's decision
log). ASCII and Arabic-Indic digits are both read, and so are the Persian (Extended
Arabic-Indic) digits `normalize_digits` reads.

What num2words writes is shaped for speech, since each clause is one request
(domain/text/clauses.py): the commas of its English thousands ("one thousand, two hundred")
are dropped, so the splitter never cuts a number, and the Arabic "and" it writes as a word of
its own is joined to the word after it, as Arabic writes it. Only whole numbers reach
num2words, whose decimals read the wrong fraction (plan 003, step 4), and one call at a time,
since its converters keep each call's state on one shared object.
"""

from __future__ import annotations

import re
import threading

from num2words import num2words

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.text.digits import _DIGIT_CHARACTERS

# Each digit's name, 0 to 9, read one at a time in an ID: in Arabic the MSA forms num2words
# gives a number of one digit.
_DIGIT_WORDS: dict[str, tuple[str, ...]] = {
    "ar": (
        "\u0635\u0641\u0631",  # sifr: sad, feh, reh
        "\u0648\u0627\u062d\u062f",  # wahid: waw, alef, hah, dal
        "\u0627\u062b\u0646\u0627\u0646",  # ithnan: alef, theh, noon, alef, noon
        "\u062b\u0644\u0627\u062b\u0629",  # thalatha: theh, lam, alef, theh, teh marbuta
        "\u0623\u0631\u0628\u0639\u0629",  # arba'a: alef with hamza, reh, beh, ain, teh marbuta
        "\u062e\u0645\u0633\u0629",  # khamsa: khah, meem, seen, teh marbuta
        "\u0633\u062a\u0629",  # sitta: seen, teh, teh marbuta
        "\u0633\u0628\u0639\u0629",  # sab'a: seen, beh, ain, teh marbuta
        "\u062b\u0645\u0627\u0646\u064a\u0629",  # thamaniya: theh, meem, alef, noon, yeh, teh m.
        "\u062a\u0633\u0639\u0629",  # tis'a: teh, seen, ain, teh marbuta
    ),
    "en": ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"),
}

# A digit as a text may write it: ASCII, Arabic-Indic (U+0660 to U+0669) or Persian (U+06F0 to
# U+06F9).
_DIGIT = "[0-9\u0660-\u0669\u06f0-\u06f9]"
# The cues that name a number's last digits (plan 003's decision log), each standing as whole
# words: "ending in", in any case; and in Arabic "akhiruha" and "yantahi bi" (its beh with or
# without a tatweel), either one after "wa" or "fa" or none.
_ENDING_IN = r"(?i:ending\s+in)"
_AKHIRUHA = "\u0622\u062e\u0631\u0647\u0627"  # alef with madda above, khah, reh, heh, alef
# Yeh, noon, teh, heh, yeh; then beh, with or without a tatweel.
_YANTAHI_BI = "\u064a\u0646\u062a\u0647\u064a" r"\s+" "\u0628\u0640?"
_WA_OR_FA = "[\u0648\u0641]?"  # waw or feh, or none
_CUES = rf"(?<!\w)(?:{_ENDING_IN}|{_WA_OR_FA}(?:{_AKHIRUHA}|{_YANTAHI_BI}))"
# A run of digits, with the cue before it when one stands there.
_RUN = re.compile(rf"(?P<cue>{_CUES}\s*)?(?P<run>{_DIGIT}+)")
# The Arabic "and" (waw) num2words writes as a word of its own, and the space after it.
_LONE_AND = re.compile(r"(?<!\S)\u0648 ")
# A digit run's shortest length read as an ID with no cue and no leading zero.
_ID_DIGITS = 5

# num2words' converters are module-level objects that keep each call's number on themselves.
_ONE_AT_A_TIME = threading.Lock()


def _code(language: LanguageTag) -> str:
    """The primary code of `language`'s tag, which both Arabic tags share."""
    return "en" if language == "en" else "ar"


def speak_number(number: int, *, language: LanguageTag) -> str:
    """`number` in words, in `language` (MSA forms for both Arabic tags)."""
    if not isinstance(number, int):
        raise TypeError("speak_number says a whole number (an int); say a decimal another way")
    code = _code(language)
    with _ONE_AT_A_TIME:
        words: str = num2words(number, lang=code)
    if code == "en":
        return words.replace(",", "")
    return _LONE_AND.sub("\u0648", words)


def speak_id(digits: str, *, language: LanguageTag) -> str:
    """`digits` (ASCII or Arabic-Indic) read one by one in `language`, from the library's own
    table."""
    ascii_digits = digits.translate(_DIGIT_CHARACTERS)
    if not (ascii_digits.isascii() and ascii_digits.isdigit()):
        raise ValueError("speak_id reads a text of digits only, at least one")
    names = _DIGIT_WORDS[_code(language)]
    return " ".join(names[int(digit)] for digit in ascii_digits)


def _is_id(run: str, *, cued: bool) -> bool:
    """Whether a run of digits is read as an ID (the rule above)."""
    return cued or len(run) >= _ID_DIGITS or run.translate(_DIGIT_CHARACTERS).startswith("0")


def speak_digits(text: str, *, language: LanguageTag) -> str:
    """`text` with every run of digits in words, each an ID or a number by the rule above, the
    rest of the text as it was, but a space put between the words and a letter or digit the run
    was written against ("T2" says "T two")."""

    def said(match: re.Match[str]) -> str:
        cue, run = match.group("cue") or "", match.group("run")
        if _is_id(run, cued=bool(cue)):
            words = speak_id(run, language=language)
        else:
            words = speak_number(int(run.translate(_DIGIT_CHARACTERS)), language=language)
        before = cue[-1:] if cue else text[match.start() - 1 : match.start()]
        after = text[match.end() : match.end() + 1]
        lead = " " if re.fullmatch(r"\w", before) else ""
        tail = " " if re.fullmatch(r"\w", after) else ""
        return f"{cue}{lead}{words}{tail}"

    return _RUN.sub(said, text)
