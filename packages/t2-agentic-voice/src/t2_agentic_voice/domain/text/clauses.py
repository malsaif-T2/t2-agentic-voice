"""The clause splitter (the design's 13): the library's only one, so a reply is cut the same way
whether it is spoken or shown, and Pipecat's text-to-speech aggregation passes each clause
through whole (TOKEN), one request a clause. The phrase cache cuts a fixed phrase longer than
`max_chars` with it too, and packs the clauses into as few requests as fit
(adapters/phrase_cache.py), and the talker cuts the model's text with it as the text streams
(`ClauseStream`, agent/talker.py). Public through the `languages` facade (`split_clauses`).

A word is a run of characters between spaces (any Unicode space), and a clause ends after a
word whose last character, closing quotes and brackets aside, is a clause's mark: the Arabic
comma, semicolon, question mark and full stop, or the comma, semicolon, colon, full stop,
question mark, exclamation mark or ellipsis. So a mark inside a word ("3.5", "t2.example")
cuts nothing, but for a sentence's end glued to the next sentence with no space between: a
sentence's mark (the Arabic question mark and full stop, the full stop, question mark,
exclamation mark or ellipsis) after a letter, a digit or a letter's mark and before a letter
that is no lowercase Latin one ends a word there (an abbreviation in capitals, "U.S.", is cut
too, which only cuts its speech in two). gpt-oss writes them so when it joins two pieces of its
answer («…بالضبط؟وش …», "…as needed.Open …"; D-089), and the question limit then counts the
first one's question (agent/question_limit.py). A clause's words are joined by one space, and a
clause that holds no letter, digit or symbol (only marks, as ". ." leaves) says nothing and is
left out.
"""

from __future__ import annotations

import re
import unicodedata

# The marks that end a clause: ARABIC COMMA, ARABIC SEMICOLON, ARABIC QUESTION MARK, ARABIC FULL
# STOP; the English punctuation; HORIZONTAL ELLIPSIS.
_ENDS = frozenset("\u060c\u061b\u061f\u06d4" + ",;:.?!" + "\u2026")
# The marks that end a sentence: the Arabic question mark and full stop, and the English ones,
# as a regular expression's character class holds them; the leak check reads the same
# (agent/leaked_reasoning.py).
SENTENCE_ENDS = "\u061f\u06d4" + ".?!" + "\u2026"
_SENTENCE_ENDS = frozenset(SENTENCE_ENDS)
# Under `whole_sentences`, how long a clause must be for a comma, colon or semicolon to end it.
LONG_CLAUSE_CHARS = 120
# What may follow a clause's mark in its word: quotes and closing brackets, the right-pointing
# guillemet and the right quotation marks among them. The question limit reads a clause's end
# past them too (agent/question_limit.py).
CLOSERS = "\"')]}\u00bb\u201d\u2019"
# The general categories of what is said: letters, numbers and symbols.
_SAID = frozenset("LNS")
# The combining marks a word may end in, a letter's diacritics: the Latin ones and the Arabic
# harakat, tanween among them («حالياً.»), and the superscript alef.
WORD_MARKS = "\u0300-\u036f\u064b-\u065f\u0670"
# Where a sentence's end mark is glued to the word before it, as a lookbehind: after a letter,
# a digit or a letter's mark.
AFTER_WORD = rf"(?<=[^\W_]|[{WORD_MARKS}])"
# A sentence's end glued to the next sentence (the module's docstring): the mark is kept on the
# word it ends.
_GLUED = re.compile(rf"{AFTER_WORD}([{SENTENCE_ENDS}])(?=[^\W\d_a-z])")


def _words(text: str) -> list[str]:
    """`text`'s words: its runs between spaces, each cut after a glued sentence's end."""
    return _GLUED.sub(lambda mark: f"{mark.group(1)} ", text).split()


def _ends_clause(word: str) -> bool:
    """Whether `word` ends its clause (above)."""
    return word.rstrip(CLOSERS)[-1:] in _ENDS


def _says_something(clause: str) -> bool:
    """Whether `clause` holds a letter, a digit or a symbol."""
    return any(unicodedata.category(char)[0] in _SAID for char in clause)


