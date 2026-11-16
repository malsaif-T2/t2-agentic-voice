"""The repeat measures of a call's replies (plan 010's measurement: its calls report's definitions
and its long-call checks; D-101), one definition for every app's runs. Pure functions of the
texts they are given: no call, no clock, no model.

- **An identical repeat:** a reply whose normalized text is the same as an earlier reply's.
- **A near repeat:** a reply whose first clause, normalized, is the same as an earlier reply's, or
  whose token overlap with an earlier reply is `NEAR_REPEAT_OVERLAP` (0.8) or more.
- **The exemptions:** a reply in a turn that asks to hear something again, and a read-back said
  again, are never repeats; the caller of `find_repeat` says which a reply is.
- **The cut repeat:** after a reply cut short, the reply to "one more time" repeats it when it
  holds `CUT_REPEAT_SHARE` (60%) or more of the cut reply's tokens, the cut reply's whole text.

Every text is first put in the scorers' form (`scored_form`: `normalize_arabic`, then
`normalize_digits`), so Arabic and English compare alike: diacritics, the alef, hamza, teh
marbuta and alef maksura forms, punctuation and case make no difference, and a digit written or
said one word at a time reads as one. A token is a word of that form. The first clause is the
first clause the library's splitter gives (`split_clauses`: the Arabic comma, semicolon,
question mark and full stop, and the English punctuation), then normalized. Tokens are counted
as a multiset: a word a reply says twice counts twice, and is matched at most as often as the
other text holds it. A reply that says nothing (empty, or only marks) is never a repeat and
repeats nothing. Public through the `evals` facade (D-021).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from t2_agentic_voice.domain.scoring import scored_form
from t2_agentic_voice.domain.text.clauses import split_clauses

# The token overlap at or above which a reply is a near repeat of an earlier one.
NEAR_REPEAT_OVERLAP = 0.8
# The share of a cut reply's tokens the reply to "one more time" holds when it repeats it.
CUT_REPEAT_SHARE = 0.6


@dataclass(frozen=True)
class Repeat:
    """What `find_repeat` found: the `kind` of repeat, the place in `earlier` of the reply it
    repeats (the latest one, of the strongest kind), what it was found `by` (the whole
    normalized text, the first clause, or the token overlap), and the token `overlap` of the
    two (1.0 for an identical repeat)."""

    kind: Literal["identical", "near"]
    earlier: int
    by: Literal["text", "first_clause", "overlap"]
    overlap: float


def _tokens(text: str) -> list[str]:
    """`text`'s tokens: the words of its scored form."""
    return scored_form(text).split()


def first_clause(text: str) -> str:
    """The first clause of `text`, as the library's splitter cuts it, normalized (`scored_form`);
    empty when `text` says nothing. «تمام، خلني أشوف» gives «تمام»; "Let me check the guide.
    One moment." gives "let me check the guide"."""
    for clause in split_clauses(text, max_chars=None):
        form = scored_form(clause)
        if form:
            return form
    return ""


def token_overlap(first: str, second: str) -> float:
    """How alike two texts' tokens are, from 0.0 to 1.0: the tokens they share (a multiset's
    intersection) over the tokens of the longer of the two, so 0.8 says each holds at least
    four in five of the other's tokens. 0.0 when either says nothing."""
    one, two = Counter(_tokens(first)), Counter(_tokens(second))
    if not one or not two:
        return 0.0
    return (one & two).total() / max(one.total(), two.total())


def cut_reply_share(reply: str, cut_reply: str) -> float:
    """The share of `cut_reply`'s tokens that `reply` holds, from 0.0 to 1.0, each token matched
    at most as often as `reply` holds it: how much of a cut reply's whole text the reply to "one
    more time" says again. 0.0 when `cut_reply` says nothing, since there is nothing to say
    again, so a check that needs a share fails rather than passes."""
    cut = Counter(_tokens(cut_reply))
    if not cut:
        return 0.0
    return (cut & Counter(_tokens(reply))).total() / cut.total()


def repeats_cut_reply(reply: str, cut_reply: str) -> bool:
    """Whether `reply` says a cut reply again: `cut_reply_share` is `CUT_REPEAT_SHARE` (0.6) or
    more."""
    return cut_reply_share(reply, cut_reply) >= CUT_REPEAT_SHARE


def find_repeat(
    reply: str,
    earlier: Sequence[str],
    *,
    asks_repeat: bool = False,
    read_back: bool = False,
) -> Repeat | None:
    """The repeat `reply` makes of the replies before it in the call, `earlier` in the order
    they were said, or None. None too when its turn `asks_repeat` (the caller asked to hear
    something again) or the reply is a `read_back` said again, the two exemptions, and when
    `reply` says nothing. An identical repeat is preferred to a near one; among replies of the
    same kind, the latest is named. TypeError when `earlier` is a bare str, which would be read
    letter by letter."""
    if isinstance(earlier, str):
        raise TypeError("earlier is a sequence of replies, not one str: put one reply in a list")
    text = scored_form(reply)
    if asks_repeat or read_back or not text:
        return None
    clause = first_clause(reply)
    near: Repeat | None = None
    for place in range(len(earlier) - 1, -1, -1):
        before = earlier[place]
        before_text = scored_form(before)
        if not before_text:
            continue
        if before_text == text:
            return Repeat(kind="identical", earlier=place, by="text", overlap=1.0)
        if near is not None:
            continue
        overlap = token_overlap(reply, before)
        if clause and first_clause(before) == clause:
            near = Repeat(kind="near", earlier=place, by="first_clause", overlap=overlap)
        elif overlap >= NEAR_REPEAT_OVERLAP:
            near = Repeat(kind="near", earlier=place, by="overlap", overlap=overlap)
    return near
