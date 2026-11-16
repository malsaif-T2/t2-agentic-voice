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

An arrow, as a knowledge base writes a menu's path ("Inbox ← Archive"), is said as "then"
(`speak_arrows`), since a voice reads the symbol badly or not at all.

The forms a talker's reply holds (TD-058): a decimal ("3.5", or with the Arabic decimal
separator) is said as its whole part, "point" («فاصلة»), then its fraction digit by digit; a
number written with thousands separators ("1,234", or with the Arabic one) is that number, never
an ID; an Arabic prefix written onto a number (و، ف، ب، ل، ك and the others of
`ARABIC_PREFIXES`) stays on its first word («و٢١» says «وواحد وعشرون», not a lone waw); a bool
is refused, never said as 1 or 0; and a number past num2words' range (from 10**51 in Arabic) is
read digit by digit, after "minus" («سالب») when it is negative. The native speaker's check of
num2words' Arabic is still to come (TD-058).

A number said in a register (`speak_number(..., register=)`, Saudi or MSA) reads the library's
own tables instead (domain/text/arabic_numbers.py), as do the times, dates, durations and
amounts said by register (domain/text/spoken_forms.py); with no register, a number is said as
before.
"""

from __future__ import annotations

import re
import threading

from num2words import num2words

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import primary_code
from t2_agentic_voice.domain.text.arabic import normalize_arabic
from t2_agentic_voice.domain.text.arabic_numbers import HIGHEST, Register, arabic_number
from t2_agentic_voice.domain.text.digits import DIGIT_CHARACTERS
from t2_agentic_voice.domain.text.words import ARABIC_PREFIXES

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
DIGIT = "[0-9\u0660-\u0669\u06f0-\u06f9]"
# The cues that name a number's last digits (plan 003's decision log), each standing as whole
# words: "ending in", in any case; and in Arabic "akhiruha" and "yantahi bi" (its beh with or
# without a tatweel), either one after "wa" or "fa" or none.
_ENDING_IN = r"(?i:ending\s+in)"
_AKHIRUHA = "\u0622\u062e\u0631\u0647\u0627"  # alef with madda above, khah, reh, heh, alef
# Yeh, noon, teh, heh, yeh; then beh, with or without a tatweel.
_YANTAHI_BI = "\u064a\u0646\u062a\u0647\u064a" r"\s+" "\u0628\u0640?"
_WA_OR_FA = "[\u0648\u0641]?"  # waw or feh, or none
_CUES = rf"(?<!\w)(?:{_ENDING_IN}|{_WA_OR_FA}(?:{_AKHIRUHA}|{_YANTAHI_BI}))"
# A number as a text writes it, standing free (no digit, or digit and mark, on either side, so
# never a part of "192.168.1.1"): its whole part, with thousands separators (the comma or the
# ARABIC THOUSANDS SEPARATOR) or none, then a fraction after a point (the full stop or the
# ARABIC DECIMAL SEPARATOR), if any. Any other run of digits is read as a run alone.
_SEPARATORS = "[,\u066c]"  # the comma, ARABIC THOUSANDS SEPARATOR
_MARKS = "[.,\u066b\u066c]"  # a point or a separator: ARABIC DECIMAL and THOUSANDS SEPARATORS
_FREE_BEFORE = rf"(?<!{DIGIT})(?<!{DIGIT}{_MARKS})"
_FREE_AFTER = rf"(?!{_MARKS}?{DIGIT})"
_FORMED = (
    rf"{_FREE_BEFORE}(?P<whole>{DIGIT}{{1,3}}(?:{_SEPARATORS}{DIGIT}{{3}})+|{DIGIT}+)"
    rf"(?:[.\u066b](?P<fraction>{DIGIT}+))?{_FREE_AFTER}"
)
# A number or a run of digits, with the cue before it when one stands there.
_RUN = re.compile(rf"(?P<cue>{_CUES}\s*)?(?:{_FORMED}|(?P<run>{DIGIT}+))")
# The letters an Arabic prefix may be written with, right before a number: hamza to yeh, and
# the tatweel.
_PREFIX_LETTERS = re.compile("[\u0621-\u064a\u0640]+\\Z")
# The word said for a decimal point, and for a number below zero, as num2words says "-5"
# (salib khamsa): fasila (feh, alef, sad, lam, teh marbuta); salib (seen, alef, lam, beh).
_POINT = {"ar": "\u0641\u0627\u0635\u0644\u0629", "en": "point"}
_MINUS = {"ar": "\u0633\u0627\u0644\u0628", "en": "minus"}
# The Arabic "and" (waw) num2words writes as a word of its own, and the space after it.
_LONE_AND = re.compile(r"(?<!\S)\u0648 ")
# A digit run's shortest length read as an ID with no cue and no leading zero.
_ID_DIGITS = 5
# The numbers num2words says, by language: in Arabic, below 10**51 (from there it raises
# OverflowError, or for a number below zero fails an assertion of its own); in English it says
# every number tried, and an OverflowError it may raise is read as the same.
_RANGE = {"ar": 10**51}

# num2words' converters are module-level objects that keep each call's number on themselves.
_ONE_AT_A_TIME = threading.Lock()


def speak_number(number: int, *, language: LanguageTag, register: Register | None = None) -> str:
    """`number` in words, in `language`: with a `register`, an Arabic number from 0 to
    999 999 in that register's words, from the library's own tables (domain/text/
    arabic_numbers.py: «ألفين وأربع مية وخمسين» in Saudi); else, and for English, num2words'
    (MSA forms for both Arabic tags); past num2words' range, its digits one by one. TypeError
    for anything but an int, a bool included."""
    if isinstance(number, bool) or not isinstance(number, int):
        raise TypeError(
            "speak_number says a whole number (an int), never a bool; say a decimal another way"
        )
    code = primary_code(language)
    if register is not None and code == "ar" and 0 <= number <= HIGHEST:
        return arabic_number(number, register)
    words: str | None = None
    if abs(number) < _RANGE.get(code, abs(number) + 1):
        try:
            with _ONE_AT_A_TIME:
                words = num2words(number, lang=code)
        except OverflowError:  # past a range num2words keeps to itself
            words = None
    if words is None:
        digits = speak_id(str(abs(number)), language=language)
        return f"{_MINUS[code]} {digits}" if number < 0 else digits
    if code == "en":
        return words.replace(",", "")
    return _LONE_AND.sub("\u0648", words)


def speak_id(digits: str, *, language: LanguageTag) -> str:
    """`digits` (ASCII or Arabic-Indic) read one by one in `language`, from the library's own
    table."""
    ascii_digits = digits.translate(DIGIT_CHARACTERS)
    if not (ascii_digits.isascii() and ascii_digits.isdigit()):
        raise ValueError("speak_id reads a text of digits only, at least one")
    names = _DIGIT_WORDS[primary_code(language)]
    return " ".join(names[int(digit)] for digit in ascii_digits)


def _is_id(run: str, *, cued: bool) -> bool:
    """Whether a run of digits is read as an ID (the rule above)."""
    return cued or len(run) >= _ID_DIGITS or run.translate(DIGIT_CHARACTERS).startswith("0")


def _glued(text: str, at: int) -> bool:
    """Whether an Arabic prefix stands written onto the number that starts at `at`: the letters
    right before it, with no other letter before them, are one of `ARABIC_PREFIXES`."""
    found = _PREFIX_LETTERS.search(text, max(0, at - 8), at)
    if found is None:
        return False
    start = found.start()
    if start > 0 and re.fullmatch(r"\w", text[start - 1]):
        return False
    return normalize_arabic(found.group()) in ARABIC_PREFIXES


def _amount(whole: str, fraction: str | None, *, language: LanguageTag) -> str:
    """A number written with thousands separators or a fraction, in words: its whole part as a
    number, then the point and the fraction's digits one by one."""
    number = int(re.sub(_SEPARATORS, "", whole).translate(DIGIT_CHARACTERS))
    words = speak_number(number, language=language)
    if fraction is None:
        return words
    return f"{words} {_POINT[primary_code(language)]} {speak_id(fraction, language=language)}"


