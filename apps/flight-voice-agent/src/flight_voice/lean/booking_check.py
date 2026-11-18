"""The lean agent's one booking check (D-113; the owner: "code only checks that the booking
matches what was said"), and what each call keeps for it.

`book_trip` books the trip chosen so far only when all of these hold (`confirmed`):
- the trip is complete (the tool checks it: every leg chosen, seats for the travelers);
- since the trip was last completed or changed, a reply of the agent ended;
- the caller spoke after that reply: a turn heard after it ended; or, for a reply cut short, a
  turn later than the one it answered, heard before it ended (`cut_by`); or a turn later than
  the one it answered, heard before it ended, whose speech began once some of the reply had
  played (`spoke_over`: what of the reply had played then, the event's `reply_played`, is not
  empty and begins the reply's text).

The reply need not state the total: the owner's ruling of 2026-11-18, loosening D-113 ("the
confirmation can be done before the agent saying the total, I have it on screen"); the review
card shows it, and the caller has heard the fares. What stays is that the caller spoke after the
trip as it is now was set, so a yes said to a trip before a change never books the changed trip
(the owner's call of 2026-11-18: a yes to 09:30, then 18:15 chosen and booked in the same reply,
refused). A turn that cuts a
  reply can end before the reply's end is told: its transcript comes first, then the overlap's
  verdict stops the reply, so its `UserTurnEnded` comes before the reply's `AgentSpeechEnded`;
  so does a yes said over the closing question, which the library answers only once the reply
  has ended (`interruptions.answer_yes_over_question`, D-116).

**The events.** The check reads the call's events, which the app observes (`runtime.on`, for
each of `OBSERVED`): each `AgentSpeechEnded` (the reply's text, how much of it played, the turn
it answered) and `UserTurnEnded` with words heard (its turn, and what of a reply it began over
had played), kept per call in order and dropped at `CallEnded`, as the trip
book drops the call's trip, at most `MAX_CALLS` calls kept (the oldest dropped past it). A call
held in text reads them from the call itself instead (`read_from`, the `TextCall`'s `emitted`).
The tools mark the trip each time they write it (`mark`): a trip that differs from the one last
marked starts the check again from the events seen so far, so a total said before a change never
books the changed trip.

**A total stated** (`stated_at`): the reply's text normalized as the output guard normalizes it
(the `languages` facade's `normalize_digits` and `normalize_arabic`, a thousands mark between
digits taken out first, a space before three digits among them: "3 080" is 3080) holds the total
as a whole number, or in words in English, Saudi Arabic or MSA (`speak_number`).

Each call also keeps how its booking went (`Ledger`): the booking made and the trip as it was
booked (so a trip changed after the booking is never told as the one booked), or a write whose
end is not known, after which no second write goes out in that call.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import Final

from t2_agentic_voice.events import AgentSpeechEnded, CallEnded, Event, UserTurnEnded
from t2_agentic_voice.languages import normalize_arabic, normalize_digits, speak_number

from flight_voice.airline.bookings import Booking
from flight_voice.trip import TripDraft

MAX_CALLS: Final = 64
# The events the app observes for the check.
OBSERVED: Final[tuple[type[Event], ...]] = (AgentSpeechEnded, UserTurnEnded, CallEnded)
# A thousands mark between digits: the comma, the apostrophe, the Arabic thousands separator
# (U+066C) and the right single quotation mark (U+2019), and a space, a no-break space (U+00A0),
# a thin space (U+2009) or a narrow no-break space (U+202F), named by their code points; each
# only before exactly three digits. The model writes "3 080" now and then (f-dev-lean-4, f09),
# and a total so written was never found, so the caller's yes booked nothing.
_MARKS: Final = ",'" + "".join(chr(c) for c in (0x066C, 0x2019, 0x20, 0xA0, 0x2009, 0x202F))
_THOUSANDS: Final = re.compile(rf"(?<=[0-9])[{_MARKS}](?=[0-9]{{3}}(?![0-9]))")
_SPACES: Final = re.compile(r"\s+")


@dataclass(frozen=True)
class Said:
    """A reply of the agent that ended: its text, the share of it that played, and the caller's
    turn it answered (None for the greeting or a notice)."""

    text: str
    played: float
    turn: int | None = None


@dataclass(frozen=True)
class Heard:
    """A turn of the caller's that was heard, its number, and what of the reply its speech
    began over had played by then (None for a turn begun while the agent was silent)."""

    words: str
    turn: int | None = None
    played: str | None = None


Seen = Said | Heard


@dataclass
class Ledger:
    """How a call's booking went: the booking made and the trip as booked, and whether a
    write's end is not known."""

    booked: Booking | None = None
    trip: TripDraft | None = None
    unsure: bool = False
    writes: int = 0


@dataclass
class _Call:
    seen: list[Seen] = field(default_factory=list)
    trip: object = None
    since: int = 0
    ledger: Ledger = field(default_factory=Ledger)


def _plain(text: str) -> str:
    folded = normalize_arabic(_THOUSANDS.sub("", normalize_digits(text))).lower()
    return _SPACES.sub(" ", folded).strip()


