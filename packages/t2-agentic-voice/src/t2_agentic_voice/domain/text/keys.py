"""Key combinations and letters, said as a caller says them: "Ctrl + Shift + R" is "Control
Shift R" in English and «كنترول شفت آر» in Arabic, its plus signs never read (the owner's
choice of 2026-11-16), when the `tts.spoken_key_combinations` setting asks; and a run of
capitals spelled letter by letter (`spell_letters`: "OTP" is "O T P", «أو تي بي»), which a
team uses in its pronunciation map for its own terms (ARCH-WORDS keeps those in its app).

A combination is two keys or more joined by "+", standing as whole words: the first a key's name
(`KEY_NAMES`, in any case) or a function key ("F5"), each after it one of those, a letter or a
digit. A Latin letter is said in Arabic by its English name, as Saudi callers say it («آر»,
«إف»); a digit by its number.
"""

from __future__ import annotations

import re
from typing import Final

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import primary_code
from t2_agentic_voice.domain.text.speaking import speak_number

# The Latin letters' English names as Arabic writes them, A to Z: ei, bi, si, di, i, if, ji,
# itsh, ai, jei, kei, il, im, in, o, bi, kyu, ar, is, ti, yu, vi, dablyu, iks, wai, zid.
_LETTERS_AR: Final = (
    "\u0625\u064a\u0647",
    "\u0628\u064a",
    "\u0633\u064a",
    "\u062f\u064a",
    "\u0625\u064a",
    "\u0625\u0641",
    "\u062c\u064a",
    "\u0625\u062a\u0634",
    "\u0622\u064a",
    "\u062c\u064a\u0647",
    "\u0643\u064a\u0647",
    "\u0625\u0644",
    "\u0625\u0645",
    "\u0625\u0646",
    "\u0623\u0648",
    "\u0628\u064a",
    "\u0643\u064a\u0648",
    "\u0622\u0631",
    "\u0625\u0633",
    "\u062a\u064a",
    "\u064a\u0648",
    "\u0641\u064a",
    "\u062f\u0628\u0644\u064a\u0648",
    "\u0625\u0643\u0633",
    "\u0648\u0627\u064a",
    "\u0632\u062f",
)
# Each key's name as written (lower case), and how English and Arabic say it: kontrol, shift,
# alt, dilit, intar, iskeib, tab, windoz, komand, speis, bak speis, hom, ind.
KEY_NAMES: Final[dict[str, tuple[str, str]]] = {
    "ctrl": ("Control", "\u0643\u0646\u062a\u0631\u0648\u0644"),
    "control": ("Control", "\u0643\u0646\u062a\u0631\u0648\u0644"),
    "shift": ("Shift", "\u0634\u0641\u062a"),
    "alt": ("Alt", "\u0623\u0644\u062a"),
    "del": ("Delete", "\u062f\u064a\u0644\u064a\u062a"),
    "delete": ("Delete", "\u062f\u064a\u0644\u064a\u062a"),
    "enter": ("Enter", "\u0625\u0646\u062a\u0631"),
    "esc": ("Escape", "\u0625\u0633\u0643\u064a\u0628"),
    "tab": ("Tab", "\u062a\u0627\u0628"),
    "win": ("Windows", "\u0648\u064a\u0646\u062f\u0648\u0632"),
    "cmd": ("Command", "\u0643\u0648\u0645\u0627\u0646\u062f"),
    "space": ("Space", "\u0633\u0628\u064a\u0633"),
    "backspace": ("Backspace", "\u0628\u0627\u0643 \u0633\u0628\u064a\u0633"),
    "home": ("Home", "\u0647\u0648\u0645"),
    "end": ("End", "\u0625\u0646\u062f"),
}
# A combination's first key is a key's name or a function key, so "1 + 2" is never one.
_FIRST = rf"(?:{'|'.join(sorted(KEY_NAMES, key=len, reverse=True))}|F[1-9][0-2]?)"
_KEY = rf"(?:{_FIRST}|[A-Za-z0-9])"
_COMBINATION = re.compile(rf"(?<!\w){_FIRST}(?:\s*\+\s*{_KEY})+(?!\w)", re.IGNORECASE)
_PLUS = re.compile(r"\s*\+\s*")


def _letter(letter: str, *, arabic: bool) -> str:
    return _LETTERS_AR[ord(letter.upper()) - ord("A")] if arabic else letter.upper()


def spell_letters(letters: str, *, language: LanguageTag) -> str:
    """`letters`, Latin letters only, said one by one: "O T P" in English, «أو تي بي» in
    Arabic. ValueError for anything else."""
    if not (letters.isascii() and letters.isalpha()):
        raise ValueError("spell_letters spells Latin letters only, at least one")
    arabic = primary_code(language) == "ar"
    return " ".join(_letter(letter, arabic=arabic) for letter in letters)


def _key(written: str, *, language: LanguageTag) -> str:
    arabic = primary_code(language) == "ar"
    named = KEY_NAMES.get(written.lower())
    if named is not None:
        return named[1] if arabic else named[0]
    if written.isdigit():
        return speak_number(int(written), language=language)
    if len(written) > 1:  # a function key: its F, then its number
        return f"{_letter('F', arabic=arabic)} {speak_number(int(written[1:]), language=language)}"
    return _letter(written, arabic=arabic)


def speak_keys(text: str, *, language: LanguageTag) -> str:
    """`text` with each key combination said as its keys, one after another, its plus signs
    left out (the module's docstring); a text with none is returned as it is."""

    def said(match: re.Match[str]) -> str:
        keys = _PLUS.split(match.group())
        return " ".join(_key(key, language=language) for key in keys)

    return _COMBINATION.sub(said, text)
