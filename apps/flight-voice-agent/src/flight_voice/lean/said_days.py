"""The way back's weekday as the caller named it in the turn a search runs in, read from their
words (`CallContext.heard`), and a search's way back held to it when the model passed none
(`held_days`, D-138). Only the way back's day: the way out's is always the model's.

The model counts dates less well than it copies words, and it does not pass the weekday it
heard: replayed on 2026-11-22, «بكرة، والرجعة السبت» was searched with the way back on
Wednesday the 25th in 10 of 12 tries, and `return_weekday` was passed in none of 36. So the
caller's own words are read here, a narrow fast path the model's reading stays beside (the
owner: lists plus a model's judgement, and the return day free to choose): a weekday word
(Arabic with its article, «السبت», «والسبت», «بالسبت»; or English, "Saturday") is the way back's
when a return word («الرجعة», «العودة», «برجع», «رجوعي», "back", "home" and the like) stands
within the three words before it. A weekday after a negation or an anchor («مو», «غير»,
«بدال», «قبل», «بعد», "not", "instead", "before", "after") names no day. When exactly one
weekday is the way back's, and the model put the way back on another weekday, it moves to
that weekday's nearest date (weekday.py's `on_weekday`, three days at most either way), never
before the day out. A search from the trip's destination to its origin (the way back asked
alone, find_return.py) is the way back's own: the one weekday named, return word or not, holds
its day the same way, never before the trip's day out. A date, a count of days, "next month"
or two weekdays for the way back leave the model's date as it is. Logged when a day is moved.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from t2_agentic_voice import get_logger
from t2_agentic_voice.languages import normalize_arabic

from flight_voice.lean.draft import LeanDraft
from flight_voice.lean.weekday import WEEKDAYS, Weekday, on_weekday

__all__ = ["draft_end", "held_days", "named_days"]

log = get_logger(__name__)

# Each weekday's words: Arabic with its article (the bare forms also mean "one", "a gathering"),
# and English.
_ARABIC: Final[dict[Weekday, tuple[str, ...]]] = {
    "sunday": ("الأحد",),
    "monday": ("الاثنين", "الإثنين", "الاتنين"),
    "tuesday": ("الثلاثاء", "الثلاثا", "الثلوث"),
    "wednesday": ("الأربعاء", "الأربعا", "الربوع"),
    "thursday": ("الخميس",),
    "friday": ("الجمعة",),
    "saturday": ("السبت",),
}
_RETURN: Final = (
    "الرجعة", "رجعة", "رجعتي", "الرجوع", "رجوع", "رجوعي", "العودة", "عودة", "عودتي", "الإياب",
    "إياب", "أرجع", "نرجع", "برجع", "بنرجع", "يرجع", "ترجع", "راجع", "راجعين", "أعود", "نعود",
    "back", "return", "returning", "home",
)  # fmt: skip
_NOT: Final = (
    "مو", "مب", "ماهو", "مهو", "غير", "بدل", "بدال", "قبل", "بعد",
    "not", "instead", "except", "before", "after",
)  # fmt: skip
_PREFIXES: Final = ("", "و", "ب", "وب", "ف")  # «والسبت», «بالسبت»


def _forms(word: str) -> set[str]:
    """`word` normalized as the caller's words are, with the prefixes it takes."""
    plain = normalize_arabic(word)
    found = {p + plain for p in _PREFIXES}
    if plain.startswith("ال"):  # «للسبت»: the article's alef dropped after the preposition
        found |= {"ل" + plain[1:], "ول" + plain[1:]}
    return found


_DAY_OF: Final[dict[str, Weekday]] = {
    form: day for day, words in _ARABIC.items() for word in words for form in _forms(word)
} | {day: day for day in WEEKDAYS}
_BACK: Final = frozenset(form for word in _RETURN for form in _forms(word))
_NEGATION: Final = frozenset(form for word in _NOT for form in _forms(word))


def named_days(heard: str) -> tuple[tuple[Weekday, bool], ...]:
    """Each weekday the caller named in `heard`, in order, and whether a return word stands
    before it (the module's docstring); none after a negation or an anchor."""
    words = normalize_arabic(heard).split()
    found: list[tuple[Weekday, bool]] = []
    for at, word in enumerate(words):
        day = _DAY_OF.get(word)
        if day is None or _NEGATION & set(words[max(0, at - 2) : at]):
            continue
        found.append((day, any(w in _BACK for w in words[max(0, at - 3) : at])))
    return tuple(found)


def draft_end(draft: LeanDraft) -> str | None:
    """The code of the trip's destination, or None: a search from it to the trip's origin is
    the way back's (find.py)."""
    return None if draft.destination is None else draft.destination.code


def held_days(
    heard: str,
    depart: date,
    back: date | None,
    *,
    said: Weekday | None,
    reverse: bool = False,
    day_out: date | None = None,
) -> tuple[date, date | None]:
    """The search's `depart` and `back`, the way back's day held to the one weekday the caller
    named for it when the model passed none (`said`, its `return_weekday`) and put it on another
    (the module's docstring). A `reverse` search is the way back's own: its `depart` is held,
    never before the trip's `day_out`."""
    named = named_days(heard)
    if said is not None or not named:
        return depart, back
    if reverse:
        days = {day for day, _ in named}
        held = depart
        if len(days) == 1:
            held = on_weekday(depart, days.pop(), not_before=day_out or date.min)
        return _logged(depart, back, held, back)
    backs = {day for day, is_back in named if is_back}
    if back is None or len(backs) != 1:
        return depart, back
    return _logged(depart, back, depart, on_weekday(back, backs.pop(), not_before=depart))


def _logged(
    depart: date, back: date | None, out: date, home: date | None
) -> tuple[date, date | None]:
    """`out` and `home`, logged when either moved."""
    if (out, home) != (depart, back):
        log.info(
            "lean_days_held",
            depart=depart.isoformat(),
            held_depart=out.isoformat(),
            back=None if back is None else back.isoformat(),
            held_back=None if home is None else home.isoformat(),
        )
    return out, home
