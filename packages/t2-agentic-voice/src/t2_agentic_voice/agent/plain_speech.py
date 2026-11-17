"""Plain speech (D-111; the lead's ruling under GP-18), only under `guard.plain_speech`, off by
default: what the talker writes is said only as plain speech. Pure rules, which agent/turn.py,
turn_answer.py and clause_gate.py apply.

1. **Dot runs** (`DotRuns`). A run of two or more full stops or ellipses right after a sentence's
   mark is taken out, and one right after a word becomes one ellipsis, before the leak check and
   the clause splitter read the text: "back?.....Could" is two sentences then, so the question
   limit drops the second question and the leak check sees its start. As the text streams, a
   run at a piece's end is held until the next character comes (`feed`, `close`).
2. **Not speech** (`is_speech`). A whole clause is not speech when fewer than half of its
   characters other than spaces are letters or digits (Arabic harakat and every other combining
   mark counted as a letter's), or when it holds "[", "{" or "<": from that clause on, nothing
   more of that request is said and none of its tools runs, the way a reasoning leak is
   dropped; the turn tries the request once more when it said nothing yet (agent/turn.py).
3. **Marks taken out** (`spoken`). The zero-width space (U+200B), the word joiner (U+2060), the
   byte order mark (U+FEFF) and the markdown marks "*" and "`" are taken out of every clause
   before it is said, so they never reach text-to-speech.
"""

from __future__ import annotations

import unicodedata
from typing import Final

from t2_agentic_voice.domain.text.clauses import SENTENCE_ENDS

# What a dot run is made of: the full stop and the horizontal ellipsis.
_RUN: Final = frozenset(".\u2026")
# What a dot run after a word becomes: one ellipsis, a sentence's end.
_ONE: Final = "\u2026"
# A sentence's marks a run may follow, but the run's own (the Arabic question mark and full
# stop, the question and exclamation marks).
_MARKS: Final = frozenset(SENTENCE_ENDS) - _RUN
# What makes a clause no speech at once: a bracket, a brace or a tag's opening.
_NOT_SAID: Final = frozenset("[{<")
# The share of a clause's characters, spaces aside, that must be letters, marks or digits.
MIN_SHARE: Final = 0.5
# What is taken out of a clause before it is said: ZERO WIDTH SPACE, WORD JOINER, ZERO WIDTH
# NO-BREAK SPACE (the byte order mark), and the markdown marks.
_TAKEN: Final = dict.fromkeys(map(ord, "\u200b\u2060\ufeff*`"))


def _word(char: str) -> bool:
    """Whether `char` is a letter, a digit or a letter's combining mark."""
    return char.isalnum() or unicodedata.category(char).startswith("M")


class DotRuns:
    """Rule 1 on a text that comes in pieces (the module's docstring): `feed` each piece, and
    it gives the text up to a run still open at the piece's end; `close` gives the rest. Not
    `on`, it gives each piece as it came."""

    def __init__(self, *, on: bool = True) -> None:
        self._on = on
        self._held = ""  # a run of dots not yet closed by the next character
        self._before = ""  # the last character given before it

    def feed(self, piece: str) -> str:
        if not self._on:
            return piece
        out: list[str] = []
        for char in piece:
            if char in _RUN:
                self._held += char
                continue
            out.append(self._run())
            out.append(char)
            self._before = char
        return "".join(out)

    def close(self) -> str:
        return self._run()

    def _run(self) -> str:
        """The run held, as rule 1 makes it, and none held after."""
        run, self._held = self._held, ""
        if len(run) < 2:
            return run
        if self._before in _MARKS:
            return ""
        return _ONE if self._before and _word(self._before) else run


def is_speech(clause: str) -> bool:
    """Whether `clause` is speech (rule 2): no bracket, brace or tag's opening, and at least
    `MIN_SHARE` of its characters, spaces aside, letters, marks or digits."""
    if any(char in _NOT_SAID for char in clause):
        return False
    shown = [char for char in clause if not char.isspace()]
    if not shown:
        return True  # nothing to judge: the splitter leaves such a clause out
    return sum(_word(char) for char in shown) >= MIN_SHARE * len(shown)


def spoken(clause: str) -> str:
    """`clause` with the invisible and markdown marks taken out (rule 3), its spaces made one."""
    return " ".join(clause.translate(_TAKEN).split())
