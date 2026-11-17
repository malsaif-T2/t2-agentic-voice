"""How the yes rule reads the heard words (domain/yes_rule.py, the design's 8.3): each word's kind
on its lists (`kinds`), a plain no (`plain_no`), a change marker (`marked`), and the echo rail's
reading of the agent's own lines heard back (`echoes`, `SaidLines`, `playing`), and, under
`interruptions.yes_over_read_back` (D-108), khalas beside a send word (`holds_okay`) and a yes
said over the summary (`held_yes`). Pure, with no IO; the yes rule alone issues anything from
them.

The words are read in the rule's form (domain/words.py's `rule_form`), as the interruption rule
reads them: each listed phrase one word, the longest that starts at a word first, and a word on
no list after waw (and) a send word when the rest of it is one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from t2_agentic_voice.domain.consent_check import ConsentAnswer
from t2_agentic_voice.domain.interruption_words import QUESTION_MARKS
from t2_agentic_voice.domain.interruptions import own_words
from t2_agentic_voice.domain.text.words import holds_words, phrase_tokens
from t2_agentic_voice.domain.words import rule_form
from t2_agentic_voice.domain.yes_words import ConsentWords

# What one word of the heard words is to the rule: on a list, or on none (`content`).
Kind = Literal["no", "yes", "send", "filler", "content"]
AND = "\u0648"  # waw, and
# A chat model's word on the words (domain/consent_check.py's), or None for no word: the request
# failed or timed out.
type ModelWord = ConsentAnswer | None
# The stop words that say "that's it, go ahead" beside a yes or a send word (D-108): khalas, a
# stop word to the interruption rule and a filler to the yes rule's lists; alone it still stops
# a read-back (D-081, amended 2026-11-11).
OKAY_STOPS: Final = ("\u062e\u0644\u0627\u0635",)  # khalas, that's it: khah, lam, alef, sad


@dataclass(frozen=True, slots=True, kw_only=True)
class SaidLines:
    """What the agent said of one read-back, each line written and spoken, as the yes rule's
    echo rail reads them (domain/yes_rule.py's docstring): `read_back`, its summary and closing
    question; `asked_again`, the line that asks it again; and whether the caller's speech began
    while each was still heard, its reply playing or within its tail after it ended
    (`over_read_back`, `over_asked_again`), which the session tells, each True when it cannot
    tell, so the rail keeps that line."""

    read_back: tuple[str, ...]
    asked_again: tuple[str, ...]
    over_read_back: bool = True
    over_asked_again: bool = True


def _listed(words: ConsentWords) -> dict[str, Kind]:
    """Each listed word or phrase with its kind; one on two lists takes the first of no, yes,
    send and filler, so a word a team adds as a yes is never only a filler."""
    listed: dict[str, Kind] = {}
    lists: tuple[tuple[Kind, tuple[str, ...]], ...] = (
        ("filler", words.fillers),
        ("send", words.send),
        ("yes", words.yes),
        ("no", words.no),
    )
    for kind, phrases in lists:
        listed.update(dict.fromkeys(phrases, kind))
    return listed


def kinds(text: str, words: ConsentWords) -> set[Kind]:
    """The kinds of the words of `text`, in the rule's form, each listed phrase one word, the
    longest that starts at a word first; a word on no list after waw (and) is a send word when
    the rest of it is one."""
    listed = _listed(words)
    found: set[Kind] = set()
    for word in phrase_tokens(text.split(), listed.keys()):
        kind = listed.get(word)
        if kind is None and word.startswith(AND) and listed.get(word[1:]) == "send":
            kind = "send"
        found.add(kind or "content")
    return found


def plain_no(text: str, words: ConsentWords) -> bool:
    """Whether `text`, brought to the rule's form, is a plain no to the lists `words`: a no
    word, and beside it only send words and fillers ("no, cancel it, don't send it"), with no
    yes word and no word on none of the lists; the words `decide` declines once the summary
    played. The session reads what cuts a read-back's summary with it (voice/session/
    read_back.py's `handed`), so a cancel said over it is a no, not a correction."""
    found = kinds(rule_form(text), words)
    return "no" in found and not found & {"yes", "content"}


def marked(text: str, markers: tuple[str, ...]) -> bool:
    """Whether `text`, in the rule's form, holds a change marker as whole words, or one after
    waw (and) written onto it."""
    if any(holds_words(text, marker) for marker in markers):
        return True
    return any(word.startswith(AND) and word[1:] in markers for word in text.split())


def echoes(text: str, lines: Sequence[str]) -> bool:
    """Whether `text`, in the rule's form, is the agent's own words, its `lines` playing as the
    speech began read together as the interruption rule reads the clauses that played
    (domain/interruptions.py's `own_words`): every word a word of them, or one edit from one of
    three letters or more. Its read-back heard back, across two lines or a letter off, never
    the caller's answer."""
    heard = text.split()
    return bool(heard) and own_words(heard, [rule_form(line) for line in lines])


def playing(said: SaidLines, *, over: bool) -> tuple[str, ...]:
    """The lines of `said` still heard by the caller as the speech began: the read-back's over
    the closing question (`over`) or as the session tells it, its tail included; the ask-again
    line's as the session tells it; none else, so words begun while none was heard are never
    the agent's echo."""
    reading = over or said.over_read_back
    asking = said.over_asked_again
    return (*(said.read_back if reading else ()), *(said.asked_again if asking else ()))


def holds_okay(text: str) -> bool:
    """Whether `text`, in the rule's form, holds one of `OKAY_STOPS` as a whole word."""
    return any(holds_words(text, word) for word in OKAY_STOPS)


def held_yes(
    word: ModelWord,
    text: str,
    words: ConsentWords,
    *,
    said: SaidLines,
    rails: ConsentWords | None = None,
) -> bool:
    """Whether `text`, said over a read-back's summary, is a yes held on it (D-108): by the
    lists `words`, a yes or a send word among only yes words, send words and fillers (khalas
    among them); or, on words the lists leave unplaced, a chat model's `word` `yes` or `send`.
    Never with a question mark, a no word or a change marker of `rails` (`words` unless given),
    or when the words are the agent's own lines `said` heard back (`echoes`)."""
    form, rail = rule_form(text), rails or words
    if not form or any(mark in text for mark in QUESTION_MARKS):
        return False
    if marked(form, rail.change) or echoes(form, playing(said, over=True)):
        return False
    found = kinds(form, words)
    if found <= {"yes", "send", "filler"}:
        return bool(found & {"yes", "send"})
    return word in ("yes", "send") and "no" not in found | kinds(form, rail)
