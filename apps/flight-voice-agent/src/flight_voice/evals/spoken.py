"""How the agent's spoken words are read by run F's checks (evals/checks.py): the scorers' form
of a text, the register of the agent's own Arabic words (rule F's amendment of 2026-11-17: the
library's `register_of` reads the caller's words, and failed the Saudi forms the agent's
instructions prescribe, «متى ودك ترجع؟»), and the agent's failure notices."""

from __future__ import annotations

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