@cache
def _in_words(total: int) -> tuple[str, ...]:
    """`total` in words, each in its plain form: English (with "and" and without), Saudi, MSA."""
    english = speak_number(total, language="en")
    forms = {
        english,
        english.replace(" and ", " "),
        speak_number(total, language="ar-SA", register="saudi"),
        speak_number(total, language="ar-SA", register="msa"),
    }
    return tuple(sorted({_plain(f) for f in forms if f}))


def stated_at(text: str, total: int) -> float | None:
    """Where `text` first states `total`, its end over the text's length (the module's
    docstring), or None when it does not state it."""
    plain = _plain(text)
    if not plain:
        return None
    ends = [m.end() for m in re.finditer(rf"(?<![0-9]){total}(?![0-9])", plain)]
    for form in _in_words(total):
        ends += [m.end() for m in re.finditer(rf"(?<!\w){re.escape(form)}(?!\w)", plain)]
    return min(ends) / len(plain) if ends else None


def _key(draft: TripDraft) -> object:
    """What a trip is, for the check: its route, its legs chosen, its kind, cabin and travelers."""
    legs = (draft.chosen_outbound, None if draft.one_way else draft.chosen_return)
    return (draft.origin, draft.destination, legs, draft.one_way, draft.cabin, draft.travelers)


def _seen(events: Sequence[Event], call_id: str) -> list[Seen]:
    found: list[Seen] = []
    for event in events:
        if event.call_id != call_id:
            continue
        if isinstance(event, AgentSpeechEnded):
            found.append(Said(event.text, event.played_fraction, event.turn_id))
        elif isinstance(event, UserTurnEnded) and event.heard.strip():
            found.append(Heard(event.heard, event.turn_id, event.reply_played))
    return found


def cut_by(said: Said, before: Sequence[Seen]) -> bool:
    """Whether a turn of the caller's later than the one `said` answered, heard among `before`
    (the events seen before `said` ended), cut it: `said` played not whole (the module's
    docstring). A reply that played whole keeps the order of the events."""
    if said.played >= 1 or said.turn is None:
        return False
    answered = said.turn
    return any(isinstance(e, Heard) and e.turn is not None and e.turn > answered for e in before)


def spoke_over(said: Said, before: Sequence[Seen]) -> bool:
    """Whether a turn of the caller's later than the one `said` answered, heard among `before`
    (the events seen before `said` ended), began once some of `said` had played: what had played
    then (`Heard.played`) is not empty and begins its text (the module's docstring)."""
    if said.turn is None:
        return False
    answered = said.turn
    return any(
        isinstance(each, Heard)
        and each.turn is not None
        and each.turn > answered
        and bool(each.played)
        and said.text.startswith(each.played or "")
        for each in before
    )


class BookingCheck:
    """The check and each call's events, trip mark and ledger (the module's docstring)."""

    def __init__(self, *, max_calls: int = MAX_CALLS) -> None:
        self._max = max_calls
        self._calls: OrderedDict[str, _Call] = OrderedDict()
        self._source: Callable[[], Sequence[Event]] | None = None

    def __len__(self) -> int:
        return len(self._calls)

    def read_from(self, source: Callable[[], Sequence[Event]]) -> None:
        """Read every call's events from `source` (a call held in text: its `emitted`)."""
        self._source = source

    def _call(self, call_id: str) -> _Call:
        held = self._calls.get(call_id)
        if held is None:
            held = self._calls[call_id] = _Call()
            while len(self._calls) > self._max:
                self._calls.popitem(last=False)
        return held

    def _events(self, call_id: str) -> list[Seen]:
        if self._source is not None:
            return _seen(self._source(), call_id)
        return self._call(call_id).seen

    async def observed(self, event: Event) -> None:
        """Keep a reply that ended and a turn heard; drop an ended call's: `runtime.on(kind)
        (check.observed)` for each kind of `OBSERVED`."""
        if isinstance(event, CallEnded):
            self._calls.pop(event.call_id, None)
            return
        self._call(event.call_id).seen.extend(_seen((event,), event.call_id))

    def ledger(self, call_id: str) -> Ledger:
        """How the call's booking went so far."""
        return self._call(call_id).ledger

    def mark(self, call_id: str, draft: TripDraft) -> None:
        """The call's trip is `draft` now: when it differs from the trip last marked, the check
        starts again from the events seen so far."""
        held = self._call(call_id)
        key = _key(draft)
        if key != held.trip:
            held.trip, held.since = key, len(self._events(call_id))

    def confirmed(self, call_id: str, draft: TripDraft, total: int) -> bool:
        """Whether a reply of the agent's ended since `draft` was marked and the caller spoke
        after it (the module's docstring); `total` need no longer be said in the reply (the
        owner's ruling of 2026-11-18). A trip not marked as it is never is."""
        del total
        held = self._call(call_id)
        if _key(draft) != held.trip:
            self.mark(call_id, draft)
            return False
        seen = self._events(call_id)[held.since :]
        for n, each in enumerate(seen):
            if not isinstance(each, Said):
                continue
            after = any(isinstance(later, Heard) for later in seen[n + 1 :])
            if after or cut_by(each, seen[:n]) or spoke_over(each, seen[:n]):
                return True
        return False