def speak_digits(text: str, *, language: LanguageTag) -> str:
    """`text` with every run of digits in words, each an ID or a number by the rule above, a
    decimal and a number with thousands separators as amounts (the module's docstring), the
    rest of the text as it was, but a space put between the words and a letter or digit the run
    was written against ("T2" says "T two"), unless that letter is an Arabic prefix written onto
    the number, which stays on its first word."""

    def said(match: re.Match[str]) -> str:
        cue = match.group("cue") or ""
        whole, fraction, run = match.group("whole"), match.group("fraction"), match.group("run")
        digits = run if whole is None else whole
        if whole is not None and (fraction is not None or re.search(_SEPARATORS, whole)):
            words = _amount(whole, fraction, language=language)
        elif _is_id(digits, cued=bool(cue)):
            words = speak_id(digits, language=language)
        else:
            words = speak_number(int(digits.translate(DIGIT_CHARACTERS)), language=language)
        start = match.start("run" if whole is None else "whole")
        before = cue[-1:] if cue else text[start - 1 : start]
        after = text[match.end() : match.end() + 1]
        glued = not cue and _glued(text, start)
        lead = " " if re.fullmatch(r"\w", before) and not glued else ""
        tail = " " if re.fullmatch(r"\w", after) else ""
        return f"{cue}{lead}{words}{tail}"

    return _RUN.sub(said, text)


# The two heavy arrows people type, said as "then" too (HEAVY WIDE-HEADED RIGHTWARDS ARROW,
# HEAVY ROUND-TIPPED RIGHTWARDS ARROW): Dingbats, which the script filter keeps for it
# (domain/text/scripts.py).
HEAVY_ARROWS = "\u2794\u279c"
# The arrow characters a text may hold: the Arrows and Supplemental Arrows-A blocks' and the two
# heavy arrows.
_ARROWS = re.compile(f"[\u2190-\u21ff\u27f0-\u27ff{HEAVY_ARROWS}]")
# What an arrow is said as: thumma (then), theh, meem.
_THEN_ARABIC = "\u062b\u0645"


def speak_arrows(text: str, *, language: LanguageTag) -> str:
    """`text` with each arrow between two words said as "then" in `language`, and an arrow with
    no words on one side of it dropped; a text with no arrow is returned as it is."""
    if _ARROWS.search(text) is None:
        return text
    parts = [part.strip() for part in _ARROWS.split(text)]
    kept = [part for part in parts if any(character.isalnum() for character in part)]
    then = "then" if language == "en" else _THEN_ARABIC
    return f" {then} ".join(kept)
