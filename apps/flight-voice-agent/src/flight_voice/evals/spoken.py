"""How the agent's spoken words are read by run F's checks (evals/checks.py): the scorers' form
of a text, the register of the agent's own Arabic words (rule F's amendment of 2026-11-17: the
library's `register_of` reads the caller's words, and failed the Saudi forms the agent's
instructions prescribe, «متى ودك ترجع؟»), the agent's failure notices, and a stage note or
markup heard (`stage_note`, rule F's amendment of 2026-11-17 on stage notes: f-dev-5's callers
heard "(Waiting for user response)" and a book_trip tag, and no check failed them)."""

from __future__ import annotations

import re
from functools import cache
from typing import Final

from t2_agentic_voice.languages import normalize_arabic, normalize_digits, register_of

from flight_voice.agent import languages
from flight_voice.persona import Names


def form(text: str) -> str:
    """`text` in the scorers' form, so words compare alike in either script."""
    return normalize_digits(normalize_arabic(text))


# Forms only MSA says, never a Saudi reply (each in the scorers' form, with or without wa).
MSA_ONLY: Final = frozenset(
    [
        "سوف",
        "لن",
        "الآن",
        "أريد",
        "تريد",
        "تريدون",
        "ماذا",
        "لماذا",
        "لدينا",
        "لديك",
        "ليس",
        "ليست",
        "هكذا",
        "حسنا",
        "يمكنك",
    ]
)
# The agent's own Saudi forms (instructions/ar-SA.md) besides the caller's (`register_of`).
SAUDI_FORMS: Final = frozenset(
    ["ودك", "تبي", "تبون", "حقت", "الصبح", "رايح", "لقيت", "أبشر", "زين"]
)


# The words a stage note opens with: the guard's closed list (`guard.drop_stage_notes`), written
# here again, so the measurement never reads the rule it measures.
STAGE_WORDS: Final = (
    "Waiting",
    "Awaiting",
    "Wait for",
    "Pause",
    "Silence",
    "No output",
    "No reply",
    "No response",
    "No further",
    "No answer",
    "Listening",
    "Thinking",
    "انتظار",  # intiZaar, waiting: «[انتظار رد العميل]»
)
_STAGE: Final = re.compile(
    r"[(\[]\s*(?:" + "|".join(re.escape(word) for word in STAGE_WORDS) + ")", re.IGNORECASE
)
_LATIN_HELD: Final = re.compile(r"[(\[][^()\[\]]*[A-Za-z]")
_TAG: Final = re.compile(r"</?[A-Za-z!|]")
_ARABIC: Final = re.compile(r"[؀-ۿ]")


def stage_note(text: str) -> bool:
    """Whether `text`, what the caller heard of one turn, holds a stage note or markup: a
    parenthesis or bracket that holds a Latin letter in a reply in Arabic script (one with an
    Arabic letter), one that opens a stage word in any language and any case, or a "<" that
    opens a tag."""
    if _STAGE.search(text) or _TAG.search(text):
        return True
    return bool(_ARABIC.search(text) and _LATIN_HELD.search(text))


def _words(text: str) -> set[str]:
    found = set(form(text).split())
    return found | {w[1:] for w in found if w.startswith("و") and len(w) > 2}


def _in(text: str, forms: frozenset[str]) -> bool:
    return bool(_words(text) & {form(f) for f in forms})


def register_held(text: str, wanted: str) -> bool:
    """Whether the Arabic `text`, the agent's own words, is in the register `wanted`."""
    if wanted == "saudi":
        return not _in(text, MSA_ONLY)
    return register_of(text) != "saudi" and not _in(text, SAUDI_FORMS)


@cache
def failure_notices() -> frozenset[str]:
    """The agent's failure notices, the error and cut-off lines, each language's, in the
    scorers' form."""
    return frozenset(
        form(lang.notices[kind]) for lang in languages(Names()) for kind in ("error", "cut_off")
    )
