"""The scripts a reply may hold: what the talker writes keeps the characters of the scripts its
agent's languages write, and loses a letter of any other script (a Chinese character a model
wrote into an Arabic reply) and every pictograph, so no voice says it and no caption, history or
trace holds it.

An agent's scripts are those of all its languages, never one reply's alone: `ar-SA` and `ar`
write Arabic and Latin (so an Arabic agent keeps its product names, codes, email addresses and
links), `en` Latin. Each character is judged alone, so a text that comes in pieces gives, piece
by piece, what it gives whole; nothing is held back, and nothing is guessed in a removed
character's place.

- **Kept:** the blocks of the agent's scripts (below); General Punctuation; the Arabic-Indic and
  Persian digits; every character of a term the agent declares; every other punctuation,
  symbol, space, control or format character (quotes, the percent sign, a currency or math
  sign, the arrows the speaking rules say as "then"); a number sign that is no decimal digit (a
  superscript, a vulgar fraction, a circled digit); and a code point Python's Unicode tables
  leave unassigned, outside the ranges taken out.
- **Rewritten one for one:** a fullwidth form as its ASCII form; the ideographic space, comma and
  full stop as a space, a comma and a full stop, so no two words are joined; a decimal digit of
  any other script as its ASCII digit.
- **Taken out:** every other letter or mark (Cyrillic, Greek, Hebrew, Devanagari, a variation
  selector) and every private-use or surrogate code point; whatever its category, a character
  of the CJK and Hangul ranges, so one newer than Python's tables goes too; and the pictographs:
  the emoji blocks, Miscellaneous Symbols and Dingbats but the two heavy arrows, and the emoji
  of other blocks below U+1F000 (the copyright, registered and trade mark signs and the double
  exclamation and exclamation question marks stay, as symbols).

`remove_stray_script` gives the text with how many characters it took out or rewrote, and a
label for each kind (`Kept`), never a character it took: the first word of the character's
Unicode name ("CJK", "GREEK"), "PICTOGRAPH", "FULLWIDTH", or the category of a code point with
no name. Each verdict is found once and kept in a table of the agent's scripts and declared
characters, so two agents never share a term's verdict. Public through the `languages` facade,
so a team's measurement reads a reply as the talker says it.
"""

from __future__ import annotations

import functools
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from t2_agentic_voice.core.settings.tts import LanguageTag

type Script = Literal["arabic", "latin"]
type _Ranges = tuple[tuple[int, int], ...]
# What one code point becomes: itself (its own number), its rewrite, or nothing (None).
type _Verdict = int | str | None

# Latin: Basic Latin to the Combining Diacritical Marks, Latin Extended Additional, Latin
# Extended-C and -D, and the Latin ligatures of Alphabetic Presentation Forms.
_LATIN: _Ranges = (
    (0x0000, 0x036F),
    (0x1E00, 0x1EFF),
    (0x2C60, 0x2C7F),
    (0xA720, 0xA7FF),
    (0xFB00, 0xFB06),
)
# Arabic: the Arabic block, Arabic Supplement, Arabic Extended-B and -A, and the Arabic
# Presentation Forms-A and -B.
_ARABIC: _Ranges = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x0870, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)
_BLOCKS: Mapping[Script, _Ranges] = {"arabic": _ARABIC, "latin": _LATIN}
# The scripts each language writes.
SCRIPTS: Mapping[LanguageTag, frozenset[Script]] = {
    "ar-SA": frozenset({"arabic", "latin"}),
    "ar": frozenset({"arabic", "latin"}),
    "en": frozenset({"latin"}),
}
# Kept whatever the scripts: General Punctuation, the Arabic-Indic digits and the Persian
# (Extended Arabic-Indic) digits.
_SHARED: _Ranges = ((0x2000, 0x206F), (0x0660, 0x0669), (0x06F0, 0x06F9))
# Rewritten: the fullwidth forms of ASCII's "!" to "~", as ASCII; and the ideographic space,
# comma and full stop.
_FULLWIDTH = (0xFF01, 0xFF5E)
_FULLWIDTH_OFFSET = 0xFEE0
_IDEOGRAPHIC: Mapping[int, str] = {0x3000: " ", 0x3001: ",", 0x3002: "."}
# Taken out whatever their category: the CJK Radicals Supplement to Yi Radicals (kana, bopomofo,
# Hangul compatibility jamo, the CJK symbols and ideographs among them), the Hangul syllables
# and Hangul Jamo Extended-B, the CJK Compatibility Ideographs, the CJK Compatibility Forms, and
# the ideographs of planes 2 and 3.
_CJK: _Ranges = (
    (0x2E80, 0xA4CF),
    (0xAC00, 0xD7FF),
    (0xF900, 0xFAFF),
    (0xFE30, 0xFE4F),
    (0x20000, 0x3FFFF),
)
# The pictographs: the emoji blocks, Mahjong Tiles to Symbols and Pictographs Extended-A;
# Miscellaneous Symbols and Dingbats, but the two heavy arrows the speaking rules say as "then"
# (HEAVY WIDE-HEADED RIGHTWARDS ARROW, HEAVY ROUND-TIPPED RIGHTWARDS ARROW); and the emoji of
# other blocks below U+1F000, as Unicode's emoji data lists them: the watch and hourglass, the
# keyboard, the eject and media buttons, the circled M, the small and medium squares, the play
# and reverse buttons, two curved arrows, the left, up and down arrows, the large squares, the
# star and the heavy circle. The copyright, registered and trade mark signs, the double
# exclamation and exclamation question marks and the arrows of the Arrows block stay symbols.
_PICTOGRAPHS: _Ranges = ((0x1F000, 0x1FAFF), (0x2600, 0x27BF))
_HEAVY_ARROWS = frozenset({0x2794, 0x279C})
_EMOJI: _Ranges = (
    (0x231A, 0x231B),
    (0x2328, 0x2328),
    (0x23CF, 0x23CF),
    (0x23E9, 0x23F3),
    (0x23F8, 0x23FA),
    (0x24C2, 0x24C2),
    (0x25AA, 0x25AB),
    (0x25B6, 0x25B6),
    (0x25C0, 0x25C0),
    (0x25FB, 0x25FE),
    (0x2934, 0x2935),
    (0x2B05, 0x2B07),
    (0x2B1B, 0x2B1C),
    (0x2B50, 0x2B50),
    (0x2B55, 0x2B55),
)
# The general categories of a letter or a mark, and of a private-use or surrogate code point.
_TAKEN = frozenset({"Co", "Cs"})
PICTOGRAPH, FULLWIDTH = "PICTOGRAPH", "FULLWIDTH"
# The most labels one result gives.
MAX_LABELS = 8


