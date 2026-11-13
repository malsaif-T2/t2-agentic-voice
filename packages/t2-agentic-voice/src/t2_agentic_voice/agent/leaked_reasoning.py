"""The model's reasoning written into its answer, never said (D-089; the owner's approval of
2026-11-12, after the live call `_Hdmiy0vDE`, where the caller heard «…عشان أضيف الملاحظة.User:
"ما أعرف، سولها". Possibly they want us to ask the system for ticket status? …»). gpt-oss streams
its reasoning apart from its answer (adapters/groq_chat.py keeps only the answer), but now and
then writes some of it into the answer, glued to a sentence with no space between, as run A's
a2-dev saw too («…حالياً.We need to respond accordingly.…»).

- **Where a leak begins** is a sentence's start, two ways. Glued: a sentence's end mark (the full
  stop, question mark, exclamation mark or ellipsis, Latin or Arabic) after a letter, a digit
  or a letter's mark and before a character that is no space; there the text is a leak when
  the reply is in a language written in Arabic script and the sentence begins with a capital
  Latin letter, or, in any language, when it begins with one of the reasoning's own openings
  (`TELLS`: "We need",
  "According to", "The user", "Possibly", …). Glued or not, a sentence that begins with a
  speaker's label (`ROLES`: "User:", "Assistant:", …) is one, and so is a reply that does. A
  glued sentence that is neither (the model starting its answer again, «…بالضبط؟وش …») is
  said: the clause splitter cuts it there (domain/text/clauses.py), and the question limit
  counts its question.
- **What goes.** From a leak's first character, every piece of the model's text in that request
  goes, unspoken and unblocked; what came before it is said. The reply then stops, as the
  question limit stops one (agent/question_limit.py): the model's stream is closed, as a blocked
  clause's `drop_rest` closes it, no tool of that request runs and no request follows. What the
  model wrote is kept without the leak, so no later request reads it.
- **As it streams** (`text`): the text after a possible beginning is held until it is one or
  cannot be (a few characters: the longest opening), so the clause before it is never held.
  `close` gives what is held at the end of a request's text, when it is none; each request of
  the reply's is read on its own, so one's first sentence is never glued to the last's.
- **The count.** `logged` writes `talker_reasoning_dropped` with the call, the turn and the
  characters dropped (those that came before the stream was closed), never a word of them.

Lists, as a fast path: a leak with no tell and no glue is said, which the live calls and the
runs' stored replies will show if it happens (the owner's "lists plus a model's judgement",
2026-11-10, holds a model check for what lists miss; one here would cost every reply its time).
"""

from __future__ import annotations

import re
from typing import Final

from t2_agentic_voice.core.events import CallId, TurnId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.text.clauses import AFTER_WORD, SENTENCE_ENDS

_log = get_logger(__name__)

# A speaker's label, at a sentence's start: never words of a spoken reply.
ROLES: Final = ("User:", "Assistant:", "System:", "Developer:")
# How the reasoning's sentences open, glued to the answer's: never the start of one said to
# the caller, who is spoken to as "you".
TELLS: Final = (
    *ROLES,
    "We need",
    "We should",
    "We must",
    "We can't",
    "We cannot",
    "We have to",
    "According to",
    "The user",
    "The caller",
    "Possibly",
    "So we",
    "Let's",
    "Let me",
    "I need to",
    "I should",
)
_LONGEST: Final = max(len(tell) for tell in TELLS)
# A sentence's start: the text's first character that is no space, or one after a sentence's
# end mark (the clause splitter's), glued (group `glued`, the mark after a letter, a digit or a
# letter's mark) or after spaces.
_START = re.compile(
    rf"(?:^\s*|{AFTER_WORD}(?P<glued>[{SENTENCE_ENDS}])|[{SENTENCE_ENDS}]\s+)(?=\S)"
)


def _latin_capital(char: str) -> bool:
    return "A" <= char <= "Z"


class LeakedReasoning:
    """The leak check of one reply, in a language written in Arabic script when `arabic` (the
    module's docstring)."""

    def __init__(self, *, arabic: bool) -> None:
        self._arabic = arabic
        self._text = ""  # all the text fed, held part and leak included
        self._given = 0  # how much of it was given
        self.found = False  # a leak began: nothing more of the model's text is said
        self.dropped = 0  # the characters dropped from the leak on

    def text(self, piece: str) -> str:
        """`piece`, with the text held before it, less what is held now and what is a leak."""
        if self.found:
            self.dropped += len(piece)
            return ""
        self._text += piece
        return self._give(closing=False)

    def close(self) -> str:
        """What is held at the end of one request's text, which never became a leak; the next
        request's text starts anew."""
        given = "" if self.found else self._give(closing=True)
        self._text, self._given = "", 0
        return given

    def _give(self, *, closing: bool) -> str:
        until = len(self._text)
        # A start not yet read follows an end mark that is the given text's last character
        # other than a space, however many spaces were given after it: the scan resumes at
        # that character (at the text's beginning while it holds only spaces), so the text
        # streamed is read as it is in one piece.
        back = len(self._text[: self._given].rstrip())
        for start in _START.finditer(self._text, max(0, back - 1)):
            at = start.end()
            if at < self._given:
                continue
            verdict = self._leaks(self._text[at:], glued=start.group("glued") is not None)
            if verdict is None and not closing:
                until = at  # held until it is a leak or cannot be one
                break
            if verdict:
                self.found = True
                self.dropped = len(self._text) - at
                until = at
                break
        given, self._given = self._text[self._given : until], max(self._given, until)
        return given

    def _leaks(self, sentence: str, *, glued: bool) -> bool | None:
        """Whether `sentence`, the text from a sentence's start, is a leak; None while too
        little of it has come to tell."""
        openings = TELLS if glued else ROLES
        if any(sentence.startswith(opening) for opening in openings):
            return True
        if glued and self._arabic and sentence and _latin_capital(sentence[0]):
            return True
        if len(sentence) < _LONGEST and any(o.startswith(sentence) for o in openings):
            return None
        return False

    def logged(self, *, call_id: CallId, turn_id: TurnId) -> None:
        """Log `talker_reasoning_dropped` when a leak was found, by its count alone."""
        if self.found:
            _log.info(
                "talker_reasoning_dropped",
                call_id=call_id,
                turn_id=turn_id,
                dropped_chars=self.dropped,
            )