def _fitted(words: list[str], max_chars: int | None) -> list[str]:
    """The words of one clause, joined greedily into pieces of at most `max_chars` characters,
    cut only between words but for a word longer than `max_chars`, which alone is cut every
    `max_chars` characters, its pieces clauses of their own."""
    if max_chars is None:
        return [" ".join(words)] if words else []
    pieces: list[str] = []
    piece = ""
    for word in words:
        if len(word) > max_chars:
            pieces += [piece] if piece else []
            pieces += [word[at : at + max_chars] for at in range(0, len(word), max_chars)]
            piece = ""
        elif not piece:
            piece = word
        elif len(piece) + 1 + len(word) <= max_chars:
            piece = f"{piece} {word}"
        else:
            pieces.append(piece)
            piece = word
    return [*pieces, piece] if piece else pieces


def split_clauses(text: str, *, max_chars: int | None) -> tuple[str, ...]:
    """`text` cut into clauses at the Arabic comma and question mark, the full stop and English
    punctuation, each clause at most `max_chars` characters (the provider's `max_chars`; None for
    no limit), in order; no clause is empty, and a text with nothing to say gives none. No clause
    is cut inside a word, but for a word longer than `max_chars` (a long code read out, or a
    repetition the speech-to-text heard): that word alone is cut every `max_chars` characters,
    the only cut inside a word, so every clause still fits one request: `"x" * 201` at 200
    gives `"x" * 200` and `"x"`, and the words around such a word end their clauses before it
    and start the next after it."""
    if max_chars is not None and max_chars < 1:
        raise ValueError("max_chars is at least 1, or None for no limit")
    clauses: list[str] = []
    words: list[str] = []
    for word in _words(text):
        words.append(word)
        if _ends_clause(word):
            clauses += _fitted(words, max_chars)
            words = []
    clauses += _fitted(words, max_chars)
    return tuple(clause for clause in clauses if _says_something(clause))


class ClauseStream:
    """`split_clauses` on a text that comes in pieces, as a model writes its reply (plan 006,
    "What voice-first means here", item 4): `feed` each piece as it comes, and it gives each
    clause as soon as it is whole, once a space follows the word that ends it; `close`, at the
    text's end, gives what is left. The clauses it gives, in order, are `split_clauses` of the
    whole text, however the text was cut into pieces. Under `whole_sentences` a clause ends only
    at a sentence's end, or at a comma, colon or semicolon once it is `LONG_CLAUSE_CHARS` long:
    the English voice says each request as a whole utterance, so pieces cut at every comma sound
    out of breath (D-077)."""

    def __init__(self, *, max_chars: int | None, whole_sentences: bool = False) -> None:
        if max_chars is not None and max_chars < 1:
            raise ValueError("max_chars is at least 1, or None for no limit")
        self._max_chars = max_chars
        self._whole_sentences = whole_sentences
        self._tail = ""  # the text after the last space: a word that may go on
        self._words: list[str] = []  # the words of the clause not yet ended

    def feed(self, piece: str) -> tuple[str, ...]:
        """The clauses `piece` ends, with the text fed before it."""
        text = self._tail + piece
        cut = len(text)
        while cut > 0 and not text[cut - 1].isspace():
            cut -= 1
        self._tail = text[cut:]
        return self._clauses(_words(text[:cut]), closing=False)

    def close(self) -> tuple[str, ...]:
        """The clauses left at the text's end; the stream is empty after it."""
        words, self._tail = _words(self._tail), ""
        return self._clauses(words, closing=True)

    def _ended(self, word: str) -> bool:
        """Whether `word`, the last of the words kept, ends their clause."""
        if not self._whole_sentences or not _ends_clause(word):
            return _ends_clause(word)
        return (
            word.rstrip(CLOSERS)[-1:] in _SENTENCE_ENDS
            or len(" ".join(self._words)) >= LONG_CLAUSE_CHARS
        )

    def _clauses(self, words: list[str], *, closing: bool) -> tuple[str, ...]:
        clauses: list[str] = []
        for word in words:
            self._words.append(word)
            if self._ended(word):
                clauses += _fitted(self._words, self._max_chars)
                self._words = []
        if closing:
            clauses += _fitted(self._words, self._max_chars)
            self._words = []
        return tuple(clause for clause in clauses if _says_something(clause))