@dataclass(frozen=True, slots=True)
class Kept:
    """What `remove_stray_script` kept of a text: the `text`, how many characters it took out or
    rewrote (`changed`), and a label for each kind of them (`labels`: at most `MAX_LABELS`,
    sorted; the module's docstring). It holds no character it took."""

    text: str
    changed: int = 0
    labels: tuple[str, ...] = ()


def _within(code: int, ranges: _Ranges) -> bool:
    return any(start <= code <= end for start, end in ranges)


def _label(char: str) -> str:
    """The first word of `char`'s Unicode name, or its category when it has none."""
    name = unicodedata.name(char, "")
    return name.partition(" ")[0] if name else unicodedata.category(char)


def _verdict(char: str, blocks: _Ranges, declared: frozenset[str]) -> tuple[_Verdict, str]:
    """What `char` becomes (the module's docstring) and, when it changes, its label ("" when
    it is kept)."""
    code = ord(char)
    if char in declared or _within(code, blocks) or _within(code, _SHARED):
        return code, ""
    if _FULLWIDTH[0] <= code <= _FULLWIDTH[1]:
        plain = chr(code - _FULLWIDTH_OFFSET)
        kept = _verdict(plain, blocks, declared)[0] == ord(plain)
        return (plain if kept else None), FULLWIDTH
    if code in _IDEOGRAPHIC:
        return _IDEOGRAPHIC[code], _label(char)
    category = unicodedata.category(char)
    digit = unicodedata.decimal(char, None) if category == "Nd" else None
    if digit is not None:
        return str(digit), _label(char)
    if _within(code, _CJK):
        return None, _label(char)
    if (_within(code, _PICTOGRAPHS) and code not in _HEAVY_ARROWS) or _within(code, _EMOJI):
        return None, PICTOGRAPH
    if category[0] in "LM" or category in _TAKEN:
        return None, _label(char)
    return code, ""


class _Verdicts(dict[int, _Verdict]):
    """Each code point's verdict for one agent's scripts (`blocks`) and declared characters,
    found the first time it is asked for (`__missing__`), as `str.translate` reads a table; the
    label of each one that changes, in `labels`."""

    def __init__(self, blocks: _Ranges, declared: frozenset[str]) -> None:
        super().__init__()
        self.blocks, self.declared = blocks, declared
        self.labels: dict[int, str] = {}

    def __missing__(self, code: int) -> _Verdict:
        found, label = _verdict(chr(code), self.blocks, self.declared)
        if label:
            self.labels[code] = label
        self[code] = found
        return found


@functools.lru_cache(maxsize=64)
def _verdicts(scripts: frozenset[Script], declared: frozenset[str]) -> _Verdicts:
    blocks = tuple(each for script in sorted(scripts) for each in _BLOCKS[script])
    return _Verdicts(blocks, declared)


class ScriptRule:
    """The rule for an agent of `languages` that declares the terms `kept` (the module's
    docstring): called with a text, it gives what it keeps of it (`Kept`). ValueError for a tag
    no language has; it never raises for a text."""

    def __init__(self, languages: Iterable[LanguageTag], kept: Iterable[str] = ()) -> None:
        scripts: set[Script] = set()
        for tag in languages:
            if tag not in SCRIPTS:
                raise ValueError(f"no language has the tag {tag!r}: give ar-SA, ar or en")
            scripts |= SCRIPTS[tag]
        declared = frozenset(char for term in kept for char in term)
        self._verdicts = _verdicts(frozenset(scripts), declared)

    def __call__(self, text: str) -> Kept:
        verdicts = self._verdicts
        found = text.translate(verdicts)
        if found == text:
            return Kept(text=text)
        changed = [ord(char) for char in text if verdicts[ord(char)] != ord(char)]
        labels = sorted({verdicts.labels[code] for code in changed})[:MAX_LABELS]
        return Kept(text=found, changed=len(changed), labels=tuple(labels))


def remove_stray_script(
    text: str, *, languages: Iterable[LanguageTag], kept: Iterable[str] = ()
) -> Kept:
    """`text` with each character no script of `languages` writes taken out or rewritten, but
    those of the terms `kept` (the module's docstring); the text itself when nothing changed."""
    return ScriptRule(languages, kept)(text)
